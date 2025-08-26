# FILE: src/bot/duel/actions.py
from __future__ import annotations

import math
import random
from typing import Any, Dict, Tuple, Optional

from .state import (
    DuelState, FighterState, RangeGate, RANGE_NAMES,
    CHOKE_DAMAGE, CHOKE_STAM_DRAIN,
    GRENADE_HIT_PCT, GRENADE_DMG, GRENADE_DESTROY_PARTIAL_PCT,
    BLOCK_REDUCTION, clamp, roll, chance,
    get_combatkit, pick_weapon_for_range,
    COVER_NONE, COVER_PARTIAL, COVER_FULL
)
from .battlefield import to_hit, dodge_chance

# -----------------------------------------------------------------------------
# small helpers
# -----------------------------------------------------------------------------

def _log(ds: DuelState, text: str) -> None:
    # tolerate old/new logging styles
    if hasattr(ds, "push") and callable(getattr(ds, "push")):
        ds.push(text)  # type: ignore
    elif hasattr(ds, "add_raw") and callable(getattr(ds, "add_raw")):
        ds.add_raw(text)  # type: ignore
    else:
        ds.log.append(text)

def _apply_damage(f: FighterState, dmg: int) -> None:
    try:
        f.hp = max(0, int(getattr(f, "hp", 100)) - int(dmg))
    except Exception:
        # keep going even if a custom FighterState has different fields
        pass

def _idx_for_actor(ds: DuelState, actor: FighterState) -> int:
    return 1 if actor is ds.p1 or actor is getattr(ds, "a", None) else 2

def _fighter_by_uid(ds: DuelState, uid: int) -> FighterState:
    a = getattr(ds, "a", ds.p1)
    b = getattr(ds, "b", ds.p2)
    return a if a.user_id == uid else b

# ----------------------- Defensive Intents -----------------------

def act_block(ds: DuelState, idx: int) -> str:
    f = ds.fighter(idx)
    f.stamina = clamp(f.stamina - 4, 0, 100)
    f.status_block = True
    f.status_dodge = False
    return f"{f.display} raises a **block**."

def act_dodge(ds: DuelState, idx: int) -> str:
    f = ds.fighter(idx)
    f.stamina = clamp(f.stamina - 6, 0, 100)
    f.status_dodge = True
    f.status_block = False
    return f"{f.display} prepares to **dodge**."

# ----------------------- Attacks -----------------------

def _consume_defense_text(defender: FighterState, used: str) -> str:
    defender.status_block = False
    defender.status_dodge = False
    return used

def act_punch(ds: DuelState, idx: int) -> str:
    if ds.current_range != RangeGate.CLOSE:
        return f"❌ Punch requires **Close** range."
    atk, dfn = ds.fighter(idx), ds.foe(idx)

    # Defender may dodge?
    if dfn.status_dodge and chance(dodge_chance(dfn)):
        return _consume_defense_text(dfn, f"{atk.display} throws a **punch**, but {dfn.display} **dodges**.")

    dmg = roll((5, 9))

    extra = ""
    if dfn.status_block:
        dmg = math.floor(dmg * (1.0 - BLOCK_REDUCTION))
        extra = " (blocked)"
        _consume_defense_text(dfn, "")

    _apply_damage(dfn, dmg)
    atk.stamina = clamp(atk.stamina - 5, 0, 100)
    return f"{atk.display} **punches** {dfn.display} for **{dmg}**{extra}."

def act_shoot(ds: DuelState, idx: int) -> str:
    atk, dfn = ds.fighter(idx), ds.foe(idx)
    gate = {RangeGate.CLOSE:"CLOSE", RangeGate.NEAR:"NEAR", RangeGate.MID:"MID",
            RangeGate.FAR:"FAR", RangeGate.OUT:"OUT"}[ds.current_range]

    if gate == "OUT":
        return f"❌ Target is **out of range**."

    kit = get_combatkit(atk.user_id)
    wp = pick_weapon_for_range(kit, gate)

    if dfn.status_dodge and chance(dodge_chance(dfn)):
        _consume_defense_text(dfn, "")
        atk.stamina = clamp(atk.stamina - 7, 0, 100)
        return f"{atk.display} fires **{getattr(wp,'name','weapon')}**, but {dfn.display} **dodges**."

    hit = chance(to_hit(getattr(wp, "accuracy", 0.55), dfn.cover, atk.stamina))
    atk.stamina = clamp(atk.stamina - 7, 0, 100)
    if not hit:
        return f"{atk.display} fires **{getattr(wp,'name','weapon')}** and **misses**."

    dmg = roll(getattr(wp, "dmg", (6, 10)))

    if dfn.status_block:
        dmg = math.floor(dmg * (1.0 - BLOCK_REDUCTION))
        _consume_defense_text(dfn, "")
        _apply_damage(dfn, dmg)
        return f"{atk.display} **hits** with {getattr(wp,'name','weapon')} for **{dmg}** (blocked)."

    _apply_damage(dfn, dmg)
    return f"{atk.display} **hits** with {getattr(wp,'name','weapon')} for **{dmg}**."

def act_grenade(ds: DuelState, idx: int) -> str:
    atk, dfn = ds.fighter(idx), ds.foe(idx)
    atk.stamina = clamp(atk.stamina - 10, 0, 100)
    if chance(GRENADE_HIT_PCT):
        dmg = roll(GRENADE_DMG)
        text = f"{atk.display} **throws a grenade** — it **hits** for **{dmg}**."
        if dfn.cover == COVER_PARTIAL and chance(GRENADE_DESTROY_PARTIAL_PCT):
            dfn.cover = COVER_NONE
            text += " The blast **destroys their cover**!"
        dfn.status_block = False
        dfn.status_dodge = False
        _apply_damage(dfn, dmg)
        return text
    return f"{atk.display} **throws a grenade** — it **misses**."

# ----------------------- Grapple / Choke Flow -----------------------

def act_grapple(ds: DuelState, idx: int) -> str:
    atk, dfn = ds.fighter(idx), ds.foe(idx)
    if ds.current_range != RangeGate.CLOSE:
        return "❌ Grapple requires **Close** range."
    atk.stamina = clamp(atk.stamina - 6, 0, 100)
    if chance(0.6):
        dfn.is_choked_by = atk.user_id
        return f"{atk.display} **secures a grapple** on {dfn.display}."
    return f"{atk.display} attempts to grapple but **fails**."

def act_choke(ds: DuelState, idx: int) -> str:
    atk, dfn = ds.fighter(idx), ds.foe(idx)
    if dfn.is_choked_by != atk.user_id and atk.choking_target != dfn.user_id:
        if ds.current_range != RangeGate.CLOSE or not chance(0.45):
            return "❌ You need a **grapple** (or get lucky at Close) to choke."
    atk.choking_target = dfn.user_id
    dfn.is_choked_by = atk.user_id
    atk.stamina = clamp(atk.stamina - CHOKE_STAM_DRAIN, 0, 100)
    dmg = roll(CHOKE_DAMAGE)
    dfn.status_block = False
    dfn.status_dodge = False
    _apply_damage(dfn, dmg)
    return f"{atk.display} **chokes** {dfn.display} for **{dmg}**. {dfn.display} is struggling to breathe!"

def act_push(ds: DuelState, idx: int) -> str:
    atk, dfn = ds.fighter(idx), ds.foe(idx)
    if atk.choking_target != dfn.user_id:
        return "❌ You can **Push** primarily when you’re controlling (e.g., during choke)."
    atk.choking_target = None
    dfn.is_choked_by = None
    before = ds.current_range
    ds.current_range = RangeGate(min(before + 1, RangeGate.OUT))
    return f"{atk.display} **pushes** {dfn.display} off, breaking the choke ({RANGE_NAMES[before]} → {RANGE_NAMES[ds.current_range]})."

def act_gouge(ds: DuelState, idx: int) -> str:
    vic, atk = ds.fighter(idx), ds.foe(idx)
    if vic.is_choked_by != atk.user_id:
        return "❌ **Gouge** is only available when **you are being choked**."
    if chance(0.65):
        vic.is_choked_by = None
        atk.choking_target = None
        dmg = roll((2, 5))
        _apply_damage(atk, dmg)
        return f"{vic.display} **gouges** to break free, countering for **{dmg}**!"
    return f"{vic.display} tries to **gouge** free but **fails**."

# -----------------------------------------------------------------------------
# Back-compat shims required by the legacy view / AI
# -----------------------------------------------------------------------------

def can_throw_grenade(user_id: int) -> bool:
    try:
        kit = get_combatkit(user_id)
        return int(kit.get("grenades", 0)) > 0
    except Exception:
        return False

def grenade_hit_chance(ds: DuelState, thrower_id: int, target_id: int) -> float:
    # Use the same math as a middling firearm, adjusted by target cover.
    thrower = _fighter_by_uid(ds, thrower_id)
    target = _fighter_by_uid(ds, target_id)
    base_acc = 0.60
    return to_hit(base_acc, getattr(target, "cover", COVER_NONE), getattr(thrower, "stamina", 50))

async def resolve_pending_grenade(interaction, ds: DuelState, actor: FighterState) -> None:
    """
    Old flow: a grenade can 'land' and detonate at the start of the target's turn.
    We emulate that with ds.grenades_pending: { target_id: {from, damage} }.
    """
    pending = getattr(ds, "grenades_pending", {}) or {}
    entry = pending.pop(actor.user_id, None)
    if not entry:
        return
    from_id = int(entry.get("from", 0))
    dmg = int(entry.get("damage", 0))
    src = _fighter_by_uid(ds, from_id)
    _apply_damage(actor, dmg)
    _log(ds, f"💥 The grenade from **{src.display}** detonates near **{actor.display}** for **{dmg}**.")
    ds.grenades_pending = pending  # write back, just in case

def attack_once(ds: DuelState, attacker: FighterState, defender: FighterState) -> None:
    """Single auto-attack used by the legacy 'Attack' button."""
    idx = _idx_for_actor(ds, attacker)
    text: str
    # Prefer shooting unless we're at Close with a small chance to punch
    if ds.current_range == RangeGate.CLOSE and random.random() < 0.35:
        text = act_punch(ds, idx)
    else:
        text = act_shoot(ds, idx)
    _log(ds, text)

def fists_too_far(ds: DuelState, *_, **__) -> bool:
    """Legacy AI helper stub: True when punching is not viable."""
    return ds.current_range != RangeGate.CLOSE
