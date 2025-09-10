import os
import sqlite3
from pathlib import Path


def write(p: Path, s: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")


write(
    Path("src/core/schema.sql"),
    """
-- players
CREATE TABLE IF NOT EXISTS players (
  discord_id           TEXT PRIMARY KEY,
  name                 TEXT,
  global_name          TEXT,
  nickname             TEXT,
  is_bot               BOOLEAN,
  is_system            BOOLEAN,
  created_at_utc       TEXT,
  joined_at_utc        TEXT,
  avatar_url           TEXT,
  banner_url           TEXT,
  accent_color         INTEGER,
  premium_since_utc    TEXT,
  top_role_id          TEXT,
  top_role_name        TEXT,
  status               TEXT,
  public_flags         INTEGER,
  communication_disabled_until_utc TEXT,
  veteran_rank         TEXT,
  portrait_asset       TEXT,
  invite_code          TEXT,
  inviter_id           TEXT,
  invite_channel_id    TEXT,
  risk_score           INTEGER,
  risk_reasons         TEXT,
  first_snapshot_json  TEXT,
  created_ts           TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS player_roles (
  discord_id  TEXT,
  role_id     TEXT,
  role_name   TEXT,
  PRIMARY KEY (discord_id, role_id)
);
CREATE TABLE IF NOT EXISTS join_events (
  id                   INTEGER PRIMARY KEY AUTOINCREMENT,
  discord_id           TEXT,
  guild_id             TEXT,
  joined_at_utc        TEXT,
  invite_code          TEXT,
  inviter_id           TEXT,
  pre_roles_json       TEXT,
  post_roles_json      TEXT,
  snapshot_json        TEXT
);
""".strip(),
)

write(
    Path("src/core/portraits.py"),
    """
from pathlib import Path
PORTRAIT_DIR = Path("game/assets/portraits")
def list_portraits():
    if not PORTRAIT_DIR.exists():
        return []
    exts = {".png",".jpg",".jpeg",".webp"}
    return sorted([p for p in PORTRAIT_DIR.iterdir() if p.suffix.lower() in exts])
def pick_portrait_for_user(user_id: int) -> str | None:
    files = list_portraits()
    if not files:
        return None
    return str(files[user_id % len(files)])
""".strip(),
)

write(
    Path("src/core/risk.py"),
    """
from datetime import datetime, timezone
def compute_risk(snapshot: dict) -> tuple[int, list[str]]:
    reasons = []; score = 0
    user = snapshot.get("user", {}); member = snapshot.get("member", {})
    created = user.get("created_at")
    if created:
        try:
            created_dt = datetime.fromisoformat(created.replace("Z","+00:00"))
            age_days = (datetime.now(timezone.utc) - created_dt).days
            if age_days < 7:
                score += 30; reasons.append("very_new_account")
        except Exception:
            pass
    if not user.get("banner_url"):
        score += 3; reasons.append("no_banner")
    if not user.get("avatar_url"):
        score += 15; reasons.append("default_avatar")
    roles = member.get("roles", [])
    if len(roles) <= 1:
        score += 10; reasons.append("no_roles")
    if member.get("pending"):
        score += 10; reasons.append("membership_screen_pending")
    return score, reasons
""".strip(),
)

write(
    Path("src/core/db.py"),
    """
import json, sqlite3
from pathlib import Path
DB_PATH = Path("data/lowlife.db")
SCHEMA_PATH = Path(__file__).with_name("schema.sql")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c
def init():
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with conn() as db:
        db.executescript(schema)
def upsert_player(snapshot: dict):
    user = snapshot.get("user", {})
    member = snapshot.get("member", {})
    derived = snapshot.get("derived", {})
    ctx = snapshot.get("join_context", {})
    roles = member.get("roles", [])
    top_role = roles[-1] if roles else {"id": None, "name": None}
    with conn() as db:
        db.execute(\"\"\"
        INSERT INTO players (discord_id,name,global_name,nickname,is_bot,is_system,created_at_utc,joined_at_utc,
            avatar_url,banner_url,accent_color,premium_since_utc,top_role_id,top_role_name,status,public_flags,
            communication_disabled_until_utc,veteran_rank,portrait_asset,invite_code,inviter_id,invite_channel_id,
            risk_score,risk_reasons,first_snapshot_json)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(discord_id) DO UPDATE SET
          name=excluded.name, global_name=excluded.global_name, nickname=excluded.nickname,
          joined_at_utc=excluded.joined_at_utc, avatar_url=excluded.avatar_url, banner_url=excluded.banner_url,
          accent_color=excluded.accent_color, premium_since_utc=excluded.premium_since_utc,
          top_role_id=excluded.top_role_id, top_role_name=excluded.top_role_name, status=excluded.status,
          communication_disabled_until_utc=excluded.communication_disabled_until_utc,
          veteran_rank=excluded.veteran_rank, portrait_asset=excluded.portrait_asset,
          invite_code=excluded.invite_code, inviter_id=excluded.inviter_id, invite_channel_id=excluded.invite_channel_id,
          risk_score=excluded.risk_score, risk_reasons=excluded.risk_reasons, first_snapshot_json=excluded.first_snapshot_json
        \"\"\", (
            user.get("id"), user.get("name"), user.get("global_name"), member.get("nick"),
            bool(user.get("bot")), bool(user.get("system")),
            user.get("created_at"), member.get("joined_at"), user.get("avatar_url"), user.get("banner_url"),
            user.get("accent_color"), member.get("premium_since"), top_role.get("id"), top_role.get("name"),
            member.get("status"), user.get("public_flags"), member.get("communication_disabled_until"),
            derived.get("veteran_rank"), derived.get("portrait_asset"), ctx.get("invite_code"),
            ctx.get("inviter_id"), ctx.get("invite_channel_id"),
            int(derived.get("risk_score", 0)), json.dumps(derived.get("risk_reasons", [])),
            json.dumps(snapshot)
        ))
        db.execute("DELETE FROM player_roles WHERE discord_id=?", (user.get("id"),))
        for r in roles:
            db.execute("INSERT OR IGNORE INTO player_roles (discord_id,role_id,role_name) VALUES (?,?,?)",
                       (user.get("id"), r.get("id"), r.get("name")))
""".strip(),
)

write(
    Path("src/cogs/invite_tracker.py"),
    """
import discord
from discord.ext import commands
class InviteTracker(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._cache: dict[int, list[discord.Invite]] = {}
    async def cache_guild(self, guild: discord.Guild):
        try:
            self._cache[guild.id] = await guild.invites()
        except Exception:
            self._cache[guild.id] = []
    @commands.Cog.listener()
    async def on_ready(self):
        for g in self.bot.guilds:
            await self.cache_guild(g)
    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        await self.cache_guild(invite.guild)
    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        await self.cache_guild(invite.guild)
    async def diff_invites(self, guild: discord.Guild):
        before = self._cache.get(guild.id, [])
        try:
            after = await guild.invites()
        except Exception:
            return None, None, None
        used = None
        for a in after:
            match = next((b for b in before if b.code == a.code), None)
            if match and a.uses > match.uses:
                used = a; break
        await self.cache_guild(guild)
        if used:
            inviter_id = used.inviter.id if used.inviter else None
            channel_id = used.channel.id if used.channel else None
            return used.code, inviter_id, channel_id
        return None, None, None
async def setup(bot: commands.Bot):
    await bot.add_cog(InviteTracker(bot))
""".strip(),
)

write(
    Path("src/cogs/member_intake.py"),
    """
from __future__ import annotations
import os, discord
from discord.ext import commands
from datetime import datetime, timezone
from src.core.portraits import pick_portrait_for_user
from src.core.risk import compute_risk
from src.core.db import upsert_player
WELCOME_CHANNEL_ID = int(os.getenv("WELCOME_CHANNEL_ID", "0"))
def veteran_rank(days: int) -> str:
    return ("Legend" if days >= 365*4 else
            "Vanguard" if days >= 365*2 else
            "Regular" if days >= 365 else
            "Streetwise" if days >= 90 else
            "Rookie" if days >= 7 else
            "Fresh Meat")
class MemberIntake(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        now = datetime.now(timezone.utc)
        inv_cog = self.bot.get_cog("InviteTracker")
        invite_code = inviter_id = invite_channel_id = None
        if inv_cog:
            try:
                invite_code, inviter_id, invite_channel_id = await inv_cog.diff_invites(member.guild)
            except Exception:
                pass
        created = member.created_at.replace(tzinfo=timezone.utc)
        age_days = (now - created).days
        snapshot = {
          "user": {
            "id": str(member.id),
            "name": getattr(member, "name", None),
            "global_name": getattr(member, "global_name", None),
            "bot": bool(member.bot),
            "system": bool(member.system),
            "created_at": created.isoformat().replace("+00:00","Z"),
            "avatar_url": member.display_avatar.url if member.display_avatar else None,
            "banner_url": None,
            "accent_color": getattr(member, "accent_color", None).value if getattr(member, "accent_color", None) else None,
            "public_flags": getattr(member, "public_flags", 0).value if getattr(member, "public_flags", None) else 0,
          },
          "member": {
            "nick": member.nick,
            "joined_at": (member.joined_at or now).isoformat().replace("+00:00","Z"),
            "pending": bool(member.pending),
            "premium_since": member.premium_since.isoformat().replace("+00:00","Z") if member.premium_since else None,
            "roles": [{"id": str(r.id), "name": r.name} for r in sorted(member.roles, key=lambda r: r.position)],
            "status": str(getattr(member, "status", "offline")),
            "activities": [getattr(a, "name", str(a)) for a in getattr(member, "activities", [])],
            "voice": {
              "channel_id": str(member.voice.channel.id) if member.voice and member.voice.channel else None,
              "mute": bool(member.voice.mute) if member.voice else False,
              "deaf": bool(member.voice.deaf) if member.voice else False,
              "stream": bool(getattr(member.voice, "self_stream", False)) if member.voice else False,
            },
            "communication_disabled_until": member.communication_disabled_until.isoformat().replace("+00:00","Z") if member.communication_disabled_until else None,
            "permissions": [p for p, allowed in dict(member.guild_permissions).items() if allowed],
          },
          "join_context": {
            "invite_code": invite_code,
            "inviter_id": str(inviter_id) if inviter_id else None,
            "invite_channel_id": str(invite_channel_id) if invite_channel_id else None
          },
          "derived": {}
        }
        snapshot["derived"]["veteran_rank"] = veteran_rank(age_days)
        portrait = pick_portrait_for_user(member.id)
        if portrait: snapshot["derived"]["portrait_asset"] = portrait
        risk_score, reasons = compute_risk(snapshot)
        snapshot["derived"]["risk_score"] = risk_score
        snapshot["derived"]["risk_reasons"] = reasons
        upsert_player(snapshot)
        await self.post_mugshot(member, snapshot)
    async def post_mugshot(self, member: discord.Member, snap: dict):
        if not WELCOME_CHANNEL_ID:
            return
        channel = member.guild.get_channel(WELCOME_CHANNEL_ID)
        if not channel or not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return
        portrait = snap["derived"].get("portrait_asset")
        file = discord.File(portrait, filename="mug.png") if portrait else None
        e = discord.Embed(
            title="ðŸ“¸ NEW ARRIVAL â€” FIRST MUGSHOT",
            description=f"**Alias:** {member.mention}\\n**Rank:** {snap['derived'].get('veteran_rank','â€”')}",
            colour=discord.Color.dark_embed()
        )
        if member.display_avatar:
            e.set_thumbnail(url=member.display_avatar.url)
        e.add_field(name="Discord ID", value=f"`{member.id}`", inline=True)
        e.add_field(name="Account Created", value=f"`{snap['user']['created_at']}`", inline=True)
        join_str = snap['member']['joined_at'].replace("T", " ").replace("Z", " UTC")
        e.add_field(name="Booked At", value=f"`{join_str}`", inline=True)
        inv = snap.get("join_context", {})
        inv_line = f"`{inv.get('invite_code') or 'unknown'}`"
        if inv.get("inviter_id"):
            inv_line += f" â€¢ by <@{inv['inviter_id']}>"
        e.add_field(name="Referral", value=inv_line, inline=False)
        risk = snap["derived"].get("risk_score", 0)
        reasons = ", ".join(snap["derived"].get("risk_reasons", [])) or "â€”"
        e.add_field(name="Risk Index", value=f"`{risk}` ({reasons})", inline=False)
        e.set_footer(text="LOWLIFE SOCIETY â€” Intake Bureau")
        if file:
            e.set_image(url="attachment://mug.png")
            await channel.send(embed=e, file=file)
        else:
            await channel.send(embed=e)
async def setup(bot: commands.Bot):
    await bot.add_cog(MemberIntake(bot))
""".strip(),
)

write(
    Path("src/cogs/admin_inspector.py"),
    """
import os, io, json, discord
from discord.ext import commands
from discord import app_commands
ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID", "0"))
class AdminInspector(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    def _is_admin(self, i: discord.Interaction) -> bool:
        if isinstance(i.user, discord.Member) and i.user.guild_permissions.administrator:
            return True
        if ADMIN_ROLE_ID and isinstance(i.user, discord.Member):
            return any(r.id == ADMIN_ROLE_ID for r in i.user.roles)
        return False
    @app_commands.command(name="inspect", description="Admin: dump every possible field for a member")
    @app_commands.describe(user="Target member (defaults to you)")
    async def inspect(self, interaction: discord.Interaction, user: discord.Member | None = None):
        if not self._is_admin(interaction):
            return await interaction.response.send_message("Nope.", ephemeral=True)
        member = user or interaction.user
        data = {
            "guild_id": str(interaction.guild_id),
            "user": {
                "id": str(member.id),
                "name": getattr(member, "name", None),
                "global_name": getattr(member, "global_name", None),
                "bot": bool(member.bot),
                "system": bool(member.system),
                "created_at": member.created_at.isoformat().replace("+00:00","Z"),
                "avatar_url": member.display_avatar.url if member.display_avatar else None,
                "banner_url": None,
                "accent_color": getattr(member, "accent_color", None).value if getattr(member, "accent_color", None) else None,
                "public_flags": getattr(member, "public_flags", 0).value if getattr(member, "public_flags", None) else 0,
            },
            "member": {
                "nick": member.nick,
                "joined_at": member.joined_at.isoformat().replace("+00:00","Z") if member.joined_at else None,
                "pending": bool(member.pending),
                "premium_since": member.premium_since.isoformat().replace("+00:00","Z") if member.premium_since else None,
                "roles": [{"id": str(r.id), "name": r.name, "position": r.position} for r in sorted(member.roles, key=lambda r: r.position)],
                "status": str(getattr(member, "status", "offline")),
                "activities": [getattr(a, "name", str(a)) for a in getattr(member, "activities", [])],
                "voice": {
                  "channel_id": str(member.voice.channel.id) if member.voice and member.voice.channel else None,
                  "mute": bool(member.voice.mute) if member.voice else False,
                  "deaf": bool(member.voice.deaf) if member.voice else False,
                  "stream": bool(getattr(member.voice, "self_stream", False)) if member.voice else False,
                },
                "communication_disabled_until": member.communication_disabled_until.isoformat().replace("+00:00","Z") if member.communication_disabled_until else None,
                "permissions_true": [p for p, allowed in dict(member.guild_permissions).items() if allowed],
                "permissions_false": [p for p, allowed in dict(member.guild_permissions).items() if not allowed],
            }
        }
        e = discord.Embed(title="ðŸ› ï¸ Admin Inspector", description=f"Full dump for {member.mention}", colour=discord.Color.blurple())
        e.add_field(name="ID", value=f"`{member.id}`", inline=True)
        e.add_field(name="Account Created", value=f"`{data['user']['created_at']}`", inline=True)
        e.add_field(name="Joined Guild", value=f"`{data['member']['joined_at'] or 'â€”'}`", inline=True)
        e.add_field(name="Roles", value=(", ".join(r['name'] for r in data['member']['roles']) or "â€”")[:1024], inline=False)
        e.add_field(name="Status", value=data["member"]["status"], inline=True)
        e.add_field(name="Activities", value=", ".join(data["member"]["activities"]) or "â€”", inline=True)
        if data["user"]["avatar_url"]:
            e.set_thumbnail(url=data["user"]["avatar_url"])
        buf = io.BytesIO(json.dumps(data, indent=2).encode("utf-8"))
        file = discord.File(buf, filename=f"inspect_{member.id}.json")
        await interaction.response.send_message(embed=e, file=file, ephemeral=True)
async def setup(bot: commands.Bot):
    await bot.add_cog(AdminInspector(bot))
""".strip(),
)

write(Path("scripts/__init__.py"), "")
write(
    Path("scripts/init_db.py"),
    "from src.core.db import init\nif __name__ == '__main__':\n    init()\n    print('DB initialized at data/lowlife.db')\n",
)

print("Wrote files to src/core, src/cogs, scripts")
