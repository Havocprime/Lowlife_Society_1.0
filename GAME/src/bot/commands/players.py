from __future__ import annotations

import discord
from discord import app_commands

# Minimal in-memory profiles for MVP
PROFILES: dict[int, dict] = {}


def register(tree: app_commands.CommandTree):
    @tree.command(name="create", description="Create your player profile.")
    async def create_cmd(interaction: discord.Interaction):
        user_id = interaction.user.id
        if user_id not in PROFILES:
            PROFILES[user_id] = {"name": interaction.user.display_name, "xp": 0}
        await interaction.response.send_message(
            f"Profile ready for **{interaction.user.display_name}**."
        )

    @tree.command(name="sheet", description="Show your player sheet.")
    async def sheet_cmd(interaction: discord.Interaction):
        prof = PROFILES.get(interaction.user.id)
        if not prof:
            await interaction.response.send_message("No profile. Use /create first.")
            return
        await interaction.response.send_message(f"**{prof['name']}** â€” XP: {prof['xp']}")
