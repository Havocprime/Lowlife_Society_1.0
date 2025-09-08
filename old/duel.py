from __future__ import annotations

import discord
from discord import app_commands

from src.core.duel_core import (
    GrappleState,
    RangeBand,
    allowed_grapple_moves,
    apply_grapple_move,
    compute_attack,
    next_range_after_advance,
    next_range_after_retreat,
)
from src.core.embeds import build_combat_embed

# In-memory duel session by channel
SESSIONS: dict[int, dict] = {}


def _get_session(interaction: discord.Interaction) -> dict | None:
    return SESSIONS.get(interaction.channel_id)


def register_duel(tree: app_commands.CommandTree) -> None:
    @tree.command(name="duel", description="Start a 1v1 duel in this channel.")
    async def duel_cmd(interaction: discord.Interaction, opponent: discord.Member) -> None:
        if opponent.id == interaction.user.id:
            await interaction.response.send_message(
                "Pick an opponent who isn’t you 😅", ephemeral=True
            )
            return
        ch_id = interaction.channel_id
        SESSIONS[ch_id] = {
            "a": interaction.user.id,
            "b": opponent.id,
            "range": RangeBand.NEAR,
            "grapple": GrappleState.NONE,
            "log": ["Duel started."],
        }
        await interaction.response.send_message(embed=build_combat_embed(SESSIONS[ch_id]))

    @tree.command(name="advance", description="Advance toward your opponent.")
    async def advance_cmd(interaction: discord.Interaction) -> None:
        s = _get_session(interaction)
        if not s:
            await interaction.response.send_message("No duel in this channel.", ephemeral=True)
            return
        s["range"] = next_range_after_advance(s["range"])
        s["log"].append("You advance.")
        await interaction.response.send_message(embed=build_combat_embed(s))

    @tree.command(name="retreat", description="Retreat away from your opponent.")
    async def retreat_cmd(interaction: discord.Interaction) -> None:
        s = _get_session(interaction)
        if not s:
            await interaction.response.send_message("No duel in this channel.", ephemeral=True)
            return
        s["range"] = next_range_after_retreat(s["range"])
        s["log"].append("You retreat.")
        await interaction.response.send_message(embed=build_combat_embed(s))

    @tree.command(name="attack", description="Perform a basic attack.")
    async def attack_cmd(interaction: discord.Interaction) -> None:
        s = _get_session(interaction)
        if not s:
            await interaction.response.send_message("No duel in this channel.", ephemeral=True)
            return
        dmg, note = compute_attack(s["range"])
        s["log"].append(f"Attack → {dmg} dmg. {note}")
        await interaction.response.send_message(embed=build_combat_embed(s))

    @tree.command(
        name="grapple",
        description="Attempt a grapple move (contextual: choke / gouge / push).",
    )
    @app_commands.choices(
        move=[
            app_commands.Choice(name="choke", value="choke"),
            app_commands.Choice(name="gouge", value="gouge"),
            app_commands.Choice(name="push", value="push"),
        ]
    )
    async def grapple_cmd(interaction: discord.Interaction, move: app_commands.Choice[str]) -> None:
        s = _get_session(interaction)
        if not s:
            await interaction.response.send_message("No duel in this channel.", ephemeral=True)
            return
        allowed = allowed_grapple_moves(s["grapple"])
        if move.value not in allowed:
            allowed_text = ", ".join(sorted(allowed)) or "none"
            await interaction.response.send_message(
                f"Move **{move.value}** is not allowed right now. Allowed: {allowed_text}.",
                ephemeral=True,
            )
            return
        new_state, note = apply_grapple_move(s["grapple"], move.value)
        s["grapple"] = new_state
        s["log"].append(note)
        await interaction.response.send_message(embed=build_combat_embed(s))
