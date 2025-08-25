# FILE: src/bot/duel/state.py
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Dict, List, Optional, Tuple

# ---------- Optional providers / graceful fallbacks ----------
try:
    from src.core.combat_loadout import get_combatkit, pick_weapon_for_range, WeaponProfile  # type: ignore
except Exception:  # Minimal safe fallbacks to keep duel working stand-alone
    def get_combatkit(_user_id: int) -> dict:
        return {"weight": 15.0}
    class WeaponProfile:  # very light stub
        name: str = "Fists"
        min_range: str = "CLOSE"
        max_range: str = "CLOSE"
        accuracy: float = 0.65
        dmg: Tuple[int, int] = (4, 7)
    def pick_weapon_for_range(_kit: dict, _gate: str) -> WeaponProfile:
        wp = WeaponProfile()
        if _gate in ("NEAR", "MID", "FAR", "OUT"):
            wp.name, wp.min_range, wp.max_range, wp.accuracy, wp.dmg = "Sidearm", "NEAR", "MID", 0.55, (6, 10)
        return wp

# ============================================================
#                       CORE CONSTANTS
# ============================================================

class RangeGate(IntEnum):
    CLOSE = 0
    NEAR  = 1
    MID   = 2
    FAR   = 3
    OUT   = 4

RANGE_NAMES = {
    RangeGate.CLOSE: "Close",
    RangeGate.NEAR:  "Near",
    RangeGate.MID:   "Mid",
    RangeGate.FAR:   "Far",
    RangeGate.OUT:   "Out-of-Range",
}

# Movement costs (positive drains stamina)
MOVE_COST = {
    "ADVANCE": 6,
    "RETREAT": 6,
    "SPRINT_ADV": 10,   # jump 2 gates forward if light enough
    "SPRINT_RET": 10,   # jump 2 gates back if light enough
}

# Cover values
COVER_NONE = 0
COVER_PARTIAL = 1
COVER_FULL = 2

# Ranged modifiers from cover
COVER_TO_HIT_MOD = {
    COVER_NONE: 0.00,
    COVER_PARTIAL: -0.20,
    COVER_FULL: -0.40,
}

# Block/dodge tuning
BLOCK_REDUCTION = 0.5          # 50% damage reduction on success (consumed on use)
BLOCK_COUNTER_PCT = 0.25       # small counter chance vs light melee
DODGE_BASE = 0.12              # base dodge chance
DODGE_STAM_SCALER = 0.25       # + up to 25% of base with high stamina
DODGE_WEIGHT_SCALER = -0.15    # heavy gear penalizes dodge

# Stamina tuning (0..100 clamp)
STAMINA_BASE = 85
STAMINA_MIN_FOR_SPRINT = 35
STAMINA_REGEN_PER_TURN = 5

# Grenade / AOE
GRENADE_HIT_PCT = 0.75
GRENADE_DMG = (14, 22)
GRENADE_DESTROY_PARTIAL_PCT = 0.35

# Grapple / choke timings
CHOKE_DAMAGE = (3, 7)
CHOKE_STAM_DRAIN = 7

# Escape system (hooks only, not a full minigame yet)
CONCEALMENT_TICK = 20           # each successful hide/cover tick
WEIGHT_PENALTY_PER_10 = 4       # higher = harder to escape

def clamp(v, lo, hi): return max(lo, min(hi, v))
def roll(minmax: Tuple[int,int]) -> int: return random.randint(minmax[0], minmax[1])
def chance(p: float) -> bool: return random.random() < p

# ============================================================
#                       STATE STRUCTS
# ============================================================

@dataclass
class FighterState:
    user_id: int
    display: str
    stamina: int = STAMINA_BASE
    cover: int = COVER_NONE
    choking_target: Optional[int] = None  # id of the target being choked (if attacking)
    is_choked_by: Optional[int] = None    # id of attacker choking this fighter (if defending)
    concealment: int = 0
    weight: float = 15.0  # from kit; affects dodge/sprint

    # Defensive intents that persist until consumed (one incoming attack)
    status_block: bool = False
    status_dodge: bool = False

@dataclass
class DuelState:
    guild_id: int
    channel_id: int
    p1: FighterState
    p2: FighterState
    current_range: RangeGate = RangeGate.MID
    turn_of: int = 1  # 1 -> p1, 2 -> p2
    round_no: int = 1
    log: List[str] = field(default_factory=list)
    active: bool = True

    def fighter(self, idx: int) -> FighterState:
        return self.p1 if idx == 1 else self.p2
    def foe(self, idx: int) -> FighterState:
        return self.p2 if idx == 1 else self.p1

# In-memory registry (single duel per channel)
DUELS: Dict[int, DuelState] = {}
