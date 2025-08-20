

# =================================
# FILE: GAME/src/bot/duel.py
# =================================
from __future__ import annotations
import discord
from discord import app_commands


from src.core.duel_core import (
RangeBand, next_range_after_advance, next_range_after_retreat,
compute_attack, GrappleState, resolve_grapple_options
)
from src.core.embeds import build_combat_embed


# Simple in-memory duel session by channel
SESSIONS: dict[int, dict] = {}




def register_duel(tree: app_commands.CommandTree):
@tree.command(name="duel", description="Start a 1v1 duel in this channel.")
async def duel_cmd(interaction: discord.Interaction, opponent: discord.Member):
ch_id = interaction.channel_id
SESSIONS[ch_id] = {
"a": interaction.user.id,
"b": opponent.id,
"range": RangeBand.NEAR,
"grapple": GrappleState.NONE,
"log": ["Duel started."]
}
embed = build_combat_embed(SESSIONS[ch_id])
await interaction.response.send_message(embed=embed)


@tree.command(name="advance", description="Advance toward opponent.")
async def advance_cmd(interaction: discord.Interaction):
s = SESSIONS.get(interaction.channel_id)
if not s:
await interaction.response.send_message("No duel here.")
return
s["range"] = next_range_after_advance(s["range"])
s["log"].append("You advance.")
await interaction.response.send_message(embed=build_combat_embed(s))


@tree.command(name="retreat", description="Retreat from opponent.")
async def retreat_cmd(interaction: discord.Interaction):
s = SESSIONS.get(interaction.channel_id)
if not s:
await interaction.response.send_message("No duel here.")
return
s["range"] = next_range_after_retreat(s["range"])
s["log"].append("You retreat.")
await interaction.response.send_message(embed=build_combat_embed(s))


@tree.command(name="attack", description="Perform a basic attack.")
async def attack_cmd(interaction: discord.Interaction):
s = SESSIONS.get(interaction.channel_id)
if not s:
await interaction.response.send_message("No duel here.")
return
dmg, note = compute_attack(s["range"]) # MVP deterministic
s["log"].append(f"Attack -> {dmg} dmg. {note}")
await interaction.response.send_message(embed=build_combat_embed(s))


@tree.command(name="grapple", description="Contextual grapple options (Choke/Push/Gouge).")
async def grapple_cmd(interaction: discord.Interaction):
s = SESSIONS.get(interaction.channel_id)
if not s:
await interaction.response.send_message("No duel here.")
return
s["grapple"] = resolve_grapple_options(s["grapple"]) # MVP cycle
s["log"].append(f"Grapple state -> {s['grapple'].name}")
await interaction.response.send_message(embed=build_combat_embed(s))

