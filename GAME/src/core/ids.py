# ─────────────────────────────────────────────────────────────────────────────
# FILE: GAME/src/core/ids.py
# PURPOSE: Snowflake‑ish ID generator + mint_id & roll_seed helpers
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations


import os, time, threading, random
from typing import Literal


# Epoch: 2025‑08‑01 00:00:00 UTC (arbitrary, stable)
_EPOCH_MS = int(1754006400 * 1000)


_seq_lock = threading.Lock()
_seq = 0
_machine = (os.getpid() & 0x1F) # 5 bits from PID (dev‑friendly, not security)


IdKind = Literal["user", "character", "item", "skill", "txn"]




def _next_seq() -> int:
global _seq
with _seq_lock:
_seq = (_seq + 1) & 0xFFF # 12 bits
return _seq




def new_id(kind: IdKind) -> int:
"""64‑bit snowflake‑ish: [41 bits ts | 5 bits machine | 6 bits kind | 12 bits seq]
kind_map = stable map from string → 6 bits. Not cryptographically unique.
"""
kind_map = {
"user": 0,
"character": 1,
"item": 2,
"skill": 3,
"txn": 4,
}
kind_bits = kind_map.get(kind, 63) & 0x3F
ts_ms = int(time.time() * 1000) - _EPOCH_MS
seq = _next_seq()
val = ((ts_ms & ((1 << 41) - 1)) << (5 + 6 + 12)) | ((_machine & 0x1F) << (6 + 12)) | (kind_bits << 12) | seq
return val




def new_mint_id() -> int:
return new_id("item")




def new_roll_seed() -> int:
return random.randint(0, 9999)

