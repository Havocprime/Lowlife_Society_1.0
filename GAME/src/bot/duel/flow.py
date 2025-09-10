# FILE: src/bot/duel/flow.py
from __future__ import annotations

from .battlefield import readable_state
from .state import RANGE_NAMES, DuelState


def render_state(ds: DuelState) -> str:
    head = f"**Round {ds.round_no}** â€” {RANGE_NAMES[ds.current_range]}\n{readable_state(ds)}"
    recent = "\n".join(ds.log[-6:])
    return f"{head}\n\n{recent or '*â€¦*'}"
