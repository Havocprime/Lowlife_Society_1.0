# GAME/src/cogs/admin_backfill.py
from __future__ import annotations
import traceback
import discord
from discord import app_commands, Interaction
from discord.ext import commands

from src.db.dal import ensure_core_schema, get_or_create_player

class BackfillCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="backfill_accounts", description="[Admin] Create/ensure player accounts for all current members.")
    @app_commands.checks.has_permissions(administrator=True)
    async def backfill_accounts(self, inter: Interaction):
        await inter.response.defer(ephemeral=True)
        guild = inter.guild
        if not guild:
            await inter.followup.send("Run this command inside the LOWLIFE server.", ephemeral=True)
            return

        try:
            ensure_core_schema()

            # Try cache first; if members intent isn't enabled, fallback to fetch
            members = list(guild.members)
            if len(members) <= 1:  # probably missing cache/intent
                members = [m async for m in guild.fetch_members(limit=None)]

            ensured = 0
            for m in members:
                if m.bot:
                    continue
                get_or_create_player(str(m.id), m.name, m.display_name)
                ensured += 1

            await inter.followup.send(f"Backfill complete. Ensured player rows for **{ensured}** members.", ephemeral=True)

        except Exception as e:
            # Surface a short error + keep the full trace in logs
            tb = traceback.format_exc(limit=2)
            await inter.followup.send(f"âš ï¸ Backfill failed: `{e.__class__.__name__}: {e}`\n``{tb}``", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(BackfillCog(bot))
