from __future__ import annotations

from enum import IntEnum, auto

from src.core.items import damage_for


class RangeBand(IntEnum):
    CLOSE = 0
    NEAR = 1
    MID = 2
    FAR = 3
    OOR = 4  # Out of Range


def next_range_after_advance(r: RangeBand) -> RangeBand:
    return RangeBand(max(RangeBand.CLOSE, r - 1))


def next_range_after_retreat(r: RangeBand) -> RangeBand:
    return RangeBand(min(RangeBand.OOR, r + 1))


def compute_attack(r: RangeBand, weapon: str = "fists") -> tuple[int, str]:
    dmg = damage_for(weapon, r)
    note = f"with {weapon}"
    return dmg, note


class GrappleState(IntEnum):
    NONE = 0
    CHOKING = auto()
    GOUGE_WINDOW = auto()
    PUSHED = auto()


def allowed_grapple_moves(state: GrappleState) -> set[str]:
    if state == GrappleState.NONE:
        return {"choke"}
    if state == GrappleState.CHOKING:
        return {"gouge"}
    if state == GrappleState.GOUGE_WINDOW:
        return {"push"}
    if state == GrappleState.PUSHED:
        return set()
    return set()


def apply_grapple_move(state: GrappleState, move: str) -> tuple[GrappleState, str]:
    move = move.lower()
    if move not in allowed_grapple_moves(state):
        return state, f"Illegal move **{move}** in state {state.name}."
    if state == GrappleState.NONE and move == "choke":
        return GrappleState.CHOKING, "You apply a choke!"
    if state == GrappleState.CHOKING and move == "gouge":
        return GrappleState.GOUGE_WINDOW, "Defender gouges to break the choke!"
    if state == GrappleState.GOUGE_WINDOW and move == "push":
        return GrappleState.PUSHED, "Defender pushes you off!"
    if state == GrappleState.PUSHED:
        return GrappleState.NONE, "Grapple resets."
    return state, "No change."
