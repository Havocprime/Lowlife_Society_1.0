from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class RangeBand(IntEnum):
    CLOSE = 0
    NEAR = 1
    MID = 2
    FAR = 3
    OOR = 4  # Out of Range


@dataclass
class WeaponProfile:
    name: str
    close: int
    near: int
    mid: int
    far: int


DEFAULT_WEAPON = WeaponProfile("Fists", close=5, near=3, mid=1, far=0)
