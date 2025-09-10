from __future__ import annotations

import discord
from discord import app_commands

from src.core.embeds import build_sheet_embed
from src.core.storage import ensure_player, load_player, save_player


def register_players(tree: app_commands.CommandTree) -> None:
    @tree.command(name="create", description="Create your character.")
    @app_commands.describe(cls="Class/archetype name")
    async def create_cmd(interaction: discord.Interaction, cls: str = "wanderer"):
        uid = interaction.user.id
        if load_player(uid):
            await interaction.response.send_message("You already have a character.", ephemeral=True)
            return
        p = {"cls": cls, "lvl": 1, "hp": 10, "inv": ["fists"], "equipped": "fists"}
        save_player(uid, p)
        await interaction.response.send_message("Character created!", ephemeral=True)

    @tree.command(name="sheet", description="Show a character sheet.")
    async def sheet_cmd(interaction: discord.Interaction, user: discord.Member | None = None):
        target = user or interaction.user
        data = ensure_player(target.id)
        await interaction.response.send_message(embed=build_sheet_embed(data, target.id))
