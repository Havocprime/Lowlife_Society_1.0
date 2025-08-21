from __future__ import annotations
import os
from pathlib import Path
import discord
from discord import app_commands

from src.core.embeds import build_update_embed

NOTES_PATH = os.getenv("UPDATES_NOTES_PATH", "GAME/data/updates/notes.md")

def register_updates(tree: app_commands.CommandTree):
    @tree.command(name="update", description="Post an updatelog embed.")
    async def update_cmd(interaction: discord.Interaction):
        notes = ""
        p = Path(NOTES_PATH)
        if p.exists():
            notes = p.read_text(encoding="utf-8")
        embed = build_update_embed(notes)
        await interaction.response.send_message(embed=embed)
