from __future__ import annotations
import discord
from discord import app_commands
from src.core.duel_core import (
    RangeBand, GrappleState,
    next_range_after_advance, next_range_after_retreat,
    compute_attack, allowed_grapple_moves, apply_grapple_move,
)
from src.core.embeds import build_combat_embed
from src.core.storage import ensure_player

SESSIONS: dict[int, dict] = {}

def _get_session(interaction: discord.Interaction) -> dict | None:
    return SESSIONS.get(interaction.channel_id)

def _ensure_participant(inter, s) -> bool:
    if inter.user.id not in (s["a"], s["b"]):
        # Not part of this duel
        return False
    return True

def register_duel(tree: app_commands.CommandTree) -> None:
    @tree.command(name="duel", description="Start a 1v1 duel in this channel.")
    async def duel_cmd(interaction: discord.Interaction, opponent: discord.Member) -> None:
        if opponent.id == interaction.user.id:
            await interaction.response.send_message("Pick an opponent who isn’t you 😅", ephemeral=True); return
        ch_id = interaction.channel_id
        a, b = interaction.user.id, opponent.id
        pa = ensure_player(a)
        pb = ensure_player(b)
        SESSIONS[ch_id] = {
            "a": a, "b": b,
            "range": RangeBand.NEAR,
            "grapple": GrappleState.NONE,
            "hp": {a: int(pa.get("hp", 10)), b: int(pb.get("hp", 10))},
            "log": ["Duel started."],
        }
        await interaction.response.send_message(embed=build_combat_embed(SESSIONS[ch_id]))

    @tree.command(name="advance", description="Advance toward your opponent.")
    async def advance_cmd(interaction: discord.Interaction) -> None:
        s = _get_session(interaction)
        if not s: await interaction.response.send_message("No duel in this channel.", ephemeral=True); return
        if not _ensure_participant(interaction, s): await interaction.response.send_message("You’re not in this duel.", ephemeral=True); return
        s["range"] = next_range_after_advance(s["range"])
        s["log"].append(f"<@{interaction.user.id}> advances.")
        await interaction.response.send_message(embed=build_combat_embed(s))

    @tree.command(name="retreat", description="Retreat away from your opponent.")
    async def retreat_cmd(interaction: discord.Interaction) -> None:
        s = _get_session(interaction)
        if not s: await interaction.response.send_message("No duel in this channel.", ephemeral=True); return
        if not _ensure_participant(interaction, s): await interaction.response.send_message("You’re not in this duel.", ephemeral=True); return
        s["range"] = next_range_after_retreat(s["range"])
        s["log"].append(f"<@{interaction.user.id}> retreats.")
        await interaction.response.send_message(embed=build_combat_embed(s))

    @tree.command(name="attack", description="Perform a basic attack.")
    async def attack_cmd(interaction: discord.Interaction) -> None:
        s = _get_session(interaction)
        if not s: await interaction.response.send_message("No duel in this channel.", ephemeral=True); return
        if not _ensure_participant(interaction, s): await interaction.response.send_message("You’re not in this duel.", ephemeral=True); return

        attacker = interaction.user.id
        defender = s["b"] if attacker == s["a"] else s["a"]
        weapon = ensure_player(attacker).get("equipped", "fists")
        dmg, _ = compute_attack(s["range"], weapon)
        s["hp"][defender] = max(0, int(s["hp"][defender]) - int(dmg))
        s["log"].append(f"<@{attacker}> hits <@{defender}> for **{dmg}** with **{weapon}**.")

        if s["hp"][defender] <= 0:
            s["log"].append(f"<@{attacker}> **WINS!**")
            await interaction.response.send_message(embed=build_combat_embed(s))
            SESSIONS.pop(interaction.channel_id, None)
            return

        await interaction.response.send_message(embed=build_combat_embed(s))

    @tree.command(name="grapple", description="Attempt a grapple move (choke/gouge/push).")
    @app_commands.choices(move=[
        app_commands.Choice(name="choke", value="choke"),
        app_commands.Choice(name="gouge", value="gouge"),
        app_commands.Choice(name="push", value="push"),
    ])
    async def grapple_cmd(interaction: discord.Interaction, move: app_commands.Choice[str]) -> None:
        s = _get_session(interaction)
        if not s: await interaction.response.send_message("No duel in this channel.", ephemeral=True); return
        if not _ensure_participant(interaction, s): await interaction.response.send_message("You’re not in this duel.", ephemeral=True); return

        allowed = allowed_grapple_moves(s["grapple"])
        if move.value not in allowed:
            await interaction.response.send_message(f"Move **{move.value}** is not allowed now.", ephemeral=True); return

        new_state, note = apply_grapple_move(s["grapple"], move.value)
        s["grapple"] = new_state
        s["log"].append(note)
        await interaction.response.send_message(embed=build_combat_embed(s))
