# GAME/src/admin/export.py
from __future__ import annotations

import subprocess
import sys

import discord
from discord import app_commands
from discord.ext import commands

from src.core.perm import Role, require_role


class ExportCmd(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="export", description="Export players or events to CSV.")
    @app_commands.describe(kind="players | events")
    @require_role(Role.ADMIN)
    async def export(self, interaction: discord.Interaction, kind: str):
        await interaction.response.defer(ephemeral=True)
        script = "scripts/export_players.py" if kind == "players" else "scripts/export_events.py"
        try:
            out = subprocess.check_output([sys.executable, script], text=True)
            await interaction.followup.send(f"âœ… Exported: `{out.strip()}`", ephemeral=True)
        except subprocess.CalledProcessError as e:
            await interaction.followup.send(f"âŒ Export failed: {e}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ExportCmd(bot))
