# GAME/src/cogs/admin_tools.py  (only the name changed)
from __future__ import annotations
import discord
from discord import app_commands
from discord.ext import commands

class AdminTools(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="freeze", description="Admin: freeze a user (stub)")
    async def freeze(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.send_message(f"(stub) Would freeze {member.mention}", ephemeral=True)

    @app_commands.command(name="invest_basic", description="Admin: basic timeline (stub)")
    async def investigate_basic(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.send_message(f"(stub) Timeline for {member.mention}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminTools(bot))
