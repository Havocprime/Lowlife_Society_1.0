# GAME/src/cogs/admin_items.py
from __future__ import annotations

import os
import asyncio
import discord
from discord import app_commands
from discord.ext import commands

from src.inventory.manager import restore_item_by_name, purge_item_by_name, list_item_name_status, list_item_names


class AdminItems(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # You can gate with your own admin check here if desired.
    def _is_admin(self, interaction: discord.Interaction) -> bool:
        return bool(interaction.user.guild_permissions.manage_guild)

    # --- nuke legacy /createitem no matter where it was registered ---
    async def cog_load(self) -> None:
        async def _remove():
            await self.bot.wait_until_ready()
            tree = self.bot.tree
            try:
                # Remove global command named "createitem" if present
                tree.remove_command("createitem", guild=None)
            except Exception:
                pass
            try:
                # Also remove a dev-guild scoped version if you use one
                dev_id = int(os.getenv("DEV_GUILD_ID", "0")) or None
                if dev_id:
                    tree.remove_command("createitem", guild=discord.Object(id=dev_id))
            except Exception:
                pass
            # NOTE: After startup, run your normal /sync so Discord prunes it remotely.

        asyncio.create_task(_remove())

    # =========================
    # Restore / Purge
    # =========================
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

    @item_restore.autocomplete("name")
    async def _ac_restore_name(self, interaction: discord.Interaction, current: str):
        rows = list_item_name_status(current or "", limit=25)
        names = [r["name"] for r in rows if r.get("deleted")]
        return [app_commands.Choice(name=n, value=n) for n in names]

    @app_commands.command(name="item_purge", description="Hard-delete an item by name (no undo)")
    @app_commands.describe(name="Exact name to purge (case-insensitive)")
    async def item_purge(self, interaction: discord.Interaction, name: str):
        if not self._is_admin(interaction):
            return await interaction.response.send_message("Nope.", ephemeral=True)

        await interaction.response.defer(ephemeral=True, thinking=True)
        n = purge_item_by_name(name)
        await interaction.followup.send(f"🗑️ Purged **{name}** ({n} row(s)).", ephemeral=True)

    @item_purge.autocomplete("name")
    async def _ac_purge_name(self, interaction: discord.Interaction, current: str):
        names = list_item_names(current or "", limit=25, include_deleted=True)
        return [app_commands.Choice(name=n, value=n) for n in names]


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminItems(bot))
