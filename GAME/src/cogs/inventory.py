from __future__ import annotations
from datetime import datetime, timezone
from discord.ext import commands
from discord import app_commands


from src.inventory.manager import grant_item, inventory_for_user
from src.inventory.serializers import as_embed_lines
from src.models.item import Item, ItemClass


class InventoryCog(commands.Cog):
def __init__(self, bot: commands.Bot):
self.bot = bot


@app_commands.command(name="inv_grant", description="Admin: grant test item")
async def inv_grant(self, interaction, member: str, name: str = "Test Knife"):
# NOTE: member is expected to be a mention or raw ID; convert to int safely in your real code
user_id = int(member.strip("<@!>"))
it = Item(
id=int(datetime.now(timezone.utc).timestamp()),
name=name,
item_class=ItemClass.WEAPON,
created_at=datetime.now(timezone.utc),
bind_on_pickup=False,
durability=100,
pitch_value=50,
rune_value=0,
scrap_value=5,
)
inv_id = grant_item(user_id, it, qty=1, equipped=False)
await interaction.response.send_message(f"Granted {name} to {member} (inv_id={inv_id}).")


@app_commands.command(name="inventory", description="Show your inventory")
async def inventory(self, interaction):
rows = inventory_for_user(interaction.user.id)
lines = as_embed_lines(rows)
await interaction.response.send_message("Your inventory:\n" + ("\n".join(lines) or "(empty)"), ephemeral=True)


async def setup(bot: commands.Bot):
await bot.add_cog(InventoryCog(bot))