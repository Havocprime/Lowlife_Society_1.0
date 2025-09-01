from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
import random

from .range import Range

# Actions the engine understands
Action = Literal["advance", "retreat", "wait", "attack"]

@dataclass(slots=True)
class Actor:
    name: str
    acc: int   # accuracy (0–100-ish)
    evd: int   # evasion (0–100-ish)
    hp: int

@dataclass(slots=True)
class AttackResult:
    hit: bool
    dmg: int
    roll: int
    dc: int

def _range_dc_modifier(r: Range) -> int:
    # lower DC is easier to hit; tweak as desired
    return {
        Range.CLOSE: -5,
        Range.MID:   0,
        Range.FAR:   +5,
        Range.OUT:   +20,  # basically unhittable
    }[r]

def attack(attacker: Actor, defender: Actor, r: Range) -> AttackResult:
    """Very simple attack check: roll vs DC."""
    roll = random.randint(1, 100)
    base_dc = 50
    dc = base_dc + defender.evd // 2 + _range_dc_modifier(r) - attacker.acc // 4
    hit = roll >= dc
    dmg = 0
    if hit:
        # light placeholder damage formula; tune later
        dmg = max(1, 5 + attacker.acc // 10 - defender.evd // 12)
    return AttackResult(hit=hit, dmg=dmg, roll=roll, dc=dc)
