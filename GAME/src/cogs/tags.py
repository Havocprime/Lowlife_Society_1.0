# GAME/src/cogs/tags.py
from __future__ import annotations

import os, logging, traceback, uuid, difflib, inspect, re
from typing import Optional, Callable, Tuple, Any

import discord
from discord import app_commands, Interaction
from discord.ext import commands

# Tag engine (display-name catalog + instances)
from src.systems.tags.schema import ensure_tags_schema
import src.systems.tags.dal as tag_dal  # keep the module form only

# Core DAL (player lookup)
from src.db import dal as core_dal

# Health service
from src.services import health as health_svc

log = logging.getLogger("tags.cog")

# Export a registry object for other modules (e.g., playerlog) that import us.
registry = getattr(tag_dal, "_registry", None)

# Use the engine that DAL already created (bound to the registry).
try:
    ENGINE = tag_dal.engine()
except Exception:
    ENGINE = None  # shims below will no-op safely


# ------------------------------ config ------------------------------

def _enabled() -> bool:
    return os.getenv("TAGS_ENABLED", "0") == "1"

FALLBACK_OWNER_KIND = os.getenv("TAGS_FALLBACK_OWNER_KIND", "discord")


# ------------------------------ seed catalog import ------------------
try:
    from src.cogs.tags_catalog import get_seed_catalog  # type: ignore
except Exception:
    try:
        from src.tags.catalog import get_seed_catalog  # type: ignore
    except Exception:
        def get_seed_catalog() -> dict[str, dict]:
            return {
                "status.bleeding": {"family": "status", "max_intensity": 10},
                "wound.gunshot": {"family": "wound", "max_intensity": 3},
                "wound.bruise": {"family": "wound", "max_intensity": 3},
                "wound.scratch": {"family": "wound", "max_intensity": 3},
            }


# ------------------------------ helpers ------------------------------

def _rget(row, key, default=None):
    """Safe dict/Row access that won't explode on missing keys."""
    try:
        return row[key]
    except Exception:
        try:
            # sqlite3.Row vs tuple
            idx = 0 if key == "id" else None
            if idx is not None:
                return row[idx]
        except Exception:
            pass
        return default


async def _engine_start(engine) -> None:
    if not engine:
        return
    start = getattr(engine, "start", None)
    if not callable(start):
        return
    if inspect.iscoroutinefunction(start):
        await start()
    else:
        try:
            start()
        except Exception:
            log.debug("ENGINE.start() raised (sync); continuing.", exc_info=True)


async def _engine_stop(engine) -> None:
    if not engine:
        return
    stop = getattr(engine, "stop", None)
    if not callable(stop):
        return
    if inspect.iscoroutinefunction(stop):
        await stop()
    else:
        try:
            stop()
        except Exception:
            log.debug("ENGINE.stop() raised (sync); continuing.", exc_info=True)


def _conn():
    """Best-effort writer connection to the core DB."""
    for name in ("write_conn", "conn", "_conn", "get_conn"):
        fn = getattr(core_dal, name, None)
        if callable(fn):
            return fn()
    raise RuntimeError("No DAL connection factory found")


def ensure_seed_keys():
    """
    Create/seed the key registry table used by HP-drain models.
    NOTE: This writes to `tag_keys` to avoid colliding with `systems.tags.tags`.
    """
    cat = get_seed_catalog()
    con = _conn()
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tag_keys(
            key TEXT PRIMARY KEY,
            family TEXT,
            max_intensity INTEGER
        )
    """)
    cur.executemany(
        "INSERT OR IGNORE INTO tag_keys(key, family, max_intensity) VALUES(?, ?, ?)",
        [(k, v.get("family"), int(v.get("max_intensity", 10))) for k, v in cat.items()]
    )
    con.commit()
    log.info("Seeded %d tag key(s) into tag_keys (idempotent).", len(cat))


def _ensure_tag_keys_table(con):
    con.execute("""
        CREATE TABLE IF NOT EXISTS tag_keys(
            key TEXT PRIMARY KEY,
            family TEXT,
            max_intensity INTEGER
        )
    """)


def _migrate_seed_catalog_into_tag_keys(con):
    # Only populate when empty
    cur = con.execute("SELECT COUNT(*) FROM tag_keys")
    if int(cur.fetchone()[0]) > 0:
        return
    cat = get_seed_catalog()
    rows = [(k, v.get("family"), int(v.get("max_intensity", 10))) for k, v in cat.items()]
    con.executemany(
        "INSERT OR IGNORE INTO tag_keys(key, family, max_intensity) VALUES(?, ?, ?)",
        rows
    )
    con.commit()


def _which_db(con) -> str:
    try:
        row = con.execute("PRAGMA database_list").fetchone()
        if row is None:
            return "<unknown>"
        try:
            return row["file"] or "<memory>"
        except Exception:
            try:
                return row[2] or "<memory>"
            except Exception:
                return str(row)
    except Exception:
        return "<unknown>"


# Robust owner resolver (player if available; else discord)
def _resolve_owner(user: discord.abc.User) -> Tuple[str, int]:
    """
    Returns (owner_kind, owner_id).
    1) Try common DAL helpers to get a canonical 'player' id.
    2) If none work, fall back to ('discord', discord_id).
    """
    candidates: list[tuple[str, Callable]] = []
    for name in ("get_or_create_player", "get_or_create_account", "player_get_or_create", "ensure_player"):
        fn = getattr(core_dal, name, None)
        if callable(fn):
            candidates.append((name, fn))

    discord_id = int(user.id)

    for name, fn in candidates:
        try:
            try:
                pid = fn(discord_id=discord_id)  # keyword form
            except TypeError:
                pid = fn(discord_id)            # positional form
            pid_int = int(pid)
            return ("player", pid_int)
        except Exception as e:
            log.debug("DAL helper %s failed: %r", name, e)

    log.warning(
        "Tags: falling back to (%s, %s) — no player DAL helper succeeded",
        FALLBACK_OWNER_KIND, discord_id
    )
    return (FALLBACK_OWNER_KIND, discord_id)


def _read_hp(owner_kind: str, owner_id: int) -> Tuple[int, int]:
    """
    Read HP safely regardless of health service return shape.
    If owner_kind != 'player', returns a neutral default.
    """
    try:
        if owner_kind != "player":
            return (0, 100)
        st = health_svc.get_state(owner_id)
        if isinstance(st, dict):
            return int(st.get("hp", 0)), int(st.get("max_hp", 100))
        if isinstance(st, (tuple, list)) and len(st) >= 2:
            return int(st[0]), int(st[1])
    except Exception:
        log.debug("health.get_state failed for %s:%s", owner_kind, owner_id, exc_info=True)
    return (0, 100)


def _catalog_names() -> list[str]:
    """List all tag display-names from the catalog table managed by systems.tags.*"""
    con = tag_dal._conn()
    try:
        rows = con.execute("SELECT name FROM tags").fetchall()
    except Exception:
        return []
    names: list[str] = []
    for r in rows:
        try:
            names.append(r["name"])
        except Exception:
            try:
                names.append(r[0])
            except Exception:
                pass
    return names


# tolerant name lookup (exact, case-insensitive, a few aliases)
_ALIASES = {
    "bleed": "Bleeding",
    "bleeding": "Bleeding",
    "gunshot": "Gunshot Wound",
    "gunshot_wound": "Gunshot Wound",
    "gsw": "Gunshot Wound",
}

def _canonical_tag_name(requested: str) -> Optional[str]:
    names = _catalog_names()
    if requested in names:
        return requested
    lowered = {n.lower(): n for n in names}
    if requested.lower() in lowered:
        return lowered[requested.lower()]
    alias = _ALIASES.get(requested.lower())
    if alias and alias in names:
        return alias
    return None


def _suggest_names(requested: str, limit: int = 3) -> list[str]:
    names = _catalog_names()
    choices = list({*names, *(_ALIASES.values())})
    return difflib.get_close_matches(requested, choices, n=limit, cutoff=0.5)


def _parse_severity(value: str | int | None) -> int:
    """Map 'light/medium/heavy' or '1/2/3' (as str/int) → 1..3, default 3."""
    if value is None:
        return 3
    s = str(value).strip().lower()
    if s.isdigit():
        try:
            return max(1, min(3, int(s)))
        except Exception:
            return 3
    mapping = {
        "light": 1, "lite": 1, "minor": 1,
        "medium": 2, "moderate": 2,
        "heavy": 3, "severe": 3,
    }
    return mapping.get(s, 3)


# ------------------------------ name → key resolver ------------------------------

# Hard mappings for our default catalog.
_NAME_TO_KEY = {
    "Bleeding": "status.bleeding",
    "Gunshot Wound": "wound.gunshot",
}
# lowercase convenience
_NAME_TO_KEY_LOWER = {k.lower(): v for k, v in _NAME_TO_KEY.items()}

def _list_all_keys() -> list[str]:
    """Read all engine keys from tag_keys (core DB)."""
    try:
        con = _conn()
        rows = con.execute("SELECT key FROM tag_keys ORDER BY key").fetchall()
    except Exception:
        return []
    out: list[str] = []
    for r in rows:
        try:
            out.append(r["key"])
        except Exception:
            try:
                out.append(r[0])
            except Exception:
                pass
    return out

def _display_name_to_key(name_or_key: str) -> Optional[str]:
    """
    Accepts either a display name ('Bleeding') or a raw key ('status.bleeding').
    Returns the engine key if it can be resolved.
    """
    s = (name_or_key or "").strip()
    if not s:
        return None

    # If it's already a key we know, take it.
    all_keys = _list_all_keys()
    if s in all_keys:
        return s

    # Known explicit map
    if s in _NAME_TO_KEY:
        return _NAME_TO_KEY[s]
    if s.lower() in _NAME_TO_KEY_LOWER:
        return _NAME_TO_KEY_LOWER[s.lower()]

    # Heuristics: try matching suffix (e.g., 'bleeding' → 'status.bleeding')
    slug = s.lower().replace(" ", "_")
    for k in all_keys:
        if k.lower().endswith(slug):
            return k

    # Fuzzy last resort
    if all_keys:
        lowers = [k.lower() for k in all_keys]
        hits = difflib.get_close_matches(slug, lowers, n=1, cutoff=0.6)
        if hits:
            idx = lowers.index(hits[0])
            return all_keys[idx]

    return None


# ------------------------------ DAL shims ------------------------------

def _dal_apply_tag(
    owner_kind: str,
    owner_id: int,
    tag_key: str,
    *,
    anchor_path: str = "entity",
    stacks: int = 1,
    duration_ms: Optional[int] = None,
    source_kind: Optional[str] = None,
    source_ref: Optional[str] = None,
):
    """
    Version-tolerant wrapper around the DAL's apply_tag.

    The DAL expects a **key** (e.g., 'status.bleeding' or 'wound.gunshot').

    We handle a variety of calling conventions and kwargs:
      - A) apply_tag(owner_kind, owner_id, key, **kwargs)
      - B) apply_tag(entity_id, key, **kwargs)                 # entity_id may be (kind,id) | "kind:id" | id
      - C) apply_tag_name(entity_id=..., tag_name=..., **kwargs)  # legacy helper

    Kwarg normalization:
      anchor_path → anchor
      stacks      → count
      duration_ms → duration

    If the engine raises "unexpected keyword argument 'X'", we drop X and retry.
    We also try a minimal call with no kwargs first, then add normalized kwargs.
    """
    fn = getattr(tag_dal, "apply_tag", None)
    if not callable(fn):
        raise RuntimeError("tags.dal.apply_tag is not available")

    # Normalize/rename kwargs and remove Nones
    base_kwargs = {
        "anchor": anchor_path,
        "count": int(max(1, stacks)),
        "duration": None if duration_ms is None else int(duration_ms),
        "source_kind": source_kind,
        "source_ref": source_ref,
    }
    base_kwargs = {k: v for k, v in base_kwargs.items() if v is not None}

    # Try *no kwargs first* (some engines only accept required args)
    kw_variants: list[dict[str, Any]] = [
        {},
        {k: base_kwargs[k] for k in ("anchor", "count", "duration") if k in base_kwargs},
        base_kwargs,  # richer
    ]

    # Candidate positional signatures
    entity_id_str = f"{owner_kind}:{int(owner_id)}"
    arg_variants: list[tuple[Any, ...]] = [
        (owner_kind, int(owner_id), tag_key),  # (kind, id, key)
        (entity_id_str, tag_key),              # ("kind:id", key)
        (int(owner_id), tag_key),              # (id, key)
    ]

    def _call_with_pruning(callable_fn, args: tuple[Any, ...], kw: dict) -> Any:
        """
        Call fn(*args, **kw). If a TypeError mentions an unexpected kw,
        drop it and retry until it sticks or another error occurs.
        """
        while True:
            try:
                return callable_fn(*args, **kw)  # type: ignore[misc]
            except TypeError as te:
                # Handle: unexpected keyword argument 'foo'
                m = re.search(r"unexpected keyword argument '([^']+)'", str(te))
                if m:
                    bad = m.group(1)
                    if bad in kw:
                        kw.pop(bad)
                        continue
                # Also handle: got multiple values for argument 'x'
                m2 = re.search(r"multiple values for argument '([^']+)'", str(te))
                if m2:
                    bad = m2.group(1)
                    if bad in kw:
                        kw.pop(bad)
                        continue
                raise

    last_err: Optional[BaseException] = None

    # 1) Try minimal→richer kwargs across all arg signatures
    for args in arg_variants:
        for kw in kw_variants:
            try:
                return _call_with_pruning(fn, args, dict(kw))
            except Exception as e:
                last_err = e

    # 2) Legacy fallback if provided by your DAL
    alt = getattr(tag_dal, "apply_tag_name", None)
    if callable(alt):
        # Map to legacy names if needed
        for args in ((entity_id_str, tag_key), (int(owner_id), tag_key)):
            for kw in kw_variants:
                k2 = dict(kw)
                if "count" in k2 and "stacks" not in k2:
                    k2["stacks"] = k2.pop("count")
                if "duration" in k2 and "duration_ms" not in k2:
                    k2["duration_ms"] = k2.pop("duration")
                if "anchor" in k2 and "anchor_path" not in k2:
                    k2["anchor_path"] = k2.pop("anchor")
                # alt usually takes explicit named params
                def _alt_call(entity, tag):
                    return alt(entity_id=entity, tag_name=tag, **k2)  # type: ignore[misc]
                try:
                    return _call_with_pruning(_alt_call, (args[0], args[1]), {})
                except Exception as e:
                    last_err = e

    raise RuntimeError(f"apply_tag failed: {last_err!r}" if last_err else "apply_tag failed")


def _dal_list_instances(owner_kind: str, owner_id: int):
    """Try DAL helper; if missing, query directly."""
    fn = getattr(tag_dal, "list_instances", None)
    if callable(fn):
        return fn(owner_kind, owner_id)

    con = tag_dal._conn()
    return con.execute(
        """
        SELECT i.id, i.owner_kind, i.owner_id, i.anchor_path, i.stacks,
               i.tick_ms, i.state, t.name
        FROM tag_instances i
        JOIN tags t ON t.id = i.tag_id
        WHERE i.owner_kind = ? AND i.owner_id = ?
        ORDER BY i.id DESC
        """,
        (owner_kind, owner_id),
    ).fetchall()


def _dal_clear_owner(owner_kind: str, owner_id: int) -> int:
    """Try DAL helper; if missing, delete directly and return count."""
    fn = getattr(tag_dal, "clear_owner", None)
    if callable(fn):
        return int(fn(owner_kind, owner_id))

    con = tag_dal._conn()
    cur = con.execute(
        "DELETE FROM tag_instances WHERE owner_kind = ? AND owner_id = ?",
        (owner_kind, owner_id),
    )
    con.commit()
    if cur.rowcount is not None and cur.rowcount >= 0:
        return int(cur.rowcount)
    return 0


# ------------------------------ core helpers ------------------------------

async def _apply_gunshot(
    itx: Interaction,
    *,
    owner_kind: str,
    owner_id: int,
    target: discord.Member | discord.User,
    anchor_path: str,
    stacks: int,
) -> None:
    """Core implementation used by both /dev_gunshot and /wound_gunshot."""
    # Resolve engine keys
    gsw_key = _display_name_to_key("Gunshot Wound")
    if not gsw_key:
        await itx.followup.send("❌ `Gunshot Wound` key not found. Run **/tag_seed** first.", ephemeral=True)
        return

    iid = _dal_apply_tag(
        owner_kind, owner_id, gsw_key,
        anchor_path=anchor_path,
        stacks=max(1, int(stacks)),
        duration_ms=None,
        source_kind="cmd",
        source_ref="gunshot",
    )

    bleed_key = _display_name_to_key("Bleeding")
    if bleed_key:
        _dal_apply_tag(
            owner_kind, owner_id, bleed_key,
            anchor_path=anchor_path,
            stacks=max(1, int(stacks) - 1),
            duration_ms=None,
            source_kind="cmd",
            source_ref="gunshot",
        )

    await itx.followup.send(
        f"🩸 Applied **Gunshot Wound** (sev {stacks}) @ `{anchor_path}` on {target.mention} "
        f"(owner=`{owner_kind}:{owner_id}`, instance #{iid})",
        ephemeral=True,
    )


# ------------------------------ display-name seeding ------------------------------

_DEFAULT_CATALOG = [
    {"name": "Bleeding",       "kind": "dynamic", "polarity": "negative", "config_json": None},
    {"name": "Gunshot Wound",  "kind": "event",   "polarity": "negative", "config_json": None},
]

def _seed_catalog() -> tuple[int, int]:
    """
    Insert defaults if missing into systems.tags.tags (display catalog).
    Returns (inserted_count, total_rows_after).
    """
    con = tag_dal._conn()
    inserted = 0
    for row in _DEFAULT_CATALOG:
        cur = con.execute(
            "INSERT OR IGNORE INTO tags (name, kind, polarity, config_json) VALUES (?, ?, ?, ?)",
            (row["name"], row["kind"], row["polarity"], row["config_json"]),
        )
        inserted += cur.rowcount if hasattr(cur, "rowcount") else 0
    cur = con.execute("SELECT COUNT(*) AS c FROM tags")
    total = cur.fetchone()["c"]
    con.commit()
    return (inserted, total)


# ------------------------------ cog --------------------------------

class TagsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        try:
            ensure_tags_schema()   # catalog/instances schema
            ensure_seed_keys()     # key registry (tag_keys) for HP-drain models
            log.info("Tags schema ensured and tag_keys seeded.")
        except Exception as e:
            log.exception("Startup failed: %s", e)

        for noisy in ("tags.registry", "tags.engine", "health"):
            logging.getLogger(noisy).setLevel(logging.WARNING)

        if _enabled():
            await _engine_start(ENGINE)

    async def cog_unload(self):
        if _enabled():
            await _engine_stop(ENGINE)

    # ----------------------- Commands -----------------------

    @app_commands.command(name="tag_catalog", description="List available tag templates in the catalog")
    async def tag_catalog(self, itx: Interaction):
        if not _enabled():
            return await itx.response.send_message("Tags disabled.", ephemeral=True)
        await itx.response.defer(ephemeral=True)

        try:
            con = tag_dal._conn()
            rows = con.execute(
                "SELECT name, kind, polarity FROM tags ORDER BY name LIMIT 200"
            ).fetchall()
            if not rows:
                return await itx.followup.send("Catalog is empty. Run /tag_seed.", ephemeral=True)
            lines = [
                f"- **{r['name']}**  ({(r['kind'] or 'dynamic')}{(' · ' + r['polarity']) if r['polarity'] else ''})"
                for r in rows
            ]
            await itx.followup.send("\n".join(lines), ephemeral=True)
        except Exception:
            trace = uuid.uuid4().hex[:8]
            log.error("[tag_catalog] trace=%s\n%s", trace, traceback.format_exc())
            await itx.followup.send(f"⚠️ Catalog read failed. Trace `{trace}`.", ephemeral=True)

    @app_commands.command(name="tag_add", description="[DEV] Apply a tag to an anchor on a player/discord user")
    @app_commands.describe(
        tag_name="Catalog name (e.g., Bleeding) — or a raw key (e.g., status.bleeding)",
        anchor_path="Where to attach (e.g., body:Left Bicep)",
        stacks="Stacks to add",
        duration_ms="Duration override in ms",
        user="Target user (defaults to you)"
    )
    async def tag_add(
        self,
        itx: Interaction,
        tag_name: str,
        anchor_path: str = "entity",
        stacks: int = 1,
        duration_ms: Optional[int] = None,
        user: Optional[discord.Member] = None,
    ):
        if not _enabled():
            return await itx.response.send_message("Tags disabled.", ephemeral=True)

        await itx.response.defer(ephemeral=True)
        trace = uuid.uuid4().hex[:8]

        try:
            target = user or itx.user
            owner_kind, owner_id = _resolve_owner(target)

            # Allow raw key OR display name.
            key: Optional[str] = None
            all_keys = _list_all_keys()
            if tag_name in all_keys:
                key = tag_name
                canon = None
            else:
                canon = _canonical_tag_name(tag_name)
                if not canon:
                    suggestions = _suggest_names(tag_name)
                    hint = f" Did you mean: {', '.join(f'`{s}`' for s in suggestions)}?" if suggestions else ""
                    return await itx.followup.send(f"❌ Tag `{tag_name}` not found in catalog.{hint}", ephemeral=True)
                key = _display_name_to_key(canon)

            if not key:
                # give a helpful hint with nearby keys
                nearby = difflib.get_close_matches(tag_name.lower().replace(" ", "_"),
                                                   [k.lower() for k in all_keys], n=3, cutoff=0.5)
                hint = f" Try a key like: {', '.join(f'`{k}`' for k in nearby)}." if nearby else ""
                return await itx.followup.send(
                    f"❌ Could not resolve a tag key for `{tag_name}`.{hint}", ephemeral=True
                )

            iid = _dal_apply_tag(
                owner_kind, owner_id, key,
                anchor_path=anchor_path,
                stacks=max(1, int(stacks)),
                duration_ms=duration_ms,
                source_kind="cmd",
                source_ref="tag_add",
            )

            shown = canon or key
            await itx.followup.send(
                f"✅ `{shown}` x{stacks} → `{anchor_path}` on {target.mention} "
                f"(owner=`{owner_kind}:{owner_id}`, instance #{iid})",
                ephemeral=True,
            )

        except Exception:
            log.error("[tag_add] trace=%s\n%s", trace, traceback.format_exc())
            await itx.followup.send(f"⚠️ Something broke. Trace `{trace}`. (See server logs.)", ephemeral=True)

    @app_commands.command(name="tag_list", description="List your active tags")
    async def tag_list(self, itx: Interaction, user: Optional[discord.Member] = None):
        if not _enabled():
            return await itx.response.send_message("Tags disabled.", ephemeral=True)

        await itx.response.defer(ephemeral=True)
        trace = uuid.uuid4().hex[:8]

        try:
            target = user or itx.user
            owner_kind, owner_id = _resolve_owner(target)

            rows = _dal_list_instances(owner_kind, owner_id)
            if not rows:
                return await itx.followup.send("No active tags.", ephemeral=True)

            lines = []
            for r in rows:
                tick_ms = _rget(r, "tick_ms")
                timer = f"⏱ {int(tick_ms)}ms" if tick_ms else ""
                state = f" · state:`{_rget(r, 'state')}`" if _rget(r, "state") else ""
                anchor = _rget(r, "anchor_path", "entity")
                lines.append(f"- **{_rget(r,'name','<unknown>')}** x{_rget(r,'stacks',1)} @ `{anchor}` {timer}{state}")

            await itx.followup.send("\n".join(lines), ephemeral=True)

        except Exception:
            log.error("[tag_list] trace=%s\n%s", trace, traceback.format_exc())
            await itx.followup.send(f"⚠️ Something broke. Trace `{trace}`.", ephemeral=True)

    @app_commands.command(name="tag_clear", description="[DEV] Clear all tags from a player/discord user")
    async def tag_clear(self, itx: Interaction, user: Optional[discord.Member] = None):
        if not _enabled():
            return await itx.response.send_message("Tags disabled.", ephemeral=True)

        await itx.response.defer(ephemeral=True)
        trace = uuid.uuid4().hex[:8]

        try:
            target = user or itx.user
            owner_kind, owner_id = _resolve_owner(target)
            n = _dal_clear_owner(owner_kind, owner_id)
            await itx.followup.send(
                f"🧹 Cleared {n} tag(s) from {target.mention} (owner=`{owner_kind}:{owner_id}`).",
                ephemeral=True
            )
        except Exception:
            log.error("[tag_clear] trace=%s\n%s", trace, traceback.format_exc())
            await itx.followup.send(f"⚠️ Something broke. Trace `{trace}`.", ephemeral=True)

    @app_commands.command(name="status", description="Show HP and active tags for you (or a target user)")
    async def status(self, itx: Interaction, user: Optional[discord.Member] = None):
        if not _enabled():
            return await itx.response.send_message("Tags disabled.", ephemeral=True)
        await itx.response.defer(ephemeral=True)
        trace = uuid.uuid4().hex[:8]

        try:
            target = user or itx.user
            owner_kind, owner_id = _resolve_owner(target)

            hp, max_hp = _read_hp(owner_kind, owner_id)
            rows = _dal_list_instances(owner_kind, owner_id)

            lines = [f"**HP:** {hp}/{max_hp}  ·  **Owner:** `{owner_kind}:{owner_id}`"]
            if rows:
                for r in rows:
                    tick_ms = _rget(r, "tick_ms")
                    timer = f"⏱ {int(tick_ms)}ms" if tick_ms else ""
                    state = f" · state:`{_rget(r, 'state')}`" if _rget(r, "state") else ""
                    anchor = _rget(r, "anchor_path", "entity")
                    lines.append(f"- **{_rget(r,'name','<unknown>')}** x{_rget(r,'stacks',1)} @ `{anchor}` {timer}{state}")
            else:
                lines.append("_No active tags_")

            await itx.followup.send("\n".join(lines), ephemeral=True)

        except Exception:
            log.error("[status] trace=%s\n%s", trace, traceback.format_exc())
            await itx.followup.send(f"⚠️ Something broke. Trace `{trace}`.", ephemeral=True)

    # ----------------------- DEV Utilities -----------------------

    @app_commands.command(name="dev_gunshot", description="[DEV] Apply a Gunshot Wound (and auto-bleed) to a user")
    @app_commands.describe(
        severity="light | medium | heavy | 1 | 2 | 3",
        anchor_path="Where to attach (e.g., body:Left Bicep)",
        user="Target user (defaults to you)",
    )
    async def dev_gunshot(
        self,
        itx: Interaction,
        severity: str = "heavy",
        anchor_path: str = "body:Left Bicep",
        user: Optional[discord.Member] = None,
    ):
        if not _enabled():
            return await itx.response.send_message("Tags disabled.", ephemeral=True)

        await itx.response.defer(ephemeral=True)

        try:
            target = user or itx.user
            owner_kind, owner_id = _resolve_owner(target)
            stacks = _parse_severity(severity)
            await _apply_gunshot(
                itx,
                owner_kind=owner_kind,
                owner_id=owner_id,
                target=target,
                anchor_path=anchor_path,
                stacks=stacks,
            )
        except Exception:
            trace = uuid.uuid4().hex[:8]
            log.error("[dev_gunshot] trace=%s\n%s", trace, traceback.format_exc())
            await itx.followup.send(f"⚠️ Something broke. Trace `{trace}`.", ephemeral=True)

    @app_commands.command(name="wound_gunshot", description="[DEV] Numeric version of /dev_gunshot (1–3)")
    @app_commands.describe(
        severity="1 (light), 2 (medium), 3 (heavy)",
        anchor_path="Where to attach (e.g., body:Left Bicep)",
        user="Target user (defaults to you)",
    )
    async def wound_gunshot(
        self,
        itx: Interaction,
        severity: app_commands.Range[int, 1, 3] = 3,
        anchor_path: str = "body:Left Bicep",
        user: Optional[discord.Member] = None,
    ):
        if not _enabled():
            return await itx.response.send_message("Tags disabled.", ephemeral=True)

        await itx.response.defer(ephemeral=True)

        try:
            target = user or itx.user
            owner_kind, owner_id = _resolve_owner(target)
            await _apply_gunshot(
                itx,
                owner_kind=owner_kind,
                owner_id=owner_id,
                target=target,
                anchor_path=anchor_path,
                stacks=int(severity),
            )
        except Exception:
            trace = uuid.uuid4().hex[:8]
            log.error("[wound_gunshot] trace=%s\n%s", trace, traceback.format_exc())
            await itx.followup.send(f"⚠️ Something broke. Trace `{trace}`.", ephemeral=True)

    # ----------------------- Seeder (always available) -----------------------

    @app_commands.command(name="tag_seed", description="Seed the tag catalog / keys and show what's installed")
    async def tag_seed(self, itx: Interaction):
        # Intentionally available even if TAGS_ENABLED=0 so you can prepare the DB.
        await itx.response.defer(ephemeral=True)
        trace = uuid.uuid4().hex[:8]
        try:
            ensure_tags_schema()
            ensure_seed_keys()  # creates/populates tag_keys

            con = tag_dal._conn()

            db_path = _which_db(con)
            lines: list[str] = [f"🗄️ DB: `{db_path}`"]

            has_tag_keys = bool(con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='tag_keys'"
            ).fetchone())

            if not has_tag_keys:
                lines.append("ℹ️ `tag_keys` not found — creating and seeding from seed catalog.")
                _ensure_tag_keys_table(con)
                _migrate_seed_catalog_into_tag_keys(con)
                has_tag_keys = True

            if has_tag_keys:
                c = con.execute("SELECT COUNT(*) FROM tag_keys").fetchone()[0]
                lines.append(f"🔧 `tag_keys` present — {c} key(s).")
                for r in con.execute("SELECT key, family, max_intensity FROM tag_keys ORDER BY key").fetchall():
                    try:
                        key = r["key"]; fam = r["family"]; mx = int(r["max_intensity"])
                    except Exception:
                        key, fam, mx = r[0], r[1], int(r[2])
                    lines.append(f"- **{key}**  (family:`{fam}`, max:{mx})")

            if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='tags'").fetchone():
                c = con.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
                lines.append(f"\n📚 `tags` table present — {c} row(s).")
                for r in con.execute("SELECT name, COALESCE(kind,'dynamic') AS kind, polarity FROM tags ORDER BY name").fetchall():
                    pol = f" · {r['polarity']}" if r['polarity'] else ""
                    lines.append(f"- **{r['name']}**  ({r['kind']}{pol})")

            msg = "\n".join(lines)
            if len(msg) > 1900:
                msg = msg[:1900] + "\n…"
            await itx.followup.send(msg or "Done.", ephemeral=True)

        except Exception:
            log.error("[tag_seed] trace=%s\n%s", trace, traceback.format_exc())
            try:
                await itx.followup.send(f"⚠️ Seeding failed. Trace `{trace}`. Check logs.", ephemeral=True)
            except Exception:
                pass


# ------------------------------ setup --------------------------------

async def setup(bot: commands.Bot):
    await bot.add_cog(TagsCog(bot))
