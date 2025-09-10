# GAME/src/cogs/tags.py
from __future__ import annotations

import os, logging, traceback, uuid, difflib
from typing import Optional, Callable, Tuple

import discord
from discord import app_commands, Interaction
from discord.ext import commands

# Tag engine (display-name catalog + instances)
from src.systems.tags.schema import ensure_tags_schema
from src.systems.tags import dal as tag_dal
from src.systems.tags.engine import TagEngine
from src.systems.tags.api import apply_tag

# Core DAL (player lookup)
from src.db import dal as core_dal

# Health service
from src.services import health as health_svc

# Key-based registry seeds (bruise/scratch/wound.* etc.)
from src.tags.catalog import get_seed_catalog
from src.db import dal  # raw connection for our tag_keys seeder

log = logging.getLogger("tags.cog")
ENGINE = TagEngine()

# ------------------------------ config ------------------------------

def _enabled() -> bool:
    return os.getenv("TAGS_ENABLED", "0") == "1"

FALLBACK_OWNER_KIND = os.getenv("TAGS_FALLBACK_OWNER_KIND", "discord")

# ------------------------------ helpers ------------------------------

def _conn():
    """Best-effort writer connection to the core DB."""
    for name in ("write_conn", "conn", "_conn", "get_conn"):
        fn = getattr(dal, name, None)
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

    # Fallback: treat Discord user as the owner directly
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
    return [r["name"] for r in con.execute("SELECT name FROM tags").fetchall()]

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
    gsw_name = _canonical_tag_name("Gunshot Wound")
    if not gsw_name:
        await itx.followup.send("❌ `Gunshot Wound` is not in the catalog. Run **/tag_seed** first.", ephemeral=True)
        return

    iid = apply_tag(
        owner_kind=owner_kind,
        owner_id=owner_id,
        anchor_path=anchor_path,
        tag_name=gsw_name,
        stacks=max(1, int(stacks)),
        duration_ms=None,
        source_kind="cmd",
        source_ref="gunshot",
    )

    bleed_name = _canonical_tag_name("Bleeding")
    if bleed_name:
        apply_tag(
            owner_kind=owner_kind,
            owner_id=owner_id,
            anchor_path=anchor_path,
            tag_name=bleed_name,
            stacks=max(1, int(stacks) - 1),
            duration_ms=None,
            source_kind="cmd",
            source_ref="gunshot",
        )

    await itx.followup.send(
        f"🟢 Applied **Gunshot Wound** (sev {stacks}) @ `{anchor_path}` on {target.mention} "
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

        # Quiet chatty modules; player deaths still appear as CRITICAL via playerlog.kill
        for noisy in ("tags.registry", "tags.engine", "health"):
            logging.getLogger(noisy).setLevel(logging.WARNING)

        if _enabled():
            await ENGINE.start()

    async def cog_unload(self):
        if _enabled():
            await ENGINE.stop()

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
        tag_name="Catalog name (e.g., Bleeding)",
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

            canon = _canonical_tag_name(tag_name)
            if not canon:
                suggestions = _suggest_names(tag_name)
                hint = f" Did you mean: {', '.join(f'`{s}`' for s in suggestions)}?" if suggestions else ""
                return await itx.followup.send(f"❌ Tag `{tag_name}` not found in catalog.{hint}", ephemeral=True)

            iid = apply_tag(
                owner_kind=owner_kind,
                owner_id=owner_id,
                anchor_path=anchor_path,
                tag_name=canon,
                stacks=max(1, int(stacks)),
                duration_ms=duration_ms,
                source_kind="cmd",
                source_ref="tag_add",
            )

            await itx.followup.send(
                f"✅ `{canon}` x{stacks} → `{anchor_path}` on {target.mention} "
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

            rows = tag_dal.list_instances(owner_kind, owner_id)
            if not rows:
                return await itx.followup.send("No active tags.", ephemeral=True)

            lines = []
            for r in rows:
                timer = f"⏱ {int(r['tick_ms'])}ms" if r["tick_ms"] else ""
                state = f" · state:`{r['state']}`" if r["state"] else ""
                anchor = r["anchor_path"]
                lines.append(f"- **{r['name']}** x{r['stacks']} @ `{anchor}` {timer}{state}")

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
            n = tag_dal.clear_owner(owner_kind, owner_id)
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
            rows = tag_dal.list_instances(owner_kind, owner_id)

            lines = [f"**HP:** {hp}/{max_hp}  ·  **Owner:** `{owner_kind}:{owner_id}`"]
            if rows:
                for r in rows:
                    timer = f"⏱ {int(r['tick_ms'])}ms" if r["tick_ms"] else ""
                    state = f" · state:`{r['state']}`" if r["state"] else ""
                    anchor = r["anchor_path"]
                    lines.append(f"- **{r['name']}** x{r['stacks']} @ `{anchor}` {timer}{state}")
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

    @app_commands.command(name="tag_seed", description="Seed the tag catalog with defaults (Bleeding, Gunshot Wound)")
    async def tag_seed(self, itx: Interaction):
        # Intentionally available even if TAGS_ENABLED=0 so you can prepare the DB.
        await itx.response.defer(ephemeral=True)
        try:
            ensure_tags_schema()
            inserted, total = _seed_catalog()
            con = tag_dal._conn()
            rows = con.execute("SELECT name, kind, polarity FROM tags ORDER BY name").fetchall()
            lines = [
                f"Seeded {inserted} tag(s). Catalog now has {total} rows.",
                *[f"- **{r['name']}**  ({(r['kind'] or 'dynamic')}{(' · ' + r['polarity']) if r['polarity'] else ''})" for r in rows]
            ]
            await itx.followup.send("\n".join(lines), ephemeral=True)
        except Exception:
            trace = uuid.uuid4().hex[:8]
            log.error("[tag_seed] trace=%s\n%s", trace, traceback.format_exc())
            await itx.followup.send(f"⚠️ Seeding failed. Trace `{trace}`. Check logs.", ephemeral=True)

# ------------------------------ setup --------------------------------

async def setup(bot: commands.Bot):
    await bot.add_cog(TagsCog(bot))
