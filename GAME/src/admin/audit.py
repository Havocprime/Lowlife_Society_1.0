# GAME/src/admin/audit.py
from __future__ import annotations
import discord
from discord import app_commands
from discord.ext import commands
from src.core.audit import audit_event

class AuditCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="audit_recent",
        description="(Legacy) Opens the paged audit viewer to avoid message-length limits."
    )
    @audit_event(action_type="admin.audit_recent_legacy")
    async def audit_recent_legacy(self, interaction: discord.Interaction):
        # keep it super robust: always ephemeral and short
        try:
            await interaction.response.defer(ephemeral=True, thinking=False)
        except Exception:
            pass  # already acknowledged elsewhere

        await interaction.followup.send(
            "Heads-up: **/audit_recent** is legacy and can exceed Discord's 2,000-char limit.\n"
            "Use **/audit_recent_paged** instead (Prev/Next buttons, CSV-safe).",
            ephemeral=True,
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(AuditCog(bot))
