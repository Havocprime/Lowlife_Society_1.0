"""
Very simple AI that:
- respects choke/grapple phases
- won't punch across non-melee range
- moves and paints trails across *all* traversed tiles
"""

# FILE: src/bot/duel/ai.py
from __future__ import annotations

import discord
from .state import DuelState

async def maybe_ai_take_turn(interaction: discord.Interaction, ds: DuelState) -> None:
    """
    Minimal no-op so legacy view callbacks don't explode.
    You can expand this later to auto-act when the opponent is the bot.
    """
    return None

import random

from src.core.duel_core import (
    DuelState, rg_to_loadout_range, compute_attack_numbers,
    load_player_stats, armor_kind_from_wclass, apply_armor_reduction,
    record_hit, clamp, iclamp,
)
from .actions import fists_too_far
from .battlefield import update_cover_flags, mark_path_between
from .views import maybe_offer_finisher, hud_update_with_view, hud_update_auto

async def maybe_ai_take_turn(inter, state: DuelState):
    if not state.active or not state.current().is_ai:
        return

    # Present finisher if available and stop
    fin_view = await maybe_offer_finisher(inter, state)
    if fin_view is not None:
        await hud_update_with_view(inter, state, inter.user, fin_view)
        return

    # Pending grenade on AI's tile?
    from .actions import resolve_pending_grenade
    await resolve_pending_grenade(inter, state, state.current())

    ai = state.current()
    foe = state.other()

    # Choke phase
    if state.choking:
        choker, target = state.choking
        if ai.user_id == choker:
            state.breath[target] = iclamp(state.breath.get(target, 50) - random.randint(8, 12), 0, 100)
            state.bloodflow[target] = iclamp(state.bloodflow.get(target, 50) - random.randint(4, 8), 0, 100)
            state.push(f"🤖 {ai.name} tightens the choke.")
            if state.breath[target] <= 0 or state.bloodflow[target] <= 0:
                state.unconscious.add(target)
                record_hit(state, choker, target, "strangled", "")
                winner = state.winner()
                if winner:
                    state.finisher = (winner.user_id, target)
                    msg = "☠️ Your opponent is **unconscious**. Choose their fate."
                    if not state.log_lines or state.log_lines[-1] != msg:
                        state.add_raw(msg)
            state.end_turn()
            await hud_update_auto(inter, state, inter.user)
            return
        else:
            state.push(f"🤖 {ai.name} struggles for air…")
            state.end_turn()
            await hud_update_auto(inter, state, inter.user)
            return

    # Grapple phase
    if state.grappling:
        choice = random.choice(["wrestle", "punch", "break"])
        if choice == "wrestle":
            dmg = random.randint(1, 2)
            foe.hp = max(0, foe.hp - dmg)
            if random.random() < 0.5:
                state.positioning[ai.user_id] = iclamp(state.positioning.get(ai.user_id, 50) + 10, 0, 100)
                state.positioning[foe.user_id] = iclamp(state.positioning.get(foe.user_id, 50) - 10, 0, 100)
                swing = " Position improved."
            else:
                swing = ""
            state.push(f"🤖 {ai.name} wrestles {foe.name} for **{dmg}**.{swing}")
            record_hit(state, ai.user_id, foe.user_id, "wrestle", "")
        elif choice == "punch":
            dmg = random.randint(1, 5)
            foe.hp = max(0, foe.hp - dmg)
            state.push(f"🤖 {ai.name} punches {foe.name} for **{dmg}**.")
            record_hit(state, ai.user_id, foe.user_id, "punch", "Fists")
        else:
            my_pos = state.positioning.get(ai.user_id, 50)
            their_pos = state.positioning.get(foe.user_id, 50)
            p = clamp(0.40 + (my_pos - their_pos) / 200.0, 0.10, 0.90)
            if random.random() <= p:
                state.grappling = False
                state.choking = None
                state.push(f"🤖 {ai.name} breaks free!")
            else:
                state.positioning[ai.user_id] = iclamp(my_pos - 5, 0, 100)
                state.positioning[foe.user_id] = iclamp(their_pos + 5, 0, 100)
                state.push(f"🤖 {ai.name} tries to break free but fails.")
        state.end_turn()
        await hud_update_auto(inter, state, inter.user)
        return

    # Ranged/default phase
    rng_name = rg_to_loadout_range(state.rngate())
    calc = compute_attack_numbers(state.guild_id, ai.user_id, rng_name)
    took_action = False
    if calc.get("ready"):
        weapon_name = calc["weapon"].name
        if weapon_name == "Fists" and fists_too_far(state):
            step = random.randint(1, 2)
            prev = iclamp(state.pos.get(ai.user_id, 0), 0, state.vis_segments - 1)
            state.micro_move(ai.user_id, step)
            cur = iclamp(state.pos.get(ai.user_id, 0), 0, state.vis_segments - 1)
            mark_path_between(state, ai.user_id, prev, cur)
            update_cover_flags(state)
            state.push(f"🤖 {ai.name} advances **{step} meters**.")
            took_action = True
        else:
            p = float(calc["accuracy"]) / 100.0
            if foe.user_id in state.in_cover:
                p *= (1.0 - float(state.cover_pct.get(foe.user_id, 0)) / 100.0)
            if foe.user_id in state.hidden:
                p = 0.0
            atk = load_player_stats(ai.user_id); dfn = load_player_stats(foe.user_id)
            p += 0.015 * (atk["combat"] - dfn["combat"]) + 0.010 * (atk["fitness"] - dfn["fitness"])
            p = clamp(p, 0.00, 0.98)
            if random.random() <= p:
                base = int(calc["damage"])
                kind = armor_kind_from_wclass(calc["weapon"].wclass)
                final, mit = apply_armor_reduction(state, foe.user_id, dfn, base, kind)
                foe.hp = max(0, foe.hp - final)
                if weapon_name == "Fists":
                    state.push(f"🤖 {ai.name} **swings** and hits {foe.name} for **{final}**{f' (−{mit} armor)' if mit>0 else ''}.")
                else:
                    state.push(f"🤖 {ai.name} fires **{calc['weapon'].name}** and hits {foe.name} for **{final}**{f' (−{mit} armor)' if mit>0 else ''}.")
                record_hit(state, ai.user_id, foe.user_id, "shot", calc["weapon"].name)
                took_action = True
            else:
                if weapon_name == "Fists":
                    state.push(f"🤖 {ai.name} **swings** and **misses**.")
                else:
                    state.push(f"🤖 {ai.name} fires and **misses**.")
                took_action = True

    if not took_action:
        step = random.randint(1, 2)
        prev = iclamp(state.pos.get(ai.user_id, 0), 0, state.vis_segments - 1)
        state.micro_move(ai.user_id, step)
        cur = iclamp(state.pos.get(ai.user_id, 0), 0, state.vis_segments - 1)
        mark_path_between(state, ai.user_id, prev, cur)
        update_cover_flags(state)
        state.push(f"🤖 {ai.name} advances **{step} meters**.")

    state.end_turn()
    await hud_update_auto(inter, state, inter.user)
