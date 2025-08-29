# GAME/src/admin/audit.py
from __future__ import annotations
import discord
from discord import app_commands
from discord.ext import commands

# Safe import for the decorator (fallback no-op if audit module isn't ready yet)
try:
    from src.core.audit import audit_event
except Exception:
    def audit_event(*_args, **_kwargs):
        def deco(fn): return fn
        return deco


class AuditCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="audit_recent_legacy",
        description="Legacy: prefer /audit_recent_paged.",
    )
    @audit_event(action_type="admin.audit_recent_legacy")
    async def audit_recent_legacy(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True, thinking=False)
        except Exception:
            pass

        await interaction.followup.send(
            "Heads-up: **/audit_recent** is legacy and can exceed Discord’s 2,000-char limit.\n"
            "Use **/audit_recent_paged** instead (Prev/Next buttons, CSV-safe).",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(AuditCog(bot))
