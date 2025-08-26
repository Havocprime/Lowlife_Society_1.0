from __future__ import annotations
import discord
from discord import app_commands
from src.core.storage import get_inventory, get_equipped, equip_item, add_item, ensure_player

def register_inventory(tree: app_commands.CommandTree) -> None:
    @tree.command(name="inventory", description="Show your inventory (ephemeral).")
    async def inventory_cmd(interaction: discord.Interaction):
        uid = interaction.user.id
        ensure_player(uid)
        inv = get_inventory(uid)
        eq = get_equipped(uid)
        txt = f"Equipped: **{eq}**\n" + ("Empty." if not inv else "• " + "\n• ".join(inv))
        await interaction.response.send_message(txt, ephemeral=True)

    @tree.command(name="equip", description="Equip an item from your inventory.")
    async def equip_cmd(interaction: discord.Interaction, item: str):
        uid = interaction.user.id
        ok = equip_item(uid, item)
        if ok:
            await interaction.response.send_message(f"Equipped **{item}**.", ephemeral=True)
        else:
            await interaction.response.send_message(f"You don’t have **{item}**.", ephemeral=True)

    @tree.command(name="give", description="Admin: give an item to a user.")
    async def give_cmd(interaction: discord.Interaction, user: discord.Member, item: str):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Admin only.", ephemeral=True); return
        ok = add_item(user.id, item)
        if ok:
            await interaction.response.send_message(f"Gave **{item}** to {user.mention}.", ephemeral=True)
        else:
            await interaction.response.send_message(f"{user.mention} already has **{item}**.", ephemeral=True)
