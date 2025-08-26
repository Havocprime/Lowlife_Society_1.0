from __future__ import annotations 

import os, sys, asyncio, logging, io, csv, json
from pathlib import Path
from datetime import datetime, timezone

import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from zoneinfo import ZoneInfo

# ---------------- build marker -------------
BUILD_TAG = "bot.py:v4-inspect_full-and-cmd-origin-log"

# ---------- paths & env ----------
THIS_FILE = Path(__file__).resolve()
GAMEROOT  = THIS_FILE.parents[2]      # ...\GAME\src
SUPERROOT = THIS_FILE.parents[3]      # repo root

for p in (SUPERROOT, GAMEROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

# load .env from both locations; GAME overrides root
load_dotenv(SUPERROOT / ".env")
load_dotenv(GAMEROOT / ".env", override=True)

TOKEN    = os.getenv("DISCORD_TOKEN", "").strip()
GUILD_ID = int(os.getenv("DISCORD_GUILD_ID", "0") or "0")
ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID", "0") or "0")
TRUSTED_ROLE_IDS = {int(x) for x in os.getenv("TRUSTED_ROLE_IDS", "").split(",") if x.strip().isdigit()}
TRUSTED_ROLE_NAMES = {x.strip().lower() for x in os.getenv("TRUSTED_ROLE_NAMES", "").split(",") if x.strip()}

# ✅ import AFTER sys.path is set
from src.core.audit import ensure_db, audit_event

# event/db helpers
from src.core.events import (
    recent_events, last_event_time, DB_PATH,
    message_count, list_admin_notes
)

# ---------- logging ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
log = logging.getLogger("boot")
log.info("Starting %s", BUILD_TAG)

# ---------- helpers ----------
DANGEROUS_PERMS = {
    "administrator","manage_guild","manage_channels","manage_roles","manage_webhooks",
    "kick_members","ban_members","mention_everyone","manage_messages","manage_threads",
    "mute_members","deafen_members","move_members","priority_speaker"
}

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

LA_TZ = None
try:
    LA_TZ = ZoneInfo("America/Los_Angeles")
except Exception:
    LA_TZ = None

def _fmt_ts_local(ts_in) -> str:
    """DD/MM/YY H:MM AM/PM in LA time if available; accepts iso 'Z', seconds, ms, datetime."""
    try:
        dt: datetime
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
        h12  = hour % 12 or 12
        return f"{dt.day}/{dt.month}/{dt.year % 100:02d} {h12}:{dt.minute:02d} {ampm}"
    except Exception:
        return str(ts_in)

def _is_trusted(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    if ADMIN_ROLE_ID and any(r.id == ADMIN_ROLE_ID for r in member.roles):
        return True
    if TRUSTED_ROLE_IDS and any(r.id in TRUSTED_ROLE_IDS for r in member.roles):
        return True
    if TRUSTED_ROLE_NAMES and any(r.name.lower() in TRUSTED_ROLE_NAMES for r in member.roles):
        return True
    return False

def _snippet(s: str | None, n: int = 120) -> str:
    if not s:
        return ""
    s = s.replace("\n", " ").strip()
    return (s[:n] + "…") if len(s) > n else s

def _to_int(x):
    try:
        return int(x)
    except Exception:
        return None

def _ch_mention_from_payload(guild: discord.Guild, d: dict) -> str:
    cid = d.get("channel_id") or d.get("channel") or d.get("cid")
    if isinstance(cid, dict):
        cid = cid.get("id")
    cid = _to_int(cid)
    if not cid:
        return "—"
    ch = guild.get_channel(cid)
    return ch.mention if ch else f"<#{cid}>"

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

def _role_mentions(guild: discord.Guild, ids: list[str] | list[int] | None) -> str:
    if not ids:
        return "—"
    out = []
    for rid in ids:
        rid_i = _to_int(rid)
        if rid_i is None:
            out.append(f"`{rid}`")
            continue
        r = guild.get_role(rid_i)
        out.append(r.mention if r else f"`{rid_i}`")
    return ", ".join(out) if out else "—"

# ---------- bot ----------
class LowlifeBot(commands.Bot):
    async def setup_hook(self):
        # Ensure audit DB/schema exists before anything logs
        await ensure_db()

        async def try_load(mod: str):
            try:
                await self.load_extension(mod)
                log.info("loaded extension: %s", mod)
            except Exception:
                log.exception("failed to load %s", mod)  # full traceback

        # your cogs
        await try_load("src.cogs.invite_tracker")
        await try_load("src.cogs.member_intake")
        await try_load("src.cogs.admin_inspector")   # likely owns the old /inspect
        await try_load("src.cogs.activity_logger")
        await try_load("src.cogs.admin_notes")
        await try_load("src.cogs.analytics")
        await try_load("src.cogs.audit_log")         # investigatory commands

        # --- explicitly register the /notes group into the same scope we sync ---
        try:
            from src.cogs.admin_notes import notes as _notes_group  # type: ignore
            if GUILD_ID:
                self.tree.add_command(_notes_group, guild=discord.Object(id=GUILD_ID))
            else:
                self.tree.add_command(_notes_group)
            log.info("registered notes group from src.cogs.admin_notes")
        except Exception as e:
            log.warning("could not import/register notes group: %s", e)

        # --- /sync (admin-only) ---
        @app_commands.command(name="sync", description="Admin: resync slash commands here")
        @audit_event(action_type="admin.sync")
        async def sync_cmd(interaction: discord.Interaction):
            if not (
                isinstance(interaction.user, discord.Member)
                and interaction.user.guild_permissions.administrator
            ):
                await interaction.response.send_message("Nope.", ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True, thinking=True)
            if interaction.guild:
                cmds = await interaction.client.tree.sync(guild=interaction.guild)  # type: ignore
                await interaction.followup.send(f"Synced {len(cmds)} commands to this guild.", ephemeral=True)
            else:
                cmds = await interaction.client.tree.sync()
                await interaction.followup.send(f"Synced {len(cmds)} commands globally.", ephemeral=True)

        # --- /inspect_full (admin-only, expanded) ---
        @app_commands.command(
            name="inspect_full",
            description="Admin: full profile with derived stats and recent actions (new formatting)"
        )
        @app_commands.describe(user="Target member (defaults to you)")
        @audit_event(
            action_type="admin.inspect",
            target_user=lambda interaction, user=None: user,
            extra=lambda interaction, user=None: {"scope": "full_profile"}
        )
        async def inspect_full(interaction: discord.Interaction, user: discord.Member | None = None):
            if not (
                isinstance(interaction.user, discord.Member)
                and interaction.user.guild_permissions.administrator
            ):
                await interaction.response.send_message("Nope.", ephemeral=True)
                return

            await interaction.response.defer(ephemeral=True, thinking=True)

            member: discord.Member = user or interaction.user  # type: ignore
            created = member.created_at
            joined  = member.joined_at

            # images
            avatar_url = member.display_avatar.url if member.display_avatar else None
            banner_url = None
            try:
                u = await interaction.client.fetch_user(member.id)  # type: ignore
                if getattr(u, "banner", None):
                    banner_url = u.banner.url
            except Exception:
                pass

            # roles & perms
            roles_sorted = [r for r in sorted(member.roles, key=lambda r: r.position) if r.name != "@everyone"]
            top3 = [r.name for r in roles_sorted[-3:]] if roles_sorted else []
            risky = []
            for name, allowed in member.guild_permissions:
                if allowed and name in DANGEROUS_PERMS:
                    risky.append(name)
                if len(risky) >= 5:
                    break

            # presence / devices / activities
            status = str(getattr(member, "status", "offline"))
            dev = {
                "desktop": str(getattr(member, "desktop_status", "offline")),
                "mobile":  str(getattr(member, "mobile_status", "offline")),
                "web":     str(getattr(member, "web_status", "offline")),
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

            # message counts from our logs
            msg7  = message_count(member.id, 7, interaction.guild.id)   # type: ignore
            msg30 = message_count(member.id, 30, interaction.guild.id)  # type: ignore

            # admin notes preview
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

            if notes_lines:
                e.add_field(name=f"Admin Notes — latest {len(notes_lines)}", value="\n".join(notes_lines), inline=False)

            # ---- recent actions: explicit formatting here ----
            recents = recent_events(member.id, 50)

            pretty = []
            for ts, kind, payload in recents[:10]:
                try:
                    data = json.loads(payload or "{}")
                except Exception:
                    data = {}

                if kind == "message":
                    ch = _ch_mention_from_payload(interaction.guild, data)  # type: ignore
                    text = _snippet(_extract_text(data))
                    desc = f"message in {ch} — “{text or '—'}”"
                elif kind == "message_edit":
                    ch = _ch_mention_from_payload(interaction.guild, data)  # type: ignore
                    after = _snippet(_extract_text(data) or (data.get("after") or {}).get("content") or "")
                    desc = f"edited message in {ch} — “{after or '—'}”"
                elif kind == "message_delete":
                    ch = _ch_mention_from_payload(interaction.guild, data)  # type: ignore
                    txt = _snippet(_extract_text(data) or (data.get("before") or {}).get("content") or "")
                    desc = f"deleted message in {ch} — “{txt or 'unknown'}”"
                elif kind == "message_bulk_delete":
                    ch = _ch_mention_from_payload(interaction.guild, data)  # type: ignore
                    cnt = data.get("count", 0)
                    cached = data.get("cached_with_text", 0)
                    extra = f" ({cached} with text)" if cached else ""
                    desc = f"bulk delete in {ch} — {cnt} messages{extra}"
                else:
                    # Compact fallback for non-message events
                    desc = kind.replace("_", " ")

                pretty.append(f"{_fmt_ts_local(ts)} — {desc}")

            if pretty:
                e.add_field(name="Recent Actions", value="\n".join(pretty), inline=False)

            e.set_footer(text=f"{BUILD_TAG} — Use /note_list to view all, /note_add to add, /note_delete to remove")

            # CSV attachment
            out = io.StringIO()
            w = csv.writer(out)
            w.writerow(["ts_utc","kind","payload"])
            for ts, kind, payload in recents:
                w.writerow([ts, kind, payload])
            file = discord.File(io.BytesIO(out.getvalue().encode("utf-8")),
                                filename=f"recent_actions_{member.id}.csv")

            await interaction.followup.send(embed=e, file=file, ephemeral=True)

        # ----- register commands and sync now -----
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            self.tree.add_command(sync_cmd, guild=guild)
            self.tree.add_command(inspect_full, guild=guild)  # << our new name
            self.tree.copy_global_to(guild=guild)
            cmds = await self.tree.sync(guild=guild)
            log.info("slash commands guild-synced: %d cmds to %s", len(cmds), GUILD_ID)
        else:
            self.tree.add_command(sync_cmd)
            self.tree.add_command(inspect_full)  # << our new name
            cmds = await self.tree.sync()
            log.info("slash commands globally synced: %d cmds", len(cmds))

        # --- print who owns each command (module) to spot conflicts ---
        for cmd in self.tree.walk_commands():
            try:
                mod = getattr(cmd.callback, "__module__", "?")
            except Exception:
                mod = "?"
            log.info("slash cmd: /%s from %s", cmd.qualified_name, mod)

        log.info("tree.walk_commands(): %s", [c.qualified_name for c in self.tree.walk_commands()])

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
