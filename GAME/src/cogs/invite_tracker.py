import discord
from discord.ext import commands


class InviteTracker(commands.Cog):
    """Tracks invite uses to attribute referrals at join time."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._cache: dict[int, list[discord.Invite]] = {}

    async def cache_guild(self, guild: discord.Guild):
        try:
            self._cache[guild.id] = await guild.invites()
        except discord.Forbidden:
            self._cache[guild.id] = []
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

    async def diff_invites(self, guild: discord.Guild) -> tuple[str | None, int | None, int | None]:
        before = self._cache.get(guild.id, [])
        try:
            after = await guild.invites()
        except discord.Forbidden:
            return None, None, None
        except Exception:
            return None, None, None

        used = None
        for a in after:
            match = next((b for b in before if b.code == a.code), None)
            if match and a.uses > match.uses:
                used = a
                break
        await self.cache_guild(guild)
        if used:
            inviter_id = used.inviter.id if used.inviter else None
            channel_id = used.channel.id if used.channel else None
            return used.code, inviter_id, channel_id
        return None, None, None


async def setup(bot: commands.Bot):
    await bot.add_cog(InviteTracker(bot))
