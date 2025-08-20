# FILE: src/bot/duel/flow.py
from __future__ import annotations

from .state import DuelState, RANGE_NAMES
from .battlefield import readable_state

def render_state(ds: DuelState) -> str:
    head = f"**Round {ds.round_no}** — {RANGE_NAMES[ds.current_range]}\n{readable_state(ds)}"
    recent = "\n".join(ds.log[-6:])
    return f"{head}\n\n{recent or '*…*'}"
