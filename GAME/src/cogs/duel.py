# GAME/src/cogs/duel.py
from __future__ import annotations
import discord
from discord import app_commands
from discord.ext import commands

from src.combat.engine import simulate
from src.combat.resolver import Actor

class DuelCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="duel_sim", description="Simulate a simple duel (dev tool)")
    async def duel_sim(
        self,
        interaction: discord.Interaction,
        a_acc: int = 50, a_evd: int = 30,
        b_acc: int = 45, b_evd: int = 35,
    ):
        a = Actor(name="A", acc=a_acc, evd=a_evd, hp=60)
        b = Actor(name="B", acc=b_acc, evd=b_evd, hp=60)
        state = simulate(
            a, b,
            ["attack", "advance", "attack", "attack"],
            ["wait", "attack", "retreat", "attack"],
        )
        lines = [f"{x.actor} {x.action} @ {x.distance.name}: {x.detail}" for x in state.log]
        if state.over:
            lines.append(f"WINNER: {state.winner}")
        out = "\n".join(lines)
        if len(out) > 1900:
            out = out[:1900] + "\n…"
        await interaction.response.send_message(out, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(DuelCog(bot))
