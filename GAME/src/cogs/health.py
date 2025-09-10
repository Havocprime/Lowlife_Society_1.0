from __future__ import annotations
import discord
from discord import app_commands
from discord.ext import commands
from pathlib import Path
import sqlite3

from src.core.events import DB_PATH as EVENTS_DB  # your audit/events db
from src.db.users_dal import DB_PATH as GAME_DB

class HealthCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="health", description="Show build info and DB connectivity")
    async def health(self, interaction: discord.Interaction):
        # try a trivial query on the game DB
        ok = True
        detail = "ok"
        try:
            GAME_DB.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(GAME_DB) as cx:
                cx.execute("PRAGMA foreign_keys = ON")
                cx.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('users','items','inventory')")
        except Exception as e:
            ok = False
            detail = f"{type(e).__name__}: {e}"

        txt = (
            f"**Build**: {interaction.client.__class__.__name__}\n"
            f"**Game DB**: `{GAME_DB}` â€” {'OK' if ok else 'ERR'} ({detail})\n"
            f"**Events DB**: `{EVENTS_DB}`\n"
        )
        await interaction.response.send_message(txt, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(HealthCog(bot))
