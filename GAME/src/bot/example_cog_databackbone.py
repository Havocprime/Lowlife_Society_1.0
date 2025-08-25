
# ─────────────────────────────────────────────────────────────────────────────
# FILE: GAME/src/bot/example_cog_databackbone.py
# PURPOSE: Proof‑of‑life commands hitting the backbone (slash commands stub)
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


class DataBackboneDemo(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="mkchar", description="Create a character for your Discord user")
    async def mkchar(self, interaction: discord.Interaction, name: str):
        user = self.bot.data_ctx.users.get_or_create_by_discord(interaction.user.id)
        char = self.bot.data_ctx.characters.create_for_user(user.id, name)
        await interaction.response.send_message(f"Created character '{char.name}' (id={char.id}) for user={user.id}", ephemeral=True)

    @app_commands.command(name="mychars", description="List your characters")
    async def mychars(self, interaction: discord.Interaction):
        user = self.bot.data_ctx.users.get_or_create_by_discord(interaction.user.id)
        chars = self.bot.data_ctx.characters.by_user(user.id)
        if not chars:
            await interaction.response.send_message("You have no characters yet.", ephemeral=True)
            return
        lines = [f"• {c.name} (id={c.id})"]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(DataBackboneDemo(bot))

