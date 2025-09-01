from __future__ import annotations
from dataclasses import dataclass
from random import randint
from typing import Literal


from .range import Range, HIT_MOD


@dataclass(slots=True)
class Actor:
name: str
acc: int # accuracy stat
evd: int # evasion stat
hp: int


@dataclass(slots=True)
class AttackResult:
hit: bool
roll: int
dc: int
dmg: int




Action = Literal["attack", "advance", "retreat", "wait"]




def attack(attacker: Actor, defender: Actor, distance: Range) -> AttackResult:
roll = randint(1, 100)
dc = 50 + defender.evd - attacker.acc - HIT_MOD.get(distance, 0)
hit = roll >= dc and distance != Range.OUT
dmg = randint(6, 14) if hit else 0
return AttackResult(hit=hit, roll=roll, dc=dc, dmg=dmg)