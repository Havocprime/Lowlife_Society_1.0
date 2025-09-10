# GAME/src/core/ids.py
from __future__ import annotations

import random
import time


def new_id(kind: str = "generic") -> int:
    """
    Monotonic-ish integer ID.
    Uses epoch milliseconds with a small random suffix to avoid collisions.
    """
    return int(time.time() * 1000) * 1000 + random.randint(0, 999)


def new_mint_id() -> int:
    return new_id("item")


def new_roll_seed() -> int:
    return random.randint(0, 9_999)
