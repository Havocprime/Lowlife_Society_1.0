"""
Command group wiring, state registry, and simple setup utilities.
This is the only module your bot needs to import (`register_duel`).
"""

from __future__ import annotations
import asyncio
import logging
import random
from typing import Optional, Tuple, Dict

import discord
from discord import app_commands

from src.core.duel_core import (
    DuelState, Combatant, load_player_stats, clamp,
)
from .ui import player_hud_embed, post_public_banner
from .battlefield import init_battlefield
from .views import make_view, hud_update_auto, safe_reply
from .constants import LOG_VISIBLE

log = logging.getLogger("duel.registry")

# ---------- Seed combat log & initiative ----------

def _seed_combat_log(state: DuelState, rows: int = LOG_VISIBLE - 1, fill_char: str = "◐") -> None:
    if not state.log_lines:
        state.log_lines.extend([fill_char] * rows)
        state.full_log_lines.extend([fill_char] * rows)

def _decide_initiative(state: DuelState) -> None:
    a, b = state.players()
    sa, sb = load_player_stats(a.user_id), load_player_stats(b.user_id)
    p_a = clamp(0.5 + 0.02 * (sa["combat"] - sb["combat"]) + 0.01 * (sa["fitness"] - sb["fitness"]), 0.10, 0.90)
    roll = random.random()
    first = a if roll <= p_a else b
    state.turn_id = 0 if first is a else 1
    pa = round(p_a * 100); pb = 100 - pa
    state.initiative_note = f"a{pa}_[b{pb}]"
    state.log_lines.append(f"Initiative: {a.name} {pa}% vs {b.name} {pb}% → **{first.name}** starts.")
    state.full_log_lines.append(state.log_lines[-1])

# ---------- per-channel registry ----------

_DUEL_BY_CHANNEL: Dict[Tuple[int, int], DuelState] = {}

def _chan_key(inter: discord.Interaction) -> Tuple[int, int]:
    return (inter.guild_id or 0, inter.channel_id)

def _end_duel_in_channel(state: DuelState | None):
    if not state: return
    _DUEL_BY_CHANNEL.pop((state.guild_id, state.channel_id), None)

# ---------- App commands ----------

duel_group = app_commands.Group(name="duel", description="Duel commands")

@duel_group.command(name="start", description="Start a duel with another player")
async def duel_start(inter: discord.Interaction, opponent: discord.Member):
    me = inter.user
    if opponent.id == me.id:
        await safe_reply(inter, content="You can’t duel yourself. Try `/duel ai` to test against a bot.", ephemeral=True)
        return

    key = _chan_key(inter)
    if key in _DUEL_BY_CHANNEL and _DUEL_BY_CHANNEL[key].active:
        await safe_reply(inter, content="There’s already an active duel in this channel. Use `/duel reset` first.", ephemeral=True)
        return

    a = Combatant(user_id=me.id, name=me.display_name)
    b = Combatant(user_id=opponent.id, name=opponent.display_name)
    state = DuelState(guild_id=key[0], channel_id=key[1], a=a, b=b)

    _seed_combat_log(state); _decide_initiative(state)
    init_battlefield(state)
    _DUEL_BY_CHANNEL[key] = state

    await post_public_banner(inter, state)
    await safe_reply(inter, embed=player_hud_embed(state, me), view=make_view(state, inter.client, me.id), ephemeral=False)

@duel_group.command(name="ai", description="Start a duel against an AI Defender")
async def duel_ai(inter: discord.Interaction):
    from .ai import maybe_ai_take_turn
    me = inter.user
    key = _chan_key(inter)
    if key in _DUEL_BY_CHANNEL and _DUEL_BY_CHANNEL[key].active:
        await safe_reply(inter, content="There’s already an active duel in this channel. Use `/duel reset` first.", ephemeral=True)
        return

    a = Combatant(user_id=me.id, name=me.display_name)
    b = Combatant(user_id=10_000_000_000 + (me.id % 1_000_000_000), name="AI Defender", is_ai=True)
    state = DuelState(guild_id=key[0], channel_id=key[1], a=a, b=b)

    _seed_combat_log(state); _decide_initiative(state)
    init_battlefield(state)
    _DUEL_BY_CHANNEL[key] = state

    await post_public_banner(inter, state)
    await safe_reply(inter, embed=player_hud_embed(state, me), view=make_view(state, inter.client, me.id), ephemeral=False)

    if state.active and state.current().is_ai:
        await asyncio.sleep(0.3)
        await maybe_ai_take_turn(inter, state)

@duel_group.command(name="reset", description="Force end the duel in this channel")
async def duel_reset(inter: discord.Interaction):
    state = _DUEL_BY_CHANNEL.get(_chan_key(inter))
    if not state:
        await safe_reply(inter, content="No duel to reset here.", ephemeral=True)
        return
    state.finisher = None
    state.active = False
    state.push("⛔ Duel reset.")
    _end_duel_in_channel(state)
    try:
        from .ui import update_public_result
        await update_public_result(inter, state, "Aborted.")
    except Exception:
        pass
    await safe_reply(inter, embed=player_hud_embed(state, inter.user), ephemeral=True)

def register_duel(tree: app_commands.CommandTree):
    # Remove any previously-registered /duel command that's not a group
    try:
        existing = tree.get_command("duel", type=discord.AppCommandType.chat_input, guild=None)
        if existing and not isinstance(existing, app_commands.Group):
            tree.remove_command(existing.name, type=discord.AppCommandType.chat_input, guild=None)
    except Exception as e:
        logging.getLogger("duel").warning("Couldn't remove old /duel: %s", e)
    tree.add_command(duel_group)
