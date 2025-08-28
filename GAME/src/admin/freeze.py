from __future__ import annotations
import discord
from discord import app_commands
from discord.ext import commands
from src.core.perm import require_role, Role
from src.core.ops import FREEZE_FLAG, econ_frozen

class Freeze(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="freeze_econ", description="ADMIN: toggle economy writes.")
    @app_commands.describe(mode="'on' or 'off'")
    @require_role(Role.ADMIN)
    async def freeze(self, interaction: discord.Interaction, mode: str):
        m = mode.lower().strip()
        if m == "on":
            FREEZE_FLAG.parent.mkdir(parents=True, exist_ok=True)
            FREEZE_FLAG.touch()
            await interaction.response.send_message("🧊 Economy **frozen**.", ephemeral=True)
        elif m == "off":
            if FREEZE_FLAG.exists():
                FREEZE_FLAG.unlink()
            await interaction.response.send_message("🔥 Economy **thawed**.", ephemeral=True)
        else:
            await interaction.response.send_message(
                f"Mode must be 'on' or 'off' (currently: {'on' if econ_frozen() else 'off'}).",
                ephemeral=True,
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(Freeze(bot))
