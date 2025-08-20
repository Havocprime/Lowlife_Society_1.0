

# ========================================
# FILE: GAME/src/bot/inventory_cmds.py
# ========================================
from __future__ import annotations
import discord
from discord import app_commands


INVENTORY: dict[int, list[str]] = {}




def register_inventory_commands(tree: app_commands.CommandTree):
@tree.command(name="inventory", description="Show your inventory (ephemeral).")
async def inv_cmd(interaction: discord.Interaction):
items = INVENTORY.get(interaction.user.id, [])
text = ", ".join(items) if items else "(empty)"
await interaction.response.send_message(f"Inventory: {text}", ephemeral=True)

