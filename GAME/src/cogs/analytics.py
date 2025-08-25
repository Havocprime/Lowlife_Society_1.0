from __future__ import annotations

import json, sqlite3
from datetime import datetime, timedelta, timezone
from typing import Dict, Tuple

import discord
from discord import app_commands
from discord.ext import commands

from src.core.events import DB_PATH

def _cutoff(days: int | None) -> str | None:
    if not days:
        return None
    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return dt.isoformat().replace("+00:00","Z")

class Analytics(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="topchannels", description="Show most active channels by message count")
    @app_commands.describe(days="Window in days (7, 30, or 0 for all)", limit="How many rows to show")
    async def topchannels(self, interaction: discord.Interaction, days: int = 7, limit: int = 10):
        await interaction.response.defer(ephemeral=True, thinking=True)
        if not interaction.guild:
            await interaction.followup.send("Guild only.", ephemeral=True); return
        cutoff = _cutoff(days if days > 0 else None)

        sql = "SELECT ts_utc, payload FROM events WHERE guild_id=? AND kind='message'"
        args = [int(interaction.guild.id)]
        if cutoff:
            sql += " AND ts_utc>=?"
            args.append(cutoff)

        counts: Dict[int, Tuple[int,str]] = {}
        with sqlite3.connect(DB_PATH) as con:
            for ts, payload in con.execute(sql, args):
                try:
                    data = json.loads(payload or "{}")
                except Exception:
                    data = {}
                cid = int(data.get("channel_id") or 0)
                if not cid:
                    continue
                name = data.get("channel_name") or ""
                n, _ = counts.get(cid, (0, name))
                counts[cid] = (n+1, name or counts.get(cid, (0, ""))[1])

        items = sorted(counts.items(), key=lambda kv: kv[1][0], reverse=True)[:max(1, min(25, limit))]
        if not items:
            await interaction.followup.send("No data in that window.", ephemeral=True); return

        lines = [f"{i+1:>2}. <#{cid}> — **{n}**" for i, (cid, (n, _)) in enumerate(items)]
        title = f"Top Channels (last {days}d)" if days > 0 else "Top Channels (all time)"
        e = discord.Embed(title=title, description="\n".join(lines), color=0x5865F2)
        await interaction.followup.send(embed=e, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Analytics(bot))
