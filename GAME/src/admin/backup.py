# GAME/src/admin/backup.py
from __future__ import annotations
import io, zipfile, os, datetime as dt
import discord
from discord import app_commands
from discord.ext import commands

from src.core.settings import SETTINGS
from src.core.ack import ack_once

# Safe import for audit_event (fallback no-op to avoid hard import failures)
try:
    from src.core.audit import audit_event
except Exception:
    def audit_event(*_args, **_kwargs):
        def deco(fn): return fn
        return deco


class BackupCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="db_backup", description="Admin: DM a zipped backup of the game DB.")
    @app_commands.checks.has_permissions(administrator=True)
    @audit_event(action_type="admin.db_backup")
    async def db_backup(self, interaction: discord.Interaction):
        await ack_once(interaction, ephemeral=True)

        db_path = SETTINGS.db_path
        if not os.path.exists(db_path):
            await interaction.followup.send("DB not found.", ephemeral=True)
            return

        # create a ZIP in memory
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.write(db_path, arcname="lowlife.db")
        buf.seek(0)

        ts = dt.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        file = discord.File(buf, filename=f"lowlife-db-{ts}.zip")

        try:
            await interaction.user.send(content="Here is your DB backup:", file=file)
            await interaction.followup.send("Sent you a DM with the backup.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send(
                "I can't DM you. Open your DMs and try again.", ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(BackupCog(bot))
