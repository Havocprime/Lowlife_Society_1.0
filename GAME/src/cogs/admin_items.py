from __future__ import annotations
import discord
from discord import app_commands
from discord.ext import commands

from src.inventory.manager import restore_item_by_name, purge_item_by_name, list_item_name_status

class AdminItems(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # You can gate with your own admin check here if desired.
    def _is_admin(self, interaction: discord.Interaction) -> bool:
        return bool(interaction.user.guild_permissions.manage_guild)

    @app_commands.command(name="item_restore", description="Restore a soft-deleted item by name")
    @app_commands.describe(name="Name of the item (deleted items appear in autocomplete)")
    async def item_restore(self, interaction: discord.Interaction, name: str):
        if not self._is_admin(interaction):
            return await interaction.response.send_message("Nope.", ephemeral=True)

        await interaction.response.defer(ephemeral=True, thinking=True)
        ok = restore_item_by_name(name)
        if ok:
            await interaction.followup.send(f"✅ Restored **{name}**.", ephemeral=True)
        else:
            await interaction.followup.send(f"ℹ️ '{name}' was not deleted or not found.", ephemeral=True)

    @app_commands.command(name="item_purge", description="Hard-delete an item by name (no undo)")
    @app_commands.describe(name="Exact name to purge (case-insensitive)")
    async def item_purge(self, interaction: discord.Interaction, name: str):
        if not self._is_admin(interaction):
            return await interaction.response.send_message("Nope.", ephemeral=True)

        await interaction.response.defer(ephemeral=True, thinking=True)
        n = purge_item_by_name(name)
        await interaction.followup.send(f"🗑️ Purged **{name}** ({n} row(s)).", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminItems(bot))
