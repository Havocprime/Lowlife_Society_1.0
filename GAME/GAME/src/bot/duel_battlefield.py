# FILE: src/bot/duel_battlefield.py
from __future__ import annotations

import random
from collections import deque
from typing import Deque, Dict, List

from src.core.duel_core import range_label, iclamp

# ---- Glyphs & tiles ----
GLYPH_A = "🔶"
GLYPH_B = "🔷"
GLYPH_A_SMALL = "🔸"   # peek icon when A is inside cover
GLYPH_B_SMALL = "🔹"   # peek icon when B is inside cover
GLYPH_GRAPPLE = "🤼"

# Background (stored internally per cell as a char; rendered to UI as TILE_BG_VIS)
TILE_BG_DAY = "◽"
TILE_BG_NIGHT = "◾"
TILE_BG_VIS = "..."     # what the user sees for any background cell

# Cover & props
TILE_COVER = "🚧"
TILE_DOOR = "🚪"
TILE_BARREL = "🛢️"

# Trails (lightweight markers placed on bottom row on background cells only)
TRAIL_A = "▫"
TRAIL_B = "▪"

# How many historical indices to keep per fighter
TRAIL_LEN = 10


# ---------- Battlefield init / state ----------
def init_battlefield(state) -> None:
    """Create a simple 1D battlefield once per duel (sprinkles of cover/doors/barrels)."""
    if getattr(state, "bf_ready", False):
        return

    is_night = bool(random.getrandbits(1))
    state.map_time = "Night" if is_night else "Day"
    bg = TILE_BG_NIGHT if is_night else TILE_BG_DAY

    segs = state.vis_segments
    tiles: List[str] = [bg] * segs
    used = set()

    def place(sym: str, count_range: tuple[int, int]):
        n = random.randint(*count_range)
        for _ in range(n):
            tries = 0
            while tries < 32:
                idx = random.randint(1, segs - 2)
                if idx not in used:
                    used.add(idx)
                    tiles[idx] = sym
                    break
                tries += 1

    place(TILE_COVER, (3, 6))
    place(TILE_DOOR, (0, 2))
    place(TILE_BARREL, (1, 3))

    state.map_tiles = tiles      # internal per-cell e.g. "◽", "🚧", ...
    state.map_bg = bg            # "◽" or "◾"
    state.bf_ready = True


# ---------- Trails ----------
def init_trails(state) -> None:
    """Ensure trail deques exist per fighter."""
    trails: Dict[int, Deque[int]] = getattr(state, "trails", None)
    if trails is None:
        state.trails = {}
    for uid in (state.a.user_id, state.b.user_id):
        if uid not in state.trails:
            state.trails[uid] = deque(maxlen=TRAIL_LEN)
    # seed current positions once
    for uid in (state.a.user_id, state.b.user_id):
        pos = iclamp(state.pos.get(uid, 0), 0, state.vis_segments - 1)
        record_trail(state, uid, pos)


def record_trail(state, user_id: int, idx: int | None = None) -> None:
    """Append the current (or given) index into the user's trail."""
    if not getattr(state, "bf_ready", False):
        init_battlefield(state)
    if not hasattr(state, "trails"):
        init_trails(state)

    if idx is None:
        idx = iclamp(state.pos.get(user_id, 0), 0, state.vis_segments - 1)

    dq: Deque[int] = state.trails[user_id]
    # avoid duplicating the same cell back-to-back
    if not dq or dq[-1] != idx:
        dq.append(idx)


# ---------- Render ----------
def _is_cover(sym: str) -> bool:
    return sym in {TILE_COVER, TILE_DOOR, TILE_BARREL}


def battlefield_text(state) -> str:
    """
    Returns the two-row battlefield string with label:
      1) TOP row: background (rendered as "...") with *mini* icons (🔸/🔹) ONLY if that fighter is in cover.
      2) BOTTOM row: features + background ("..."). Big icons (🔶/🔷) placed if not in cover.
         Trails (▫ / ▪) appear on background cells only, never overriding cover or players.
    """
    init_battlefield(state)
    segs = state.vis_segments
    tiles = list(getattr(state, "map_tiles", [])) or [getattr(state, "map_bg", TILE_BG_DAY)] * segs
    bg_internal = getattr(state, "map_bg", TILE_BG_DAY)

    top = [TILE_BG_VIS] * segs
    bottom = [TILE_BG_VIS if t == bg_internal else t for t in tiles]

    if state.grappling:
        # Show grapple on bottom; top stays background
        center_left = max(0, (segs // 2) - 1)
        bottom[center_left] = GLYPH_GRAPPLE
        label = "Distance: **Grappling ~1m**"
        return f"{label}\n{''.join(top)}\n{''.join(bottom)}"

    # Normal placement
    a_id, b_id = state.a.user_id, state.b.user_id
    ia = iclamp(state.pos.get(a_id, 1), 0, segs - 1)
    ib = iclamp(state.pos.get(b_id, segs - 2), 0, segs - 1)
    if ia == ib:
        ib = iclamp(ib + 1, 0, segs - 1)

    # Player A
    if _is_cover(tiles[ia]):
        top[ia] = GLYPH_A_SMALL
        # bottom keeps cover
    else:
        bottom[ia] = GLYPH_A

    # Player B
    if _is_cover(tiles[ib]):
        top[ib] = GLYPH_B_SMALL
    else:
        bottom[ib] = GLYPH_B

    # Trails: on bottom, only on background cells
    trails = getattr(state, "trails", {})
    if trails:
        for idx in trails.get(a_id, []):
            if bottom[idx] == TILE_BG_VIS:
                bottom[idx] = TRAIL_A
        for idx in trails.get(b_id, []):
            if bottom[idx] == TILE_BG_VIS:
                bottom[idx] = TRAIL_B

    label = f"Distance: **{range_label(state.rngate())}**"
    return f"{label}\n{''.join(top)}\n{''.join(bottom)}"
