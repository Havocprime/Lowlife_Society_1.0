from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import sqlite3
from typing import Optional


DB_PATH = Path("var/db/lowlife.sqlite")


@dataclass(slots=True)
class LedgerEntry:
id: int | None
ts: datetime
actor_discord_id: int
target_discord_id: Optional[int]
amount: int # positive or negative
memo: str
prev_hash: str | None
hash: str | None




def _iso(dt: datetime) -> str:
return dt.astimezone(timezone.utc).isoformat()




def _calc_hash(ts: str, actor: int, target: Optional[int], amount: int, memo: str, prev: Optional[str]) -> str:
s = f"{ts}|{actor}|{target}|{amount}|{memo}|{prev or ''}"
return sha256(s.encode("utf-8")).hexdigest()




def _ensure_table():
with sqlite3.connect(DB_PATH) as cx:
cx.execute(
"""
CREATE TABLE IF NOT EXISTS econ_ledger (
id INTEGER PRIMARY KEY,
ts TEXT NOT NULL,
actor_discord_id INTEGER NOT NULL,
target_discord_id INTEGER,
amount INTEGER NOT NULL,
memo TEXT NOT NULL,
prev_hash TEXT,
hash TEXT NOT NULL
)
"""
)
cx.commit()




def append(actor: int, target: Optional[int], amount: int, memo: str) -> int:
_ensure_table()
with sqlite3.connect(DB_PATH) as cx:
cx.row_factory = sqlite3.Row
cur = cx.cursor()
cur.execute("SELECT hash FROM econ_ledger ORDER BY id DESC LIMIT 1")
row = cur.fetchone()
prev = row["hash"] if row else None
ts = _iso(datetime.now(timezone.utc))
h = _calc_hash(ts, actor, target, amount, memo, prev)
cur.execute(
"""INSERT INTO econ_ledger (ts, actor_discord_id, target_discord_id, amount, memo, prev_hash, hash)
VALUES (?, ?, ?, ?, ?, ?, ?)""",
(ts, actor, target, amount, memo, prev, h),
)
cx.commit()
return int(cur.lastrowid)