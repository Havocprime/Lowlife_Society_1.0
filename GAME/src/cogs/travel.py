# GAME/src/cogs/travel.py
from __future__ import annotations
import logging
import discord
from discord import app_commands, Interaction
from discord.ext import commands

log = logging.getLogger("travel.cog")

class Travel(commands.Cog):
    """City travel & location system (scaffold)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="travel", description="Open the travel menu.")
    async def travel_root(self, itx: Interaction):
        await itx.response.send_message("🚇 Travel system coming online…", ephemeral=True)

    @app_commands.command(name="travel_go", description="Travel to a district.")
    @app_commands.describe(district="Destination district")
    async def travel_go(self, itx: Interaction, district: str):
        await itx.response.send_message(f"Heading to **{district}**…", ephemeral=True)

    @app_commands.command(name="travel_status", description="Show your current location & travel timers.")
    async def travel_status(self, itx: Interaction):
        await itx.response.send_message("You are in **Downtown**. No active travel timers.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Travel(bot))
