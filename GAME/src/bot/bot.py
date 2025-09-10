# GAME/src/bot/bot.py
from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import sys
import inspect
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands

from src.core.heartbeat import Heartbeat, HeartbeatConfig

# ---------- boot logging ----------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("discord.gateway").setLevel(logging.ERROR)
log = logging.getLogger("boot")

BUILD_TAG = "bot.py:v6f-full-inspector+module-audit+safe-sync"

# ---------- paths & env ----------
THIS_FILE = Path(__file__).resolve()
SRC_DIR = THIS_FILE.parents[1]   # .../GAME/src
GAME_DIR = THIS_FILE.parents[2]  # .../GAME
REPO_DIR = THIS_FILE.parents[3]  # repo root
for p in (GAME_DIR, SRC_DIR, REPO_DIR):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

# --- settings (after sys.path is set) ---
from src.core.settings import SETTINGS  # noqa: E402

# TEMP: verify token is being read from env correctly
tok = SETTINGS.discord_token or ""
masked = (tok[:8] + "…" + tok[-6:]) if len(tok) > 16 else "(too short)"
log.info("Token loaded (len=%d): %s", len(tok), masked)
if len(tok) < 40 or (" " in tok) or ("\n" in tok) or ("\r" in tok):
    log.error("Token looks malformed. Check GAME/.env DISCORD_TOKEN.")

TOKEN = SETTINGS.discord_token
GUILD_ID = SETTINGS.guild_id

# event helpers (for /inspect_full)
from src.core.events import (  # noqa: E402
    DB_PATH,
    last_event_time,
    list_admin_notes,
    message_count,
    recent_events,
)
from src.core.errors import setup_error_reporting  # noqa: E402

DANGEROUS_PERMS = {
    "administrator",
    "manage_guild",
    "manage_channels",
    "manage_roles",
    "manage_webhooks",
    "kick_members",
    "ban_members",
    "mention_everyone",
    "manage_messages",
    "manage_threads",
    "mute_members",
    "deafen_members",
    "move_members",
    "priority_speaker",
}

try:
    LA_TZ = ZoneInfo("America/Los_Angeles")
except Exception:
    LA_TZ = None

# ---------- small helpers ----------
def _hex_color(v):
    try:
        return f"#{int(v):06X}"
    except Exception:
        return None


def _rel_ymdh(a: datetime | None, b: datetime | None = None) -> str:
    """Rough 'y_m_d_h ago' string (years, months, days, hours)."""
    if not a:
        return "—"
    if b is None:
        b = datetime.now(timezone.utc)
    from calendar import monthrange

    y = b.year - a.year - ((b.month, b.day, b.hour) < (a.month, a.day, a.hour))
    ay = a.replace(year=a.year + y)
    m = (b.year - ay.year) * 12 + b.month - ay.month - (b.day < ay.day)
    ny = ay.year + (ay.month + m - 1) // 12
    nm = (ay.month + m - 1) % 12 + 1
    dmax = monthrange(ny, nm)[1]
    anchor = ay.replace(year=ny, month=nm, day=min(ay.day, dmax))
    delta = b - anchor
    d = delta.days
    h = delta.seconds // 3600

    parts = []
    if y:
        parts.append(f"{y}_years")
    if m:
        parts.append(f"{m}_months")
    if d:
        parts.append(f"{d}_days")
    parts.append(f"{h}_hours")
    return "_".join(parts) + " ago"


def _fmt_ts_local(ts_in) -> str:
    """DD/MM/YY H:MM AM/PM in LA time if available; accepts iso 'Z', seconds, ms, datetime."""
    try:
        if isinstance(ts_in, datetime):
            dt = ts_in
        elif isinstance(ts_in, (int, float)) or (isinstance(ts_in, str) and ts_in.isdigit()):
            val = float(ts_in)
            if val > 1e12:
                val /= 1000.0
            dt = datetime.fromtimestamp(val, tz=timezone.utc)
        elif isinstance(ts_in, str):
            s = ts_in.strip()
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        else:
            return str(ts_in)
        if LA_TZ:
            dt = dt.astimezone(LA_TZ)
        hour = dt.hour
        ampm = "AM" if hour < 12 else "PM"
        h12 = hour % 12 or 12
        return f"{dt.day}/{dt.month}/{dt.year % 100:02d} {h12}:{dt.minute:02d} {ampm}"
    except Exception:
        return str(ts_in)


def _snippet(s: str | None, n: int = 120) -> str:
    if not s:
        return ""
    s = s.replace("\n", " ").strip()
    return (s[:n] + "…") if len(s) > n else s


def _ch_label_from_payload(guild: discord.Guild, d: dict) -> str:
    """Return '#channelname' if found, otherwise <#id> or '—'."""
    cid = d.get("channel_id") or d.get("channel") or d.get("cid")
    if isinstance(cid, dict):
        cid = cid.get("id")
    try:
        cid = int(cid)
    except Exception:
        return "—"
    ch = guild.get_channel(cid)
    return f"#{ch.name}" if ch else f"<#{cid}>"


def _extract_text(d: dict) -> str:
    for k in ("content", "message", "msg", "text", "body"):
        v = d.get(k)
        if isinstance(v, str) and v:
            return v
        if isinstance(v, dict):
            c = v.get("content")
            if isinstance(c, str) and c:
                return c
    return ""


def _is_trusted(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    try:
        from src.core.perm import user_role, Role
        return user_role(member) in (Role.ADMIN, Role.MOD)
    except Exception:
        return False


# ---------- Global gate via CommandTree ----------
class LowlifeTree(app_commands.CommandTree):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """
        Global gate: block frozen accounts before any slash command runs.
        Uses the same DB path as the custodian_cog for consistency.
        """
        try:
            import sqlite3
            dbp = Path(__file__).parents[2] / "db" / "audit.sqlite"
            with sqlite3.connect(dbp) as conn:
                row = conn.execute(
                    "SELECT reason FROM account_freeze WHERE user_id=?",
                    (str(getattr(interaction.user, "id", "")),),
                ).fetchone()
            if row:
                msg = f"🚫 Your account is temporarily frozen: **{row[0]}**"
                if not interaction.response.is_done():
                    await interaction.response.send_message(msg, ephemeral=True)
                else:
                    await interaction.followup.send(msg, ephemeral=True)
                return False
        except Exception:
            # fail open; do not block commands on DB hiccups
            pass
        return True


# ---------- Bot ----------
class LowlifeBot(commands.Bot):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._heartbeat: Heartbeat | None = None
        self._bootstrap_synced: bool = False

    async def setup_hook(self):
        # global crash/error capture
        setup_error_reporting(self)

        # --- Custodian schema on boot ---
        try:
            from src.db.custodian_dal import ensure_custodian_schema
            ensure_custodian_schema()
            log.info("custodian schema ensured")
        except Exception:
            log.exception("custodian schema init failed")

        try:
            from src.db.dal import ensure_events_schema
            ensure_events_schema()
            log.info("events schema ensured")
        except Exception as e:
            log.warning("events schema ensure failed: %s", e)

            from src.db.auto_migrate import ensure_all as ensure_auto_migrations
            ensure_auto_migrations()
            log.info("auto migrations ensured")
        
            try:
                from src.db.auto_migrate import ensure_all as ensure_auto_migrations
                ensure_auto_migrations()
                log.info("auto migrations ensured")
            except Exception as e:
                log.warning("auto migrations failed: %s", e)

        # ---- Resolve ONLY the audit_event decorator via module import (robust) ----
        try:
            from src.core import audit as _audit_mod
            audit_event = getattr(_audit_mod, "audit_event")
        except Exception as e:
            log.warning("audit decorator unavailable (%s) — using no-op.", e)

            def audit_event(*_a, **_k):  # type: ignore
                def deco(fn):
                    return fn
                return deco

        # Base cogs to load
        COGS = [
            "src.cogs.activity_logger",
            "src.cogs.admin_inspector",
            "src.cogs.analytics",
            "src.cogs.audit_log",
            "src.cogs.invite_tracker",
            "src.cogs.member_intake",
            "src.cogs.welcome",
            "src.cogs.duel",
            "src.cogs.inventory",
            "src.cogs.admin_tools",
            "src.cogs.health",
            "src.cogs.suggestions",
            "src.cogs.admin_items",
            "src.cogs.item_magazine",
            "src.cogs.onboarding",
            "src.cogs.profile",
            "src.cogs.admin_backfill",
            "src.cogs.heartbeat_taps",
            "src.cogs.tags",

        ]

        async def try_load(module: str):
            try:
                await self.load_extension(module)
                log.info("loaded extension: %s", module)
            except Exception:
                log.exception("failed to load %s", module)

        for module in COGS:
            await try_load(module)

        # Extra/feature/admin cogs (best-effort)
        for module in (
            "src.cogs.events",
            "src.admin.sync",
            "src.admin.export",
            "src.admin.audit",
            "src.admin.custodian_cog",
            "src.admin.custodian_detectors",
            "src.admin.custodian_anchor",
            "src.admin.freeze",
            "src.admin.econ",
            "src.admin.roles",
            "src.admin.backup",
            "src.cogs.event_listener",
            "src.admin.investigate",
            "src.admin.events_viewer",
        ):
            await try_load(module)

        # ---------- HEARTBEAT ----------
        try:
            cfg = HeartbeatConfig(interval_s=0.5, log_every_n=12, label="LOWLIFE")
            self._heartbeat = Heartbeat(cfg)
            await self._heartbeat.start()
            log.info("heartbeat started")
        except Exception:
            log.exception("failed to start heartbeat")

        # ---------- Ensure /hb is registered ----------
        try:
            hb_cog = self.get_cog("HeartbeatTaps")
            if hb_cog and hasattr(hb_cog, "hb"):
                try:
                    self.tree.add_command(hb_cog.hb)
                except Exception as e:
                    if "already registered" not in str(e).lower():
                        log.warning("add_command(global, /hb) failed: %s", e)
                if GUILD_ID:
                    try:
                        self.tree.add_command(hb_cog.hb, guild=discord.Object(id=GUILD_ID))
                    except Exception as e:
                        if "already registered" not in str(e).lower():
                            log.warning("add_command(guild, /hb) failed: %s", e)
            else:
                log.warning("HeartbeatTaps cog not found; /hb not registered.")
        except Exception:
            log.exception("failed to register /hb")

        # --- /inspect_full (admin) ---
        @app_commands.command(
            name="inspect_full",
            description="Admin: full profile with derived stats and recent actions",
        )
        @app_commands.describe(user="Target member (defaults to you)")
        @audit_event(
            action_type="admin.inspect",
            target_user=lambda interaction, user=None: user,
            extra=lambda interaction, user=None: {"scope": "full_profile"},
        )
        async def inspect_full(
            interaction: discord.Interaction, user: discord.Member | None = None
        ):
            if not (
                isinstance(interaction.user, discord.Member)
                and interaction.user.guild_permissions.administrator
            ):
                await interaction.response.send_message("Nope.", ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True, thinking=True)

            member: discord.Member = user or interaction.user  # type: ignore
            created = member.created_at
            joined = member.joined_at

            avatar_url = member.display_avatar.url if member.display_avatar else None
            banner_url = None
            try:
                u = await interaction.client.fetch_user(member.id)  # type: ignore
                if getattr(u, "banner", None):
                    banner_url = u.banner.url
            except Exception:
                pass

            roles_sorted = [
                r for r in sorted(member.roles, key=lambda r: r.position) if r.name != "@everyone"
            ]
            top3 = [r.name for r in roles_sorted[-3:]] if roles_sorted else []
            risky = []
            for name, allowed in member.guild_permissions:
                if allowed and name in DANGEROUS_PERMS:
                    risky.append(name)
                if len(risky) >= 5:
                    break

            status = str(getattr(member, "status", "offline"))
            dev = {
                "desktop": str(getattr(member, "desktop_status", "offline")),
                "mobile": str(getattr(member, "mobile_status", "offline")),
                "web": str(getattr(member, "web_status", "offline")),
            }
            activities = []
            try:
                for a in getattr(member, "activities", []) or []:
                    if getattr(a, "name", None):
                        activities.append(getattr(a, "name"))
                    elif getattr(a, "state", None):
                        activities.append(a.state)
            except Exception:
                pass

            timeout_until = getattr(member, "communication_disabled_until", None) or getattr(
                member, "timed_out_until", None
            )
            premium_since = getattr(member, "premium_since", None)
            pending = getattr(member, "pending", None)

            last_acted_raw = last_event_time(member.id)
            last_acted_pretty = _fmt_ts_local(last_acted_raw) if last_acted_raw else "—"

            badges = []
            try:
                badges = [getattr(b, "name", str(b)) for b in member.public_flags.all()]
            except Exception:
                pass
            accent = getattr(member, "accent_color", None)
            accent_val = getattr(accent, "value", None)

            msg7 = message_count(member.id, 7, interaction.guild.id)  # type: ignore
            msg30 = message_count(member.id, 30, interaction.guild.id)  # type: ignore

            notes = list_admin_notes(interaction.guild.id, member.id, 2)  # type: ignore
            notes_lines = (
                [f"`{ts}` — <@{aid}> — {note}" for (_nid, ts, aid, note) in notes] if notes else []
            )

            header = "\n".join(
                [
                    f"{member.mention} --",
                    f"ID -- `{member.id}`",
                    f"Account Created -- `{created.isoformat().replace('+00:00','Z') if created else '—'}` ({_rel_ymdh(created)})",
                    f"Joined Guild -- `{joined.isoformat().replace('+00:00','Z') if joined else '—'}` ({_rel_ymdh(joined)})",
                ]
            )

            e = discord.Embed(
                title="🛠️ Admin Inspector — Full Profile",
                description=header,
                colour=discord.Color.blurple(),
            )
            if avatar_url:
                e.set_thumbnail(url=avatar_url)
            if banner_url:
                e.set_image(url=banner_url)

            e.add_field(
                name="Status / Devices",
                value=f"Current Status: {status} <{last_acted_pretty}>\n"
                f"🖥 {dev['desktop']}\n📱 {dev['mobile']}\n🌐 {dev['web']}",
                inline=False,
            )
            if activities:
                e.add_field(name="Activities", value="; ".join(activities)[:1024], inline=False)

            e.add_field(name="Top Roles", value=(", ".join(top3) or "—"), inline=False)
            e.add_field(
                name="⚠️ High-Risk Perms (top 5)", value=(", ".join(risky) or "—"), inline=False
            )

            trusted = _is_trusted(member)
            e.add_field(name="Trusted", value=("Yes ✅" if trusted else "No ❌"), inline=True)
            e.add_field(name="Accent", value=f"`{_hex_color(accent_val) or '—'}`", inline=True)

            if premium_since:
                e.add_field(
                    name="Boosting Since",
                    value=f"`{premium_since.isoformat().replace('+00:00','Z')}`",
                    inline=True,
                )
            if pending is not None:
                e.add_field(
                    name="Passed Screening",
                    value=("Yes" if not pending else "Pending"),
                    inline=True,
                )
            if timeout_until:
                e.add_field(
                    name="Timeout Until",
                    value=f"`{timeout_until.isoformat().replace('+00:00','Z')}`",
                    inline=True,
                )

            e.add_field(name="Badges", value=(", ".join(badges) or "—")[:1024], inline=False)
            e.add_field(name="Msg Counts", value=f"7d: `{msg7}` • 30d: `{msg30}`", inline=True)
            e.add_field(name="Log DB", value=f"`{str(DB_PATH)}`", inline=True)

            # recent actions (from your compact events table)
            try:
                recents = recent_events(member.id, 50, interaction.guild.id)  # type: ignore[attr-defined]
            except TypeError:
                recents = recent_events(member.id, 50)

            def _recent_line(ts, kind, data):
                ch = _ch_label_from_payload(interaction.guild, data) if interaction.guild else "—"  # type: ignore
                txt = _snippet(_extract_text(data))

                if kind == "message":
                    prefix = "Msg";  body = txt or "—"
                elif kind == "message_edit":
                    prefix = "Edit"; body = txt or (data.get("after") or {}).get("content") or "—"
                elif kind == "message_delete":
                    prefix = "Del";  body = txt or (data.get("before") or {}).get("content") or "unknown"
                elif kind == "message_bulk_delete":
                    prefix = f"BulkDel x{data.get('count', 0)}"
                    cached = data.get("cached_with_text", 0)
                    body = f"{cached} with text" if cached else ""
                elif kind == "presence":
                    prefix = "Presence"
                    body = data.get("text")
                    if not body:
                        sb = str(data.get("status_before") or data.get("before") or "").strip()
                        sa = str(data.get("status_after") or data.get("after") or "").strip()

                        after_snap = data.get("after") if isinstance(data.get("after"), dict) else {}
                        devbits = []
                        desk = str(after_snap.get("desktop") or "").strip()
                        mob = str(after_snap.get("mobile") or "").strip()
                        web = str(after_snap.get("web") or "").strip()
                        if desk and desk.lower() != "offline":
                            devbits.append(f"🖥 {desk}")
                        if mob and mob.lower() != "offline":
                            devbits.append(f"📱 {mob}")
                        if web and web.lower() != "offline":
                            devbits.append(f"🌐 {web}")
                        acts = after_snap.get("activities") or []
                        act_txt = ", ".join([str(a) for a in acts][:2])

                        parts = []
                        if sb or sa:
                            parts.append(f"{sb or '—'} → {sa or '—'}")
                        tail = " • ".join([p for p in (" | ".join(devbits) if devbits else "", act_txt) if p])
                        if tail:
                            parts.append(tail)
                        body = " — ".join(parts) if parts else ""
                else:
                    prefix = kind.replace("_", " ").title()
                    body = txt or ""

                return f"{_fmt_ts_local(ts)}  {prefix}@{ch} - {body or '—'}"

            pretty = []
            for row in recents[:20]:
                if len(row) >= 4:
                    _, ts, kind, payload = row[0], row[1], row[2], row[3]
                elif len(row) >= 3:
                    ts, kind, payload = row[0], row[1], row[2]
                else:
                    ts, kind, payload = row[0], (row[1] if len(row) > 1 else "event"), (row[2] if len(row) > 2 else "{}")
                try:
                    data = json.loads(payload or "{}") if isinstance(payload, (str, bytes)) else (payload or {})
                except Exception:
                    data = {}
                line = _recent_line(ts, kind, data)
                if len(line) > 120:
                    line = line[:117] + "…"
                pretty.append(line)

            out = "\n".join(pretty) if pretty else "None recorded yet — start chatting to populate this!"
            while len(out) > 1024 and len(pretty) > 1:
                pretty.pop()
                out = "\n".join(pretty)

            e.add_field(name="Recent Actions", value=out, inline=False)
            e.set_footer(text=f"{BUILD_TAG} — Use /note_list to view all, /note_add to add, /note_delete to remove")

            s = io.StringIO()
            w = csv.writer(s)
            w.writerow(["ts_utc", "kind", "payload"])
            for ts, kind, payload in recents:
                w.writerow([ts, kind, payload])
            f = discord.File(io.BytesIO(s.getvalue().encode("utf-8")), filename=f"recent_actions_{member.id}.csv")
            await interaction.followup.send(embed=e, file=f, ephemeral=True)

        # ----- register & SYNC with safe guild handling -----
        async def register_and_sync():
            try:
                self.tree.add_command(inspect_full)
            except Exception as e:
                if "already registered" not in str(e).lower():
                    log.warning("add_command(global,inspect_full) failed: %s", e)

            # debug inventory
            try:
                all_cmds = list(self.tree.get_commands())
                log.info("pre-sync: tree has %d top-level commands", len(all_cmds))
                for top in all_cmds:
                    qname = getattr(top, "qualified_name", getattr(top, "name", "?"))
                    log.info("pre-sync: /%s", qname)
            except Exception as e:
                log.warning("pre-sync inventory failed: %s", e)

            guild_added = False
            target_guild = None
            if GUILD_ID:
                target_guild = self.get_guild(GUILD_ID)
                if target_guild:
                    gobj = discord.Object(id=GUILD_ID)
                    try:
                        self.tree.add_command(inspect_full, guild=gobj)
                        guild_added = True
                    except Exception as e:
                        if "already registered" not in str(e).lower():
                            log.warning("add_command(guild,inspect_full) failed: %s", e)

            g_count = "n/a"
            try:
                gcmds = await self.tree.sync()
                g_count = str(len(gcmds))
            except Exception as e:
                log.warning("Global sync failed: %s", e)

            if GUILD_ID and guild_added and target_guild:
                try:
                    gcmds = await self.tree.sync(guild=discord.Object(id=GUILD_ID))
                    log.info("startup sync — Guild: %d • Global: %s", len(gcmds), g_count)
                    log.info("slash commands guild-synced: %d cmds to %s", len(gcmds), GUILD_ID)
                except Exception as e:
                    log.warning("Guild sync failed for %s (%s).", GUILD_ID, e)
                    log.info("startup sync — Guild: failed • Global: %s", g_count)
            else:
                log.info(
                    "startup sync — Guild: skipped (%s) • Global: %s",
                    ("not in guild" if GUILD_ID else "no GUILD_ID"),
                    g_count,
                )

            # Inventory: list what got registered (walk groups safely)
            def _log_cmd(c: app_commands.Command | app_commands.ContextMenu | app_commands.Group):
                qname = getattr(c, "qualified_name", getattr(c, "name", "?"))
                cb = getattr(c, "callback", None)
                mod = getattr(cb, "__module__", getattr(c, "__module__", "?"))
                log.info("slash cmd: /%s from %s", qname, mod)

            for top in self.tree.get_commands():
                if isinstance(top, app_commands.Group):
                    for sub in top.walk_commands():
                        _log_cmd(sub)
                else:
                    _log_cmd(top)

        await register_and_sync()

    async def _bootstrap_sync_once(self):
        """
        One-time emergency sync to break the 'guarded sync' deadlock.
        We call the ORIGINAL (unwrapped) CommandTree.sync directly, bypassing admin.sync's guard.
        """
        if self._bootstrap_synced:
            return
        self._bootstrap_synced = True

        # obtain the original (unwrapped) function object
        try:
            orig_sync_fn = inspect.unwrap(app_commands.CommandTree.sync)
            bound_sync = orig_sync_fn.__get__(self.tree, app_commands.CommandTree)

            # Global sync
            try:
                gcmds = await bound_sync()
                log.info("bootstrap sync (unwrapped): global ok — %d cmds", len(gcmds))
            except Exception as e:
                log.warning("bootstrap sync (unwrapped): global sync failed: %s", e)

            # Guild sync
            if GUILD_ID:
                try:
                    gcmds = await bound_sync(guild=discord.Object(id=GUILD_ID))
                    log.info("bootstrap sync (unwrapped): guild ok — %d cmds to %s", len(gcmds), GUILD_ID)
                except Exception as e:
                    log.warning("bootstrap sync (unwrapped): guild sync failed: %s", e)
        except Exception:
            log.exception("bootstrap sync (unwrapped) failed completely")

    async def on_ready(self):
        log.info("Logged in as %s (%s) — %s", self.user, getattr(self.user, "id", "?"), BUILD_TAG)
        await self._bootstrap_sync_once()

    # ---------- HEARTBEAT: graceful shutdown ----------
    async def close(self):
        try:
            if self._heartbeat:
                await self._heartbeat.stop()
                log.info("heartbeat stopped")
        finally:
            await super().close()


def build_bot() -> LowlifeBot:
    intents = discord.Intents.default()
    intents.guilds = True
    intents.members = True         # required for on_member_join
    intents.presences = True
    intents.message_content = True
    return LowlifeBot(command_prefix="!", intents=intents, tree_cls=LowlifeTree)


async def main():
    if not TOKEN:
        log.error("Missing DISCORD_TOKEN in .env. Put it in GAME\\.env or repo .env.")
        return
    bot = build_bot()
    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
