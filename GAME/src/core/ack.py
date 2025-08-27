from __future__ import annotations

import discord


async def ack_once(interaction: discord.Interaction, *, ephemeral: bool = True) -> None:
    """
    Safely acknowledge an interaction exactly once.
    - If not yet acknowledged: defer.
    - If already acknowledged or token is invalid: swallow NotFound.
    """
    if interaction.response.is_done():
        return
    try:
        await interaction.response.defer(ephemeral=ephemeral)
    except discord.NotFound:
        # Token already invalid/used by something else; ignore to avoid crashing.
        pass
