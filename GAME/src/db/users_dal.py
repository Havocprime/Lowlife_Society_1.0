from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

# Anchor to .../GAME/var/db/lowlife.sqlite regardless of cwd
BASE_DIR = Path(__file__).resolve().parents[2]  # .../GAME
DB_PATH = BASE_DIR / "var" / "db" / "lowlife.sqlite"

def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    cx = sqlite3.connect(DB_PATH)
    cx.execute("PRAGMA foreign_keys = ON")
    return cx

def ensure_user(discord_id: int, display_name: str | None = None) -> int:
    """Return internal users.id for this Discord ID, creating the row if needed."""
    with _connect() as cx:
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
