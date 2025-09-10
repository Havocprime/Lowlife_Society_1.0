from __future__ import annotations

import discord
from discord import app_commands

from src.core.storage import delete_player

# import the duel session table so we can clear a stuck duel in-channel
try:
    from src.bot.duel import SESSIONS as DUEL_SESSIONS
except Exception:
    DUEL_SESSIONS = {}


def register_admin(tree: app_commands.CommandTree) -> None:
    @tree.command(name="ping", description="Bot health-check")
    async def ping_cmd(interaction: discord.Interaction):
        await interaction.response.send_message("pong", ephemeral=True)

    @tree.command(name="wipe_me", description="Delete your test character (ephemeral).")
    async def wipe_me_cmd(interaction: discord.Interaction):
        uid = interaction.user.id
        delete_player(uid)
        await interaction.response.send_message("Wiped your character save.", ephemeral=True)

    @tree.command(name="reset_duel", description="Clear the duel in this channel (admin only).")
    async def reset_duel_cmd(interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Admin only.", ephemeral=True)
            return
        ch_id = interaction.channel_id
        if DUEL_SESSIONS.pop(ch_id, None) is None:
            await interaction.response.send_message("No duel to reset here.", ephemeral=True)
        else:
            await interaction.response.send_message("Duel reset for this channel.", ephemeral=True)
