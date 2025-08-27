# GAME/src/admin/sync.py
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from src.core.ack import ack_once
from src.core.perm import Role, dangerous_op_cooldown, require_role
from src.core.settings import SETTINGS


class SyncCmd(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="sync",
        description="Sync application commands (scope: guild | global | copy).",
    )
    @require_role(Role.ADMIN)  # our role gate
    @dangerous_op_cooldown("sync", seconds=15)  # simple throttle
    @app_commands.describe(scope="guild | global | copy")
    async def sync(self, interaction: discord.Interaction, scope: str | None = "guild"):
        # acknowledge safely (no double-ack crashes)
        await ack_once(interaction, ephemeral=True)

        where = "unknown"
        try:
            if scope in (None, "", "guild", "~"):
                synced = await self.bot.tree.sync(guild=discord.Object(id=SETTINGS.guild_id))
                where = f"guild {SETTINGS.guild_id}"
            elif scope in ("*", "global"):
                synced = await self.bot.tree.sync()
                where = "global"
            elif scope in ("copy", "^"):
                self.bot.tree.copy_global_to(guild=discord.Object(id=SETTINGS.guild_id))
                synced = await self.bot.tree.sync(guild=discord.Object(id=SETTINGS.guild_id))
                where = f"copied→guild {SETTINGS.guild_id}"
            else:
                synced = []
                where = f"unknown scope '{scope}'"

            await interaction.followup.send(
                f"✅ Synced **{len(synced)}** commands to **{where}**.",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.followup.send(
                f"⚠️ Sync error: `{type(e).__name__}` — {e}",
                ephemeral=True,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(SyncCmd(bot))
