from __future__ import annotations

import discord
from discord.ext import commands

from src.db.dal import append_event


class EventCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- member lifecycle ---
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        append_event(
            "member/join",
            str(member.id),
            f"member:{member.id}",
            {"name": str(member), "joined_at": str(member.joined_at)},
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        append_event("member/remove", str(member.id), f"member:{member.id}", {"name": str(member)})

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.nick != after.nick or before.roles != after.roles:
            append_event(
                "member/update",
                str(after.id),
                f"member:{after.id}",
                {
                    "before": {"nick": before.nick, "roles": [r.id for r in before.roles]},
                    "after": {"nick": after.nick, "roles": [r.id for r in after.roles]},
                },
            )

    # --- message audit (lightweight) ---
    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        if msg.author.bot:  # ignore bots (adjust if you want)
            return
        append_event(
            "msg/create",
            str(msg.author.id),
            f"channel:{msg.channel.id}",
            {"channel": msg.channel.id, "content": msg.content[:400], "msg_id": msg.id},
        )

    @commands.Cog.listener()
    async def on_guild_channel_create(self, ch: discord.abc.GuildChannel):
        append_event(
            "channel/create", None, f"channel:{ch.id}", {"name": ch.name, "type": ch.type.name}
        )

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, ch: discord.abc.GuildChannel):
        append_event(
            "channel/delete", None, f"channel:{ch.id}", {"name": ch.name, "type": ch.type.name}
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(EventCog(bot))
