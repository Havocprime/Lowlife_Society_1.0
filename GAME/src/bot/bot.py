from __future__ import annotations

import os, sys, asyncio, logging, io, csv, json, importlib
from pathlib import Path
from datetime import datetime, timezone

import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from zoneinfo import ZoneInfo

BUILD_TAG = "bot.py:v4-inspect_full-and-cmd-origin-log"

# ---------- paths & env ----------
THIS_FILE = Path(__file__).resolve()
SRC_DIR   = THIS_FILE.parents[1]   # .../GAME/src
GAME_DIR  = THIS_FILE.parents[2]   # .../GAME
REPO_DIR  = THIS_FILE.parents[3]   # repo root
for p in (GAME_DIR, SRC_DIR, REPO_DIR):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

# --- settings ---
from src.core.settings import SETTINGS
TOKEN    = SETTINGS.discord_token
GUILD_ID = SETTINGS.guild_id


# ✅ import AFTER sys.path is set
from src.core.audit import ensure_db, audit_event
from src.core.events import (
    recent_events, last_event_time, DB_PATH,
    message_count, list_admin_notes
)

COGS = [
    "src.cogs.activity_logger",
    "src.cogs.admin_inspector",
    "src.cogs.admin_notes",
    "src.cogs.analytics",
    "src.cogs.audit_log",
    "src.cogs.invite_tracker",
    "src.cogs.member_intake",
]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("boot")
log.info("Starting %s", BUILD_TAG)

DANGEROUS_PERMS = {
    "administrator","manage_guild","manage_channels","manage_roles","manage_webhooks",
    "kick_members","ban_members","mention_everyone","manage_messages","manage_threads",
    "mute_members","deafen_members","move_members","priority_speaker"
}

def _hex_color(v):
    try: return f"#{int(v):06X}"
    except Exception: return None

def _rel_ymdh(a: datetime | None, b: datetime | None = None) -> str:
    if not a: return "—"
    if b is None: b = datetime.now(timezone.utc)
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

try:
    LA_TZ = ZoneInfo("America/Los_Angeles")
except Exception:
    LA_TZ = None

def _fmt_ts_local(ts_in) -> str:
    """DD/MM/YYYY H:MM AM/PM in LA time if available; accepts iso 'Z', seconds, ms, datetime."""
    try:
        if isinstance(ts_in, datetime):
            dt = ts_in
        elif isinstance(ts_in, (int, float)) or (isinstance(ts_in, str) and ts_in.isdigit()):
            val = float(ts_in)
            if val > 1e12: val /= 1000.0
            dt = datetime.fromtimestamp(val, tz=timezone.utc)
        elif isinstance(ts_in, str):
            s = ts_in.strip()
            if s.endswith("Z"): s = s[:-1] + "+00:00"
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        else:
            return str(ts_in)
        if LA_TZ: dt = dt.astimezone(LA_TZ)
        hour = dt.hour
        ampm = "AM" if hour < 12 else "PM"
        h12  = hour % 12 or 12
        return f"{dt.day}/{dt.month}/{dt.year % 100:02d} {h12}:{dt.minute:02d} {ampm}"

    except Exception:
        return str(ts_in)

def _is_trusted(member: discord.Member) -> bool:
    if member.guild_permissions.administrator: return True
    if ADMIN_ROLE_ID and any(r.id == ADMIN_ROLE_ID for r in member.roles): return True
    if TRUSTED_ROLE_IDS and any(r.id in TRUSTED_ROLE_IDS for r in member.roles): return True
    if TRUSTED_ROLE_NAMES and any(r.name.lower() in TRUSTED_ROLE_NAMES for r in member.roles): return True
    return False

def _snippet(s: str | None, n: int = 120) -> str:
    if not s: return ""
    s = s.replace("\n", " ").strip()
    return (s[:n] + "…") if len(s) > n else s

def _to_int(x):
    try: return int(x)
    except Exception: return None

def _ch_mention_from_payload(guild: discord.Guild, d: dict) -> str:
    cid = d.get("channel_id") or d.get("channel") or d.get("cid")
    if isinstance(cid, dict): cid = cid.get("id")
    cid = _to_int(cid)
    if not cid: return "—"
    ch = guild.get_channel(cid)
    return ch.mention if ch else f"<#{cid}>"

def _ch_label_from_payload(guild: discord.Guild, d: dict) -> str:
    """Return '#channelname' if found, otherwise <#id> or '—'."""
    cid = d.get("channel_id") or d.get("channel") or d.get("cid")
    if isinstance(cid, dict):
        cid = cid.get("id")
    cid = _to_int(cid)
    if not cid:
        return "—"
    ch = guild.get_channel(cid)
    return f"#{ch.name}" if ch else f"<#{cid}>"

def _extract_text(d: dict) -> str:
    for k in ("content", "message", "msg", "text", "body"):
        v = d.get(k)
        if isinstance(v, str) and v: return v
        if isinstance(v, dict):
            c = v.get("content")
            if isinstance(c, str) and c: return c
    return ""

def _role_mentions(guild: discord.Guild, ids: list[str] | list[int] | None) -> str:
    if not ids: return "—"
    out = []
    for rid in ids:
        rid_i = _to_int(rid)
        if rid_i is None:
            out.append(f"`{rid}`"); continue
        r = guild.get_role(rid_i)
        out.append(r.mention if r else f"`{rid_i}`")
    return ", ".join(out) if out else "—"

class LowlifeBot(commands.Bot):
    async def setup_hook(self):
        # Ensure audit DB/schema
        try:
            res = ensure_db()
            if asyncio.iscoroutine(res): await res
            log.info("audit DB ready")
        except Exception:
            log.exception("audit DB init failed")

        async def setup_hook(self):
            # ... your other loads ...
            await self.load_extension("src.cogs.events")
            await self.load_extension("src.features.character_sheet.commands")


        async def try_load(mod: str):
            try:
                await self.load_extension(mod)
                log.info("loaded extension: %s", mod)
            except Exception:
                log.exception("failed to load %s", mod)

        for mod in COGS:
            await try_load(mod)

        # --- register notes group into the active scope (robust) ---
        try:
            mod = importlib.import_module("src.cogs.admin_notes")
            notes_group = getattr(mod, "notes", None)
            if notes_group:
                exists = self.tree.get_command("notes")  # type: ignore
                if exists is None:
                    try:
                        if GUILD_ID:
                            self.tree.add_command(notes_group, guild=discord.Object(id=GUILD_ID))
                        else:
                            self.tree.add_command(notes_group)
                        log.info("registered notes group")
                    except Exception as e:
                        if "already registered" in str(e).lower():
                            log.info("notes group already present; skipping (add_command duplicate)")
                        else:
                            raise
                else:
                    log.info("notes group already present; skipping (found in tree)")
        except Exception as e:
            log.warning("could not register notes group: %s", e)

        # --- /sync (admin) — tries guild, then global, and reports both ---
        @app_commands.command(
            name="sync",
            description="Admin: resync slash commands (tries guild, then global)"
        )
        @audit_event(action_type="admin.sync")
        async def sync_cmd(interaction: discord.Interaction):
            if not (isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator):
                await interaction.response.send_message("Nope.", ephemeral=True)
                return

            await interaction.response.defer(ephemeral=True, thinking=True)
            parts = []

            if interaction.guild:
                try:
                    cmds = await interaction.client.tree.sync(guild=interaction.guild)  # type: ignore
                    parts.append(f"Guild: {len(cmds)}")
                except Exception as e:
                    parts.append(f"Guild sync failed: {type(e).__name__}")

            try:
                gcmds = await interaction.client.tree.sync()
                parts.append(f"Global: {len(gcmds)}")
            except Exception as e:
                parts.append(f"Global sync failed: {type(e).__name__}")

            await interaction.followup.send("Synced — " + " • ".join(parts), ephemeral=True)

        # --- /inspect_full (admin) ---
        @app_commands.command(name="inspect_full", description="Admin: full profile with derived stats and recent actions")
        @app_commands.describe(user="Target member (defaults to you)")
        @audit_event(
            action_type="admin.inspect",
            target_user=lambda interaction, user=None: user,
            extra=lambda interaction, user=None: {"scope": "full_profile"}
        )
        async def inspect_full(interaction: discord.Interaction, user: discord.Member | None = None):
            if not (isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator):
                await interaction.response.send_message("Nope.", ephemeral=True); return
            await interaction.response.defer(ephemeral=True, thinking=True)

            member: discord.Member = user or interaction.user  # type: ignore
            created = member.created_at
            joined  = member.joined_at

            avatar_url = member.display_avatar.url if member.display_avatar else None
            banner_url = None
            try:
                u = await interaction.client.fetch_user(member.id)  # type: ignore
                if getattr(u, "banner", None):
                    banner_url = u.banner.url
            except Exception:
                pass

            roles_sorted = [r for r in sorted(member.roles, key=lambda r: r.position) if r.name != "@everyone"]
            top3 = [r.name for r in roles_sorted[-3:]] if roles_sorted else []
            risky = []
            for name, allowed in member.guild_permissions:
                if allowed and name in DANGEROUS_PERMS:
                    risky.append(name)
                if len(risky) >= 5: break

            status = str(getattr(member, "status", "offline"))
            dev = {
                "desktop": str(getattr(member, "desktop_status", "offline")),
                "mobile":  str(getattr(member, "mobile_status", "offline")),
                "web":     str(getattr(member, "web_status", "offline")),
            }
            activities = []
            try:
                for a in getattr(member, "activities", []) or []:
                    if getattr(a, "name", None): activities.append(getattr(a, "name"))
                    elif getattr(a, "state", None): activities.append(a.state)
            except Exception:
                pass

            timeout_until = getattr(member, "communication_disabled_until", None) or getattr(member, "timed_out_until", None)
            premium_since = getattr(member, "premium_since", None)
            pending = getattr(member, "pending", None)

            last_acted_raw = last_event_time(member.id)
            last_acted_pretty = _fmt_ts_local(last_acted_raw) if last_acted_raw else "—"

            badges = []
            try:
                badges = [getattr(b, "name", str(b)) for b in member.public_flags.all()]
            except Exception:
                pass
            accent = getattr(member, "accent_color", None); accent_val = getattr(accent, "value", None)

            msg7  = message_count(member.id, 7, interaction.guild.id)   # type: ignore
            msg30 = message_count(member.id, 30, interaction.guild.id)  # type: ignore

            notes = list_admin_notes(interaction.guild.id, member.id, 2)  # type: ignore
            notes_lines = [f"`{ts}` — <@{aid}> — {note}" for (_nid, ts, aid, note) in notes] if notes else []

            header = "\n".join([
                f"{member.mention} --",
                f"ID -- `{member.id}`",
                f"Account Created -- `{created.isoformat().replace('+00:00','Z') if created else '—'}` ({_rel_ymdh(created)})",
                f"Joined Guild -- `{joined.isoformat().replace('+00:00','Z') if joined else '—'}` ({_rel_ymdh(joined)})",
            ])

            e = discord.Embed(title="🛠️ Admin Inspector — Full Profile", description=header, colour=discord.Color.blurple())
            if avatar_url: e.set_thumbnail(url=avatar_url)
            if banner_url: e.set_image(url=banner_url)

            e.add_field(
                name="Status / Devices",
                value=f"Current Status: {status} <{last_acted_pretty}>\n"
                      f"🖥 {dev['desktop']}\n📱 {dev['mobile']}\n🌐 {dev['web']}",
                inline=False
            )
            if activities:
                e.add_field(name="Activities", value="; ".join(activities)[:1024], inline=False)

            e.add_field(name="Top Roles", value=(", ".join(top3) or "—"), inline=False)
            e.add_field(name="⚠️ High-Risk Perms (top 5)", value=(", ".join(risky) or "—"), inline=False)

            trusted = _is_trusted(member)
            e.add_field(name="Trusted", value=("Yes ✅" if trusted else "No ❌"), inline=True)
            e.add_field(name="Accent", value=f"`{_hex_color(accent_val) or '—'}`", inline=True)

            if premium_since:
                e.add_field(name="Boosting Since", value=f"`{premium_since.isoformat().replace('+00:00','Z')}`", inline=True)
            if pending is not None:
                e.add_field(name="Passed Screening", value=("Yes" if not pending else "Pending"), inline=True)
            if timeout_until:
                e.add_field(name="Timeout Until", value=f"`{timeout_until.isoformat().replace('+00:00','Z')}`", inline=True)

            e.add_field(name="Badges", value=(", ".join(badges) or "—")[:1024], inline=False)
            e.add_field(name="Msg Counts", value=f"7d: `{msg7}` • 30d: `{msg30}`", inline=True)
            e.add_field(name="Log DB", value=f"`{str(DB_PATH)}`", inline=True)

            # --- recent actions: explicit formatting here (always show the section) ---
            # Try to call recent_events with guild first (some versions require it)
            try:
                recents = recent_events(member.id, 50, interaction.guild.id)  # type: ignore[attr-defined]
            except TypeError:
                recents = recent_events(member.id, 50)

            def _recent_line(ts, kind, data):
                ch  = _ch_label_from_payload(interaction.guild, data) if interaction.guild else "—"  # type: ignore
                txt = _snippet(_extract_text(data))

                if kind == "message":
                    prefix = "Msg"
                    body   = txt or "—"
                elif kind == "message_edit":
                    prefix = "Edit"
                    body   = txt or (data.get("after") or {}).get("content") or "—"
                elif kind == "message_delete":
                    prefix = "Del"
                    body   = txt or (data.get("before") or {}).get("content") or "unknown"
                elif kind == "message_bulk_delete":
                    prefix = f"BulkDel x{data.get('count', 0)}"
                    cached = data.get("cached_with_text", 0)
                    body   = f"{cached} with text" if cached else ""
                else:
                    prefix = kind.replace("_", " ").title()
                    body   = txt or ""

                return f"{_fmt_ts_local(ts)}  {prefix}@{ch} - {body or '—'}"

            pretty = []
            for row in recents[:20]:  # cap at 20 lines
                # tolerate (ts, kind, payload) OR (id, ts, kind, payload)
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

                # Trim every individual line a bit so the field fits 1024 chars
                line = _recent_line(ts, kind, data)
                if len(line) > 120:
                    line = line[:117] + "…"
                pretty.append(line)

            # Always show the section (even if empty)
            out = "\n".join(pretty) if pretty else "None recorded yet — start chatting to populate this!"
            # Ensure Discord field limit (1024 chars)
            while len(out) > 1024 and len(pretty) > 1:
                pretty.pop()                # drop the oldest line in our slice
                out = "\n".join(pretty)

            e.add_field(name="Recent Actions", value=out, inline=False)



            e.set_footer(text=f"{BUILD_TAG} — Use /note_list to view all, /note_add to add, /note_delete to remove")

            out = io.StringIO(); w = csv.writer(out)
            w.writerow(["ts_utc","kind","payload"])
            for ts, kind, payload in recents:
                w.writerow([ts, kind, payload])
            file = discord.File(io.BytesIO(out.getvalue().encode("utf-8")), filename=f"recent_actions_{member.id}.csv")
            await interaction.followup.send(embed=e, file=file, ephemeral=True)

        # ----- register & SYNC with fallback -----
        async def register_and_sync():
            # Always add GLOBAL commands locally so dispatch never fails
            for fn, label in ((sync_cmd, "sync"), (inspect_full, "inspect_full")):
                try:
                    self.tree.add_command(fn)
                except Exception as e:
                    if "already registered" in str(e).lower():
                        pass
                    else:
                        log.warning("add_command(global,%s) failed: %s", label, e)

            guild_added = False
            if GUILD_ID:
                guild = discord.Object(id=GUILD_ID)
                for fn, label in ((sync_cmd, "sync"), (inspect_full, "inspect_full")):
                    try:
                        self.tree.add_command(fn, guild=guild)
                        guild_added = True
                    except Exception as e:
                        if "already registered" in str(e).lower():
                            guild_added = True
                        else:
                            log.warning("add_command(guild,%s) failed: %s", label, e)

            # Try to sync both scopes; report counts
            g_count = "n/a"
            try:
                gcmds = await self.tree.sync()
                g_count = str(len(gcmds))
            except Exception as e:
                log.warning("Global sync failed: %s", e)

            if GUILD_ID and guild_added:
                try:
                    gcmds = await self.tree.sync(guild=discord.Object(id=GUILD_ID))
                    log.info("startup sync — Guild: %d • Global: %s", len(gcmds if 'gcmds' in locals() else []), g_count)
                    log.info("slash commands guild-synced: %d cmds to %s", len(gcmds), GUILD_ID)
                except Exception as e:
                    log.warning("Guild sync failed for %s (%s).", GUILD_ID, e)
                    log.info("startup sync — Guild: failed • Global: %s", g_count)
            else:
                log.info("startup sync — Guild: skipped • Global: %s", g_count)

        await register_and_sync()

        # Inventory
        for cmd in self.tree.walk_commands():
            mod = getattr(cmd.callback, "__module__", "?")
            log.info("slash cmd: /%s from %s", cmd.qualified_name, mod)

    async def on_ready(self):
        log.info("Logged in as %s (%s) — %s", self.user, getattr(self.user, "id", "?"), BUILD_TAG)

def build_bot() -> LowlifeBot:
    intents = discord.Intents.default()
    intents.members = True
    intents.presences = True
    intents.message_content = True
    return LowlifeBot(command_prefix="!", intents=intents)

async def main():
    if not TOKEN:
        log.error("Missing DISCORD_TOKEN in .env. Put it in GAME\\.env or repo .env.")
        return
    bot = build_bot()
    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
