from __future__ import annotations
from discord.ext import commands
from discord import app_commands


class AdminTools(commands.Cog):
def __init__(self, bot: commands.Bot):
self.bot = bot


@app_commands.command(name="freeze", description="Admin: freeze a user")
async def freeze(self, interaction, member: str):
await interaction.response.send_message(f"(stub) Would freeze {member}")


@app_commands.command(name="investigate", description="Admin: basic timeline")
async def investigate(self, interaction, member: str):
await interaction.response.send_message(f"(stub) Timeline for {member}")


async def setup(bot: commands.Bot):
await bot.add_cog(AdminTools(bot))