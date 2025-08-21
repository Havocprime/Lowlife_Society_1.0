from __future__ import annotations
from enum import IntEnum, auto
from .combat_loadout import RangeBand

def next_range_after_advance(r: RangeBand) -> RangeBand:
    return RangeBand(max(RangeBand.CLOSE, r - 1))

def next_range_after_retreat(r: RangeBand) -> RangeBand:
    return RangeBand(min(RangeBand.OOR, r + 1))

def compute_attack(r: RangeBand) -> tuple[int, str]:
    # MVP deterministic damage by range
    base = {RangeBand.CLOSE: 5, RangeBand.NEAR: 3, RangeBand.MID: 2, RangeBand.FAR: 1, RangeBand.OOR: 0}[r]
    note = "solid hit" if base >= 3 else ("glancing" if base > 0 else "miss")
    return base, note

class GrappleState(IntEnum):
    NONE = 0
    CHOKING = auto()
    GOUGE_WINDOW = auto()
    PUSHED = auto()

def resolve_grapple_options(state: GrappleState) -> GrappleState:
    # MVP cyclic logic: NONE -> CHOKING -> GOUGE_WINDOW -> PUSHED -> NONE
    order = [GrappleState.NONE, GrappleState.CHOKING, GrappleState.GOUGE_WINDOW, GrappleState.PUSHED]
    i = order.index(state)
    return order[(i + 1) % len(order)]
