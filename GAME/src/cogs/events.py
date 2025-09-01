# GAME/src/cogs/events.py
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict

import discord
from discord.ext import commands

from src.db.dal import append_event, ensure_events_schema


def _now_iso() -> str:
    """UTC ISO string. Use 'Z' suffix for consistency with the rest of the bot."""
    s = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return s.replace("+00:00", "Z")


def _j(d: Dict[str, Any]) -> str:
    """Compact JSON string for payloads."""
    return json.dumps(d, separators=(",", ":"), ensure_ascii=False)


def _cut(s: str | None, n: int = 400) -> str | None:
    if not s:
        return None
    s = s.replace("\r", " ").replace("\n", " ").strip()
    return s[:n]


class EventCog(commands.Cog):
    """Lightweight event logger that writes to the unified Custodian DB (audit.sqlite)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- member lifecycle ----------

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        try:
            append_event(
                ts_utc=_now_iso(),
                guild_id=getattr(member.guild, "id", None),
                channel_id=None,
                author_id=member.id,
                kind="member.join",
                content=None,
                payload=_j(
                    {
                        "name": str(member),
                        "joined_at": getattr(member, "joined_at", None) and member.joined_at.isoformat().replace("+00:00", "Z"),
                    }
                ),
            )
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        try:
            append_event(
                ts_utc=_now_iso(),
                guild_id=getattr(member.guild, "id", None),
                channel_id=None,
                author_id=member.id,
                kind="member.remove",
                content=None,
                payload=_j({"name": str(member)}),
            )
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        try:
            if before.nick != after.nick or before.roles != after.roles:
                append_event(
                    ts_utc=_now_iso(),
                    guild_id=getattr(after.guild, "id", None),
                    channel_id=None,
                    author_id=after.id,
                    kind="member.update",
                    content=None,
                    payload=_j(
                        {
                            "before": {"nick": before.nick, "roles": [r.id for r in before.roles]},
                            "after": {"nick": after.nick, "roles": [r.id for r in after.roles]},
                        }
                    ),
                )
        except Exception:
            pass

    # ---------- messages ----------

    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        # Ignore the bot itself and other bots; also ignore DMs unless you want them
        if msg.author.bot:
            return
        if not msg.guild:
            return
        try:
            append_event(
                ts_utc=_now_iso(),
                guild_id=msg.guild.id,
                channel_id=getattr(msg.channel, "id", None),
                author_id=getattr(msg.author, "id", None),
                kind="message.create",
                content=_cut(msg.content, 800),
                payload=_j({"msg_id": msg.id}),
            )
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if getattr(after.author, "bot", False) or not after.guild:
            return
        try:
            append_event(
                ts_utc=_now_iso(),
                guild_id=after.guild.id,
                channel_id=getattr(after.channel, "id", None),
                author_id=getattr(after.author, "id", None),
                kind="message.edit",
                content=_cut(after.content, 800),
                payload=_j({"msg_id": after.id, "before": _cut(before.content, 400)}),
            )
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_message_delete(self, msg: discord.Message):
        if getattr(msg.author, "bot", False) or not msg.guild:
            return
        try:
            append_event(
                ts_utc=_now_iso(),
                guild_id=msg.guild.id,
                channel_id=getattr(msg.channel, "id", None),
                author_id=getattr(msg.author, "id", None),
                kind="message.delete",
                content=None,
                payload=_j({"msg_id": msg.id}),
            )
        except Exception:
            pass

    # ---------- channels ----------

    @commands.Cog.listener()
    async def on_guild_channel_create(self, ch: discord.abc.GuildChannel):
        try:
            g = getattr(ch, "guild", None)
            append_event(
                ts_utc=_now_iso(),
                guild_id=getattr(g, "id", None),
                channel_id=getattr(ch, "id", None),
                author_id=None,
                kind="channel.create",
                content=None,
                payload=_j({"name": getattr(ch, "name", None), "type": getattr(ch, "type", None) and ch.type.name}),
            )
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, ch: discord.abc.GuildChannel):
        try:
            g = getattr(ch, "guild", None)
            append_event(
                ts_utc=_now_iso(),
                guild_id=getattr(g, "id", None),
                channel_id=getattr(ch, "id", None),
                author_id=None,
                kind="channel.delete",
                content=None,
                payload=_j({"name": getattr(ch, "name", None), "type": getattr(ch, "type", None) and ch.type.name}),
            )
        except Exception:
            pass


async def setup(bot: commands.Bot):
    # Make sure the events table exists in the unified audit DB
    ensure_events_schema()
    await bot.add_cog(EventCog(bot))
