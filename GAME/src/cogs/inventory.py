from __future__ import annotations
import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from src.inventory.manager import grant_item, inventory_for_user, set_equipped
from src.inventory.serializers import as_embed_lines
from src.models.item import Item, ItemClass

log = logging.getLogger(__name__)


def _err_msg(e: Exception) -> str:
    return f"{type(e).__name__}: {e}"


class InventoryCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- Commands ----------

    @app_commands.command(name="inv_grant", description="Admin: grant a test item to a member")
    @app_commands.describe(member="Who gets the item?", name="Item name")
    @app_commands.checks.has_permissions(administrator=True)
    async def inv_grant(self, interaction: discord.Interaction, member: discord.Member, name: str = "Test Knife"):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            item = Item(
                id=int(datetime.now(timezone.utc).timestamp()),  # simple unique id for dev
                name=name,
                item_class=ItemClass.WEAPON,
                created_at=datetime.now(timezone.utc),
                bind_on_pickup=False,
                durability=100,
                pitch_value=50,
                rune_value=0,
                scrap_value=5,
            )
            inv_id = grant_item(member.id, item, qty=1, equipped=False)
            await interaction.followup.send(
                f"Granted **{name}** to {member.mention} (inv_id=`{inv_id}`).",
                ephemeral=True,
            )
        except Exception as e:
            log.exception("inv_grant failed")
            await interaction.followup.send(f"Grant failed: `{_err_msg(e)}`", ephemeral=True)

    @app_commands.command(name="inventory", description="Show your inventory")
    async def inventory(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            rows = inventory_for_user(interaction.user.id)
            lines = as_embed_lines(rows)
            txt = "Your inventory:\n" + ("\n".join(lines) if lines else "(empty)")
            await interaction.followup.send(txt, ephemeral=True)
        except Exception as e:
            log.exception("inventory failed")
            await interaction.followup.send(f"Inventory failed: `{_err_msg(e)}`", ephemeral=True)

    @app_commands.command(name="equip", description="Equip an inventory entry by ID")
    async def equip(self, interaction: discord.Interaction, inv_id: int):
        try:
            set_equipped(inv_id, True)
            await interaction.response.send_message(f"Equipped entry `{inv_id}`.", ephemeral=True)
        except Exception as e:
            log.exception("equip failed")
            await interaction.response.send_message(f"Equip failed: `{_err_msg(e)}`", ephemeral=True)

    @app_commands.command(name="unequip", description="Unequip an inventory entry by ID")
    async def unequip(self, interaction: discord.Interaction, inv_id: int):
        try:
            set_equipped(inv_id, False)
            await interaction.response.send_message(f"Unequipped entry `{inv_id}`.", ephemeral=True)
        except Exception as e:
            log.exception("unequip failed")
            await interaction.response.send_message(f"Unequip failed: `{_err_msg(e)}`", ephemeral=True)

    # ---------- Local error hooks (permission errors, etc.) ----------

    @inv_grant.error
    async def _grant_err(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        from discord.app_commands import CheckFailure, CommandInvokeError
        if isinstance(error, CheckFailure):
            return await interaction.response.send_message("You need **Administrator** to use this.", ephemeral=True)
        if isinstance(error, CommandInvokeError) and error.original:
            log.exception("inv_grant invoke error")
            msg = _err_msg(error.original)
        else:
            msg = _err_msg(error)
        # If we didn’t defer yet, use response; otherwise followup.
        if not interaction.response.is_done():
            await interaction.response.send_message(f"Grant failed: `{msg}`", ephemeral=True)
        else:
            await interaction.followup.send(f"Grant failed: `{msg}`", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(InventoryCog(bot))
