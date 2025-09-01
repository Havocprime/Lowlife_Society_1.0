from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

DB_PATH = Path("var/db/lowlife.sqlite")

def ensure_user(discord_id: int, display_name: str | None = None) -> int:
    """Return internal users.id, creating the row if needed."""
    with sqlite3.connect(DB_PATH) as cx:
        cx.row_factory = sqlite3.Row
        cur = cx.cursor()
        cur.execute("SELECT id FROM users WHERE discord_id = ?", (discord_id,))
        row = cur.fetchone()
        if row:
            return int(row["id"])
        cur.execute(
            "INSERT INTO users (discord_id, created_at, is_frozen, display_name) VALUES (?,?,0,?)",
            (discord_id, datetime.now(timezone.utc).isoformat(), display_name),
        )
        cx.commit()
        return int(cur.lastrowid)
