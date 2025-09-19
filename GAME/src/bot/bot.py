# GAME/src/bot/bot.py
from __future__ import annotations

# -------- UTF-8 HARDENING (do this before any logging/imports that print) --------
import os, sys
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# --- Feature flags (simple on/off switch for Tag system) ---
FEATURE_TAGS = os.getenv("FEATURE_TAGS", "1") == "1"

# --------------------------------------------------------------------------------

import asyncio
import csv
import io
import json
import logging
import inspect
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands

from src.core.heartbeat import Heartbeat, HeartbeatConfig

# ---------- logging (explicit UTF-8 handlers) ----------
THIS_FILE = Path(__file__).resolve()
SRC_DIR = THIS_FILE.parents[1]   # .../GAME/src
GAME_DIR = THIS_FILE.parents[2]  # .../GAME
REPO_DIR = THIS_FILE.parents[3]  # repo root

LOG_DIR = GAME_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

root = logging.getLogger()
for h in list(root.handlers):
    root.removeHandler(h)

console = logging.StreamHandler(sys.stdout)  # stdout is UTF-8 now
fileh   = logging.FileHandler(LOG_DIR / "lowlife.log", encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[console, fileh],
    force=True,
)

# Quiet very chatty loggers
logging.getLogger("discord.gateway").setLevel(logging.ERROR)
log = logging.getLogger("boot")

BUILD_TAG = "bot.py:v6k-utf8-guard+http-scrub+all-senders"

# ---------- paths & env ----------
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

# ---- Try the deep guard early (it may add its own wrappers) ----
try:
    from src.utils.utf8_guard import install_utf8_guard
    install_utf8_guard(logger=log)
    log.info("utf8 deep-guard installed")
    _DEEP_GUARD_OK = True
except Exception:
    log.exception("failed to install utf8 deep-guard")
    _DEEP_GUARD_OK = False

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


# ---------- Encoding helpers ----------
def demojibake(s: str | None) -> str:
    """If text went through UTF-8→CP1252 mojibake (â€” / ðŸ…), try to recover."""
    if not s:
        return ""
    # Fast exit if clearly clean ASCII
    if all(ord(ch) < 128 for ch in s):
        return s

    # Heuristic: if it *looks* baked, attempt repairs (cp1252 and latin1)
    # Markers cover lines like â”€â”€â”€, ðŸ•, Iâ€™ll, âœ…
    markers = ("Ã", "Â", "â", "ð", "�", "”", "€", "™")
    if not any(m in s for m in markers):
        # Still normalize NBSP and friends
        return s.replace("\u00A0", " ")

    def _one(x: str) -> str:
        try:
            return x.encode("cp1252").decode("utf-8")
        except Exception:
            try:
                return x.encode("latin1").decode("utf-8")
            except Exception:
                return x

    prev = s
    for _ in range(3):  # triple-pass to unwind doubles like Ã¢â‚¬â„¢
        fixed = _one(prev)
        if fixed == prev:
            break
        prev = fixed
    return prev.replace("\u00A0", " ")


# ---------- small helpers ----------
def _hex_color(v):
    try:
        return f"#{int(v):06X}"
    except Exception:
        return None


def _rel_ymdh(a: datetime | None, b: datetime | None = None) -> str:
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
    if y: parts.append(f"{y}_years")
    if m: parts.append(f"{m}_months")
    if d: parts.append(f"{d}_days")
    parts.append(f"{h}_hours")
    return "_".join(parts) + " ago"


def _fmt_ts_local(ts_in) -> str:
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
    s = demojibake(s).replace("\n", " ").strip()
    return (s[:n] + "…") if len(s) > n else s


def _ch_label_from_payload(guild: discord.Guild, d: dict) -> str:
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
            return demojibake(v)
        if isinstance(v, dict):
            c = v.get("content")
            if isinstance(c, str) and c:
                return demojibake(c)
    return ""


def _is_trusted(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    try:
        from src.core.perm import user_role, Role
        return user_role(member) in (Role.ADMIN, Role.MOD)
    except Exception:
        return False


# =============== Always-on cp1252/latin1 → UTF-8 repair layer ==================
def _utf8_clean(s: str | None) -> str | None:
    if not isinstance(s, str) or not s:
        return s
    # normalize NBSP quickly
    s = s.replace("\u00A0", " ")
    # try deep de-mojibake if it looks baked
    return demojibake(s)

def _clean_embed(e: discord.Embed | None) -> discord.Embed | None:
    if not isinstance(e, discord.Embed):
        return e
    if e.title:
        e.title = _utf8_clean(e.title) or ""
    if e.description:
        e.description = _utf8_clean(e.description) or ""
    for i, f in enumerate(list(e.fields)):
        e.set_field_at(i,
            name=_utf8_clean(f.name) or "",
            value=_utf8_clean(f.value) or "",
            inline=f.inline,
        )
    try:
        ft = getattr(e.footer, "text", None)
        if ft:
            e.set_footer(text=_utf8_clean(ft) or "", icon_url=getattr(e.footer, "icon_url", discord.Embed.Empty))
    except Exception:
        pass
    try:
        an = getattr(e.author, "name", None)
        if an:
            e.set_author(name=_utf8_clean(an) or "", icon_url=getattr(e.author, "icon_url", discord.Embed.Empty))
    except Exception:
        pass
    return e

def _clean_args_kwargs(args, kwargs):
    # positional content (Messageable.send allows content as first arg)
    if args and isinstance(args[0], str):
        args = list(args)
        args[0] = _utf8_clean(args[0])
    if "content" in kwargs and isinstance(kwargs["content"], str):
        kwargs["content"] = _utf8_clean(kwargs["content"])
    if "embed" in kwargs and kwargs["embed"]:
        kwargs["embed"] = _clean_embed(kwargs["embed"])
    if "embeds" in kwargs and kwargs["embeds"]:
        kwargs["embeds"] = [_clean_embed(e) for e in kwargs["embeds"]]
    # also sanitize allowed_mentions.parse strings just in case
    if "allowed_mentions" in kwargs:
        am = kwargs["allowed_mentions"]
        try:
            if hasattr(am, "to_dict"):
                d = am.to_dict()
                for k, v in list(d.items()):
                    if isinstance(v, str):
                        d[k] = _utf8_clean(v)
                kwargs["allowed_mentions"] = discord.AllowedMentions(**{k: v for k, v in d.items() if k in {"everyone","users","roles","replied_user"}})
        except Exception:
            pass
    return args, kwargs

def _wrap_once(obj, attr, tag):
    """Wrap obj.attr only once; tag marks the function."""
    try:
        orig = getattr(obj, attr)
        if getattr(orig, "__utf8_wrap_tag__", None) == tag:
            return
        async def wrapper(*args, **kwargs):
            a, k = _clean_args_kwargs(args, kwargs)
            return await orig(*a, **k)
        wrapper.__utf8_wrap_tag__ = tag  # type: ignore[attr-defined]
        setattr(obj, attr, wrapper)
    except Exception:
        log.exception("utf8 wrap failed for %s.%s", getattr(obj, "__name__", obj), attr)

def install_cp1252_repair_layer():
    # Interaction first reply / edit
    _wrap_once(discord.InteractionResponse, "send_message", "utf8_fix")
    _wrap_once(discord.InteractionResponse, "edit_message",  "utf8_fix")
    _wrap_once(discord.Interaction,          "edit_original_response", "utf8_fix")
    # Webhook followups (ephemeral/non-ephemeral) & edits
    try:
        from discord.webhook.async_ import Webhook
        _wrap_once(Webhook, "send",         "utf8_fix")
        _wrap_once(Webhook, "edit_message", "utf8_fix")
    except Exception:
        log.exception("utf8 wrap for Webhook failed")
    # ctx.send / channel.send / reply
    _wrap_once(discord.abc.Messageable, "send", "utf8_fix")
    try:
        _wrap_once(discord.Message, "reply", "utf8_fix")
    except Exception:
        pass
    # message.edit
    _wrap_once(discord.Message, "edit", "utf8_fix")
    log.info("utf8 cp1252-repair layer active")

# ===============================================================================
# =============== HTTP JSON UTF-8 scrub (deep clean right before send) ==========
from discord.http import HTTPClient

def _scrub_json(obj):
    if obj is None:
        return None
    if isinstance(obj, str):
        return demojibake(obj)
    if isinstance(obj, list):
        return [_scrub_json(x) for x in obj]
    if isinstance(obj, tuple):
        return tuple(_scrub_json(x) for x in obj)
    if isinstance(obj, dict):
        return {k: _scrub_json(v) for k, v in obj.items()}
    return obj

_HTTP_request_orig = HTTPClient.request
async def _HTTP_request_scrubbed(self, route, **kwargs):
    if "json" in kwargs and kwargs["json"] is not None:
        kwargs["json"] = _scrub_json(kwargs["json"])
    # ensure aiohttp doesn't try to ascii-escape
    kwargs.setdefault("headers", {})
    if isinstance(kwargs["headers"], dict):
        if "Content-Type" not in kwargs["headers"]:
            kwargs["headers"]["Content-Type"] = "application/json; charset=utf-8"
    return await _HTTP_request_orig(self, route, **kwargs)

HTTPClient.request = _HTTP_request_scrubbed  # type: ignore[attr-defined]
logging.getLogger("boot").info("http json utf8 scrub installed")
# ===============================================================================


# ---------- Global gate via CommandTree ----------
class LowlifeTree(app_commands.CommandTree):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        try:
            import sqlite3
            dbp = Path(__file__).parents[2] / "db" / "audit.sqlite"
            with sqlite3.connect(dbp) as conn:
                row = conn.execute(
                    "SELECT reason FROM account_freeze WHERE user_id=?",
                    (str(getattr(interaction.user, "id", "")),),
                ).fetchone()
            if row:
                msg = f"🚫 Your account is temporarily frozen: **{demojibake(row[0])}**"
                if not interaction.response.is_done():
                    await interaction.response.send_message(msg, ephemeral=True)
                else:
                    await interaction.followup.send(msg, ephemeral=True)
                return False
        except Exception:
            pass
        return True


# ---------- Bot ----------
class LowlifeBot(commands.Bot):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._heartbeat: Heartbeat | None = None
        self._bootstrap_synced: bool = False

    async def setup_hook(self):
        setup_error_reporting(self)

        # Always install our cp1252 repair layer (even if deep guard was OK)
        try:
            install_cp1252_repair_layer()
        except Exception:
            log.exception("failed to install cp1252 repair layer")

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
            try:
                from src.db.auto_migrate import ensure_all as ensure_auto_migrations
                ensure_auto_migrations()
                log.info("auto migrations ensured")
            except Exception as e2:
                log.warning("auto migrations failed: %s", e2)

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

        # ----------------------------- COG LOADING -----------------------------
        async def try_load(module: str):
            try:
                await self.load_extension(module)
                log.info("loaded extension: %s", module)
            except Exception:
                log.exception("failed to load %s", module)

        feature_tags_on = os.getenv("FEATURE_TAGS", "1") == "1"

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
            "src.cogs.playerlog",
        ]
        if feature_tags_on:
            COGS += ["src.cogs.tags", "src.cogs.tags_admin"]

        for module in COGS:
            await try_load(module)

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
                [f"`{ts}` — <@{aid}> — {demojibake(note)}" for (_nid, ts, aid, note) in notes]
                if notes else []
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
                      f"🖥️ {dev['desktop']}\n📱 {dev['mobile']}\n🌐 {dev['web']}",
                inline=False,
            )
            if activities:
                e.add_field(name="Activities", value="; ".join(activities)[:1024], inline=False)

            e.add_field(name="Top Roles", value=(", ".join(top3) or "—"), inline=False)
            e.add_field(
                name="⚠️ High-Risk Perms (top 5)",
                value=(", ".join(risky) or "—"),
                inline=False,
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
                    prefix = "Edit"; body = txt or demojibake((data.get("after") or {}).get("content") or "—")
                elif kind == "message_delete":
                    prefix = "Del";  body = txt or demojibake((data.get("before") or {}).get("content") or "unknown")
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
                        if desk and desk.lower() != "offline": devbits.append("🖥️ " + desk)
                        if mob and mob.lower() != "offline":  devbits.append("📱 " + mob)
                        if web and web.lower() != "offline":  devbits.append("🌐 " + web)
                        acts = after_snap.get("activities") or []
                        act_txt = ", ".join([str(a) for a in acts][:2])
                        parts = []
                        if sb or sa: parts.append(f"{sb or '—'} → {sa or '—'}")
                        tail = " • ".join([p for p in (" | ".join(devbits) if devbits else "", act_txt) if p])
                        if tail: parts.append(tail)
                        body = " — ".join(parts) if parts else ""
                else:
                    prefix = kind.replace("_", " ").title()
                    body = txt or ""
                return f"{_fmt_ts_local(ts)}  {prefix}@{ch} - {demojibake(body) or '—'}"

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
            await interaction.followup.send(embed=_clean_embed(e), file=f, ephemeral=True)

        # ----- register & SYNC with safe guild handling -----
        async def register_and_sync():
            try:
                self.tree.add_command(inspect_full)
            except Exception as e:
                if "already registered" not in str(e).lower():
                    log.warning("add_command(global,inspect_full) failed: %s", e)

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
        if self._bootstrap_synced:
            return
        self._bootstrap_synced = True
        try:
            orig_sync_fn = inspect.unwrap(app_commands.CommandTree.sync)
            bound_sync = orig_sync_fn.__get__(self.tree, app_commands.CommandTree)
            try:
                gcmds = await bound_sync()
                log.info("bootstrap sync (unwrapped): global ok — %d cmds", len(gcmds))
            except Exception as e:
                log.warning("bootstrap sync (unwrapped): global sync failed: %s", e)
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
    intents.members = True
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
