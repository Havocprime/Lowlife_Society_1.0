# GAME/src/cogs/admin/sync.py
from __future__ import annotations
import asyncio, logging, os, random
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger("admin.sync")
DEV_GUILD_ID = int(os.getenv("DEV_GUILD_ID", "0"))

async def _safe_sync(tree: app_commands.CommandTree, guild: Optional[discord.Object]) -> bool:
    delay = 1.0
    for attempt in range(3):
        try:
            if guild:
                await tree.sync(guild=guild)              # fast + low RL impact
            else:
                await tree.sync()                          # slower, use manually
            return True
        except discord.HTTPException as e:
            # backoff on 429 / general sync hiccups
            jitter = random.uniform(0.5, 1.2)
            wait = min(6.0, delay) + jitter
            log.warning(f"sync attempt {attempt+1} failed: {e}. retrying in {wait:.2f}s")
            await asyncio.sleep(wait)
            delay *= 2
    return False

class SyncCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="sync", description="Manually sync slash commands.")
    @app_commands.checks.has_permissions(administrator=True)
    async def sync(self, itx: discord.Interaction):
        await itx.response.defer(thinking=True, ephemeral=True)
        tree = self.bot.tree
        ok_dev = await _safe_sync(tree, discord.Object(id=DEV_GUILD_ID)) if DEV_GUILD_ID else True
        ok_global = await _safe_sync(tree, None)
        msg = f"Dev guild sync: {'OK' if ok_dev else 'FAIL'} | Global sync: {'OK' if ok_global else 'FAIL'}"
        await itx.followup.send(msg, ephemeral=True)
