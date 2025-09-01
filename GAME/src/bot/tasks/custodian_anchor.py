from __future__ import annotations
import os, asyncio
import discord
from discord.ext import commands, tasks
from src.core.custodian import ledger

ANCHOR_CHANNEL_ID = int(os.getenv("CUSTODIAN_ANCHOR_CHANNEL_ID", "0") or "0")

class CustodianAnchor(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.anchor_task.start()

    def cog_unload(self):
        self.anchor_task.cancel()

    @tasks.loop(minutes=60)
    async def anchor_task(self):
        if not ANCHOR_CHANNEL_ID:
            return
        try:
            ch = self.bot.get_channel(ANCHOR_CHANNEL_ID)
            if not isinstance(ch, (discord.TextChannel, discord.Thread)):
                return
            summary = ledger.verify_chain(limit=5000)
            broken = summary.get("broken_ids", [])
            status = "OK ✅" if not broken else f"ALERT ❌ broken={len(broken)} (e.g., {broken[:5]})"
            # Post the last chain hash (newest row)
            import sqlite3
            from pathlib import Path
            DBP = Path(__file__).parents[2] / "db" / "audit.sqlite"
            with sqlite3.connect(DBP) as conn:
                row = conn.execute("SELECT id, chain_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
            if row:
                await ch.send(f"⛓️ Custodian anchor — last id `{row[0]}`, hash `{row[1][:16]}…` — {status}")
        except Exception:
            # keep silent; try again next cycle
            pass

    @anchor_task.before_loop
    async def before_anchor_task(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(CustodianAnchor(bot))
