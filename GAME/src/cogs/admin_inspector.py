from __future__ import annotations

import csv
import io
import json
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands

# event log helpers
from src.core.events import DB_PATH, last_event_time, recent_events

# ---- config ----
ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID", "0"))
TRUSTED_ROLE_IDS = {
    int(x) for x in os.getenv("TRUSTED_ROLE_IDS", "").split(",") if x.strip().isdigit()
}
TRUSTED_ROLE_NAMES = {
    x.strip().lower() for x in os.getenv("TRUSTED_ROLE_NAMES", "").split(",") if x.strip()
}

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


# ---- utils ----
def _flag_names(flags_obj) -> list[str]:
    out: list[str] = []
    if not flags_obj:
        return out
    try:
        for f in flags_obj.all():
            out.append(getattr(f, "name", str(f)))
        return out
    except Exception:
        pass
    try:
        val = getattr(flags_obj, "value", 0)
        cls = flags_obj.__class__
        for attr in dir(cls):
            if attr.startswith("_"):
                continue
            bit = getattr(cls, attr, None)
            if isinstance(bit, int) and (val & bit):
                out.append(attr.lower())
    except Exception:
        pass
    return out


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
    if y:
        parts.append(f"{y}_years")
    if m:
        parts.append(f"{m}_months")
    if d:
        parts.append(f"{d}_days")
    parts.append(f"{h}_hours")
    return "_".join(parts) + " ago"


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


# ---- formatting helpers ----
LA_TZ = None
try:
    LA_TZ = ZoneInfo("America/Los_Angeles")
except Exception:
    LA_TZ = None


def _fmt_ts_local(ts_in) -> str:
    """DD/MM/YY H:MM AM/PM (LA tz if available). Accepts isoZ/seconds/ms/datetime."""
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


def _snippet(s: str | None, n: int = 120) -> str:
    if not s:
        return ""
    s = s.replace("\n", " ").strip()
    return (s[:n] + "…") if len(s) > n else s


def _emoji_name(d: dict) -> str:
    e = d.get("emoji") or {}
    name = e.get("name")
    if not name and isinstance(e, str):
        name = e
    return str(name or "emoji")


def _role_list(guild: discord.Guild, ids) -> str:
    if not ids:
        return "—"
    out = []
    for rid in ids:
        rid = _to_int(rid)
        if not rid:
            out.append(f"`{rid}`")
            continue
        r = guild.get_role(rid)
        out.append(r.mention if r else f"`{rid}`")
    return ", ".join(out) if out else "—"


# ---- Cog ----
class AdminInspector(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _is_admin(self, i: discord.Interaction) -> bool:
        return isinstance(i.user, discord.Member) and i.user.guild_permissions.administrator

    @app_commands.command(
        name="inspect", description="Admin: full profile with derived stats and recent actions"
    )
    @app_commands.describe(user="Target member (defaults to you)")
    async def inspect(self, interaction, user: discord.Member | None = None):
        if not self._is_admin(interaction):
            return await interaction.response.send_message("Nope.", ephemeral=True)

        await interaction.response.defer(ephemeral=True, thinking=True)
        member: discord.Member = user or interaction.user  # type: ignore

        # -------- gather core/derived --------
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
        high_risk = [
            p for p, ok in dict(member.guild_permissions).items() if ok and p in DANGEROUS_PERMS
        ][:5]
        trusted = _is_trusted(member)

        status = str(getattr(member, "status", "offline"))
        dev = {
            "desktop": str(getattr(member, "desktop_status", "offline")),
            "mobile": str(getattr(member, "mobile_status", "offline")),
            "web": str(getattr(member, "web_status", "offline")),
        }
        last_acted = last_event_time(member.id) or "—"
        badges = _flag_names(getattr(member, "public_flags", None))
        accent = getattr(member, "accent_color", None)
        accent_val = getattr(accent, "value", None)

        # -------- header --------
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

        last_acted_pretty = _fmt_ts_local(last_acted) if last_acted != "—" else "—"
        e.add_field(
            name="Status / Devices",
            value=f"Current Status: {status} <{last_acted_pretty}>\n"
            f"🖥 {dev['desktop']}\n📱 {dev['mobile']}\n🌐 {dev['web']}",
            inline=False,
        )

        e.add_field(name="Top Roles", value=(", ".join(top3) or "—"), inline=False)
        e.add_field(
            name="⚠️ High-Risk Perms (top 5)", value=(", ".join(high_risk) or "—"), inline=False
        )
        e.add_field(name="Trusted", value=("Yes ✅" if trusted else "No ❌"), inline=True)
        e.add_field(name="Accent", value=f"`{_hex_color(accent_val) or '—'}`", inline=True)
        e.add_field(name="Badges", value=(", ".join(badges) or "—")[:1024], inline=False)

        # -------- Recent actions (comprehensive tag@target) --------
        recents = recent_events(member.id, 50)
        if recents:
            lines = []
            for ts, kind, payload in recents[:10]:
                try:
                    d = json.loads(payload or "{}")
                except Exception:
                    d = {}

                # Messages
                if kind == "message":
                    ch = _ch_mention_from_payload(interaction.guild, d)  # type: ignore
                    text = _snippet(_extract_text(d))
                    desc = f"msg@{ch} — “{text or '—'}”"
                elif kind == "message_edit":
                    ch = _ch_mention_from_payload(interaction.guild, d)
                    after = _snippet(
                        _extract_text(d) or (d.get("after") or {}).get("content") or ""
                    )
                    desc = f"edit@{ch} — “{after or '—'}”"
                elif kind == "message_delete":
                    ch = _ch_mention_from_payload(interaction.guild, d)
                    txt = _snippet(_extract_text(d) or (d.get("before") or {}).get("content") or "")
                    desc = f"del@{ch} — “{txt or 'unknown'}”"
                elif kind == "message_bulk_delete":
                    ch = _ch_mention_from_payload(interaction.guild, d)
                    cnt = d.get("count", 0)
                    cached = d.get("cached_with_text", 0)
                    extra = f", {cached} with text" if cached else ""
                    desc = f"bulkdel@{ch} — {cnt} msgs{extra}"

                # Reactions
                elif kind == "reaction_add":
                    ch = _ch_mention_from_payload(interaction.guild, d)
                    desc = f"react+@{ch} — { _emoji_name(d) }"
                elif kind == "reaction_remove":
                    ch = _ch_mention_from_payload(interaction.guild, d)
                    desc = f"react-@{ch} — { _emoji_name(d) }"

                # Presence / activity
                elif kind == "presence":
                    desc = f"presence@self — {d.get('before')} → {d.get('after')}"
                elif kind == "activity":
                    b, a = d.get("before"), d.get("after")
                    desc = f"activity@self — {b or '—'} → {a or '—'}"

                # Voice
                elif kind == "voice_channel":
                    b = d.get("before")
                    a = d.get("after")
                    desc = f"voice@self — {b or '—'} → {a or '—'}"
                elif kind == "voice_mute":
                    desc = f"voice@mute — self={d.get('self')} server={d.get('server')}"
                elif kind == "voice_deaf":
                    desc = f"voice@deaf — self={d.get('self')} server={d.get('server')}"
                elif kind == "voice_stream":
                    desc = f"voice@stream — {d.get('streaming')}"

                # Roles / perms
                elif kind == "roles":
                    added = _role_list(interaction.guild, d.get("added"))  # type: ignore
                    removed = _role_list(interaction.guild, d.get("removed"))  # type: ignore
                    desc = f"roles@self — +{added}  −{removed}"
                elif kind == "perm_diff":
                    g = ", ".join(d.get("gained") or []) or "—"
                    l = ", ".join(d.get("lost") or []) or "—"
                    desc = f"perms@self — +{g}  −{l}"

                # Moderation / membership
                elif kind == "timeout":
                    desc = f"timeout@self — until {d.get('after') or 'cleared'}"
                elif kind == "boost":
                    desc = f"boost@self — {'started' if d.get('after') else 'ended'}"
                elif kind == "member_join":
                    desc = "member@self — joined"
                elif kind == "member_leave":
                    desc = "member@self — left"

                # Invites / channels / pins
                elif kind == "invite_create":
                    ch = _ch_mention_from_payload(interaction.guild, d)
                    desc = f"invite@{ch} — code {d.get('code')}"
                elif kind == "invite_delete":
                    desc = f"invite@deleted — code {d.get('code')}"
                elif kind == "channel_update":
                    ch = _ch_mention_from_payload(interaction.guild, d)
                    desc = f"channel@{ch} — updated"
                elif kind == "pins_update":
                    ch = _ch_mention_from_payload(interaction.guild, d)
                    desc = f"pins@{ch} — updated"

                # Channel create/delete (if logged)
                elif kind == "channel_create":
                    ch = _ch_mention_from_payload(interaction.guild, d)
                    desc = f"channel@{ch} — created"
                elif kind == "channel_delete":
                    ch = _ch_mention_from_payload(interaction.guild, d)
                    desc = f"channel@{ch} — deleted"

                else:
                    desc = kind.replace("_", " ")

                lines.append(f"{_fmt_ts_local(ts)} — {desc}")

            e.add_field(name="Recent Actions", value="\n".join(lines)[:1024], inline=False)

        e.add_field(name="Log DB", value=f"`{str(DB_PATH)}`", inline=False)

        # attach CSV
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(["ts_utc", "kind", "payload"])
        for ts, kind, payload in recents:
            w.writerow([ts, kind, payload])
        file = discord.File(
            io.BytesIO(out.getvalue().encode("utf-8")), filename=f"recent_actions_{member.id}.csv"
        )

        await interaction.followup.send(embed=e, file=file, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminInspector(bot))
