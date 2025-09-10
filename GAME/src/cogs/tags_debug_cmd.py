# GAME/src/cogs/tags_debug_cmd.py
from __future__ import annotations
import discord
from discord import app_commands
from discord.ext import commands
from src.systems.tags import dal
import sqlite3

class TagDebugCog(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.default_permissions(manage_guild=True)
    @app_commands.command(name="tag_debug", description="Show tag DB path and catalog count.")
    async def tag_debug(self, itx: discord.Interaction):
        with sqlite3.connect(dal.DB_PATH) as con:
            n = con.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
        await itx.response.send_message(
            f"DB_PATH: `{dal.DB_PATH}`\nCatalog rows: **{n}**",
            ephemeral=True
        )

async def setup(bot): await bot.add_cog(TagDebugCog(bot))
