# FILE: src/bot/duel/battlefield.py
from __future__ import annotations

import math
from .state import (
    DuelState, FighterState, RangeGate, RANGE_NAMES,
    MOVE_COST, COVER_NONE, COVER_PARTIAL, COVER_FULL,
    DODGE_BASE, DODGE_STAM_SCALER, DODGE_WEIGHT_SCALER,
    STAMINA_MIN_FOR_SPRINT, STAMINA_REGEN_PER_TURN,
    CONCEALMENT_TICK, COVER_TO_HIT_MOD, clamp
)

def gate_step(g: RangeGate, delta: int) -> RangeGate:
    return RangeGate(clamp(g + delta, RangeGate.CLOSE, RangeGate.OUT))

def readable_state(ds: DuelState) -> str:
    def cov(c):
        return {COVER_NONE:"—", COVER_PARTIAL:"▦", COVER_FULL:"▩"}.get(c, "—")
    return (f"**Range:** {RANGE_NAMES[ds.current_range]}  |  "
            f"**{ds.p1.display}** STAM {ds.p1.stamina} Cover {cov(ds.p1.cover)} "
            f"vs **{ds.p2.display}** STAM {ds.p2.stamina} Cover {cov(ds.p2.cover)}")

def to_hit(base: float, cover: int, stamina: int) -> float:
    # stamina gives slight accuracy boost if high, penalty if low
    stam_adj = (stamina - 50) / 100.0 * 0.08
    val = base + COVER_TO_HIT_MOD[cover] + stam_adj
    return clamp(val, 0.05, 0.95)

def dodge_chance(fs: FighterState) -> float:
    # Weight: -0.15 at +30 weight roughly; Stamina: + up to 25% of base
    w_adj = (fs.weight / 30.0) * DODGE_WEIGHT_SCALER
    s_adj = ((fs.stamina - 50) / 50.0) * DODGE_STAM_SCALER
    val = DODGE_BASE + w_adj + s_adj
    return clamp(val, 0.02, 0.5)

def end_turn_recover(fs: FighterState):
    fs.stamina = clamp(fs.stamina + STAMINA_REGEN_PER_TURN, 0, 100)
    # Defensive intents expire if not consumed by end of opponent's turn
    fs.status_block = False
    fs.status_dodge = False

# ----------------------- Actions: Movement & Cover -----------------------

def act_advance(ds: DuelState, idx: int, sprint: bool=False) -> str:
    f = ds.fighter(idx)
    steps = 2 if sprint and f.stamina >= STAMINA_MIN_FOR_SPRINT and f.weight <= 25 else 1
    cost = MOVE_COST["SPRINT_ADV"] if steps == 2 else MOVE_COST["ADVANCE"]
    f.stamina = clamp(f.stamina - cost, 0, 100)
    before = ds.current_range
    ds.current_range = gate_step(ds.current_range, -steps)
    return f"{f.display} **advances** ({RANGE_NAMES[before]} → {RANGE_NAMES[ds.current_range]})."

def act_retreat(ds: DuelState, idx: int, sprint: bool=False) -> str:
    f = ds.fighter(idx)
    steps = 2 if sprint and f.stamina >= STAMINA_MIN_FOR_SPRINT and f.weight <= 25 else 1
    cost = MOVE_COST["SPRINT_RET"] if steps == 2 else MOVE_COST["RETREAT"]
    f.stamina = clamp(f.stamina - cost, 0, 100)
    before = ds.current_range
    ds.current_range = gate_step(ds.current_range, +steps)
    return f"{f.display} **retreats** ({RANGE_NAMES[before]} → {RANGE_NAMES[ds.current_range]})."

def act_take_cover(ds: DuelState, idx: int, level: int) -> str:
    f = ds.fighter(idx)
    level = clamp(level, COVER_NONE, COVER_FULL)
    prev = f.cover
    f.cover = level
    # concealment rises slightly in cover
    f.concealment = clamp(f.concealment + CONCEALMENT_TICK//2, 0, 100)
    return f"{f.display} moves into **{'FULL' if level==2 else 'PARTIAL'} cover**."

def act_leave_cover(ds: DuelState, idx: int) -> str:
    f = ds.fighter(idx)
    f.cover = COVER_NONE
    return f"{f.display} **leaves cover**."

# --- Back-compat: init_battlefield ------------------------------------------
def init_battlefield(state, *, segments: int = 20) -> None:
    """
    Initialize/normalize distance lane + cover artifacts so legacy callers
    (registry/ui) can import and call this without errors.
    """
    # number of visible segments on the lane
    if not hasattr(state, "vis_segments") or not isinstance(getattr(state, "vis_segments"), int):
        state.vis_segments = int(segments)

    # per-user segment index
    if not hasattr(state, "pos") or not isinstance(getattr(state, "pos"), dict):
        state.pos = {}

    # default endpoints if not already set
    try:
        a_id = state.a.user_id
        b_id = state.b.user_id
        state.pos.setdefault(a_id, 2)
        state.pos.setdefault(b_id, max(0, state.vis_segments - 3))
    except Exception:
        # Be tolerant if state shape changes
        pass

    # optional rendering helpers used by UI/banners; keep them present
    if not hasattr(state, "cover_cells"):
        state.cover_cells = set()
    if not hasattr(state, "path_marks"):
        state.path_marks = set()
    # leave existing maps alone if they already exist
    return None


# --- Back-compat: simple distance lane for UI.banner -------------------------
def compose_distance_rows(state) -> list[str]:
    """
    Minimal, backward-compatible distance rendering for the HUD.
    Returns a single text row representing the lane.
    """
    try:
        segs = int(getattr(state, "vis_segments", 20)) or 20
        pos = getattr(state, "pos", {}) or {}
        a_id = state.a.user_id
        b_id = state.b.user_id
        a_idx = max(0, min(segs - 1, int(pos.get(a_id, 0))))
        b_idx = max(0, min(segs - 1, int(pos.get(b_id, segs - 1))))

        lane = ["·"] * segs
        if a_idx == b_idx:
            lane[a_idx] = "X"
        else:
            lane[a_idx] = "A"
            lane[b_idx] = "B"

        return ["".join(lane)]
    except Exception:
        return []

# --- Back-compat: cover + path helpers used by legacy views -------------------
def update_cover_flags(state) -> None:
    """
    No-op-ish shim so old HUD calls don't crash.
    Ensures the attrs exist; doesn't attempt graphical recalculation.
    """
    # ensure containers exist
    if not hasattr(state, "cover_cells"):
        state.cover_cells = set()
    if not hasattr(state, "cover_level"):
        state.cover_level = {}
    # You can expand this to actually project cover onto cells if desired.
    return None


def mark_path_between(state, user_id: int, start_idx: int, end_idx: int) -> None:
    """
    Record simple path marks between two segment indices for the HUD.
    Safe even if your HUD ignores it.
    """
    if not hasattr(state, "path_marks"):
        state.path_marks = set()

    try:
        a, b = int(start_idx), int(end_idx)
        if a > b:
            a, b = b, a
        for i in range(a, b + 1):
            state.path_marks.add((user_id, i))
    except Exception:
        # Keep this tolerant—never block turn resolution on visuals.
        pass


# --- Back-compat shim for UI/HUD -------------------------------------------------
def compose_distance_rows(state) -> list[str]:
    """
    Minimal, backward-compatible distance rendering for the HUD.
    Returns a list of text rows; UI can join them into the banner.
    We draw a single lane with A/B markers based on state.pos and state.vis_segments.
    """
    try:
        segs = int(getattr(state, "vis_segments", 20)) or 20
        # positions dict: {user_id: segment_index}
        pos = getattr(state, "pos", {}) or {}
        a_id = state.a.user_id
        b_id = state.b.user_id
        a_idx = max(0, min(segs - 1, int(pos.get(a_id, 0))))
        b_idx = max(0, min(segs - 1, int(pos.get(b_id, segs - 1))))

        lane = ["·"] * segs
        if a_idx == b_idx:
            lane[a_idx] = "X"   # same cell
        else:
            lane[a_idx] = "A"
            lane[b_idx] = "B"

        return ["".join(lane)]
    except Exception:
        # Be defensive: never block the HUD if state shape changes
        return []
