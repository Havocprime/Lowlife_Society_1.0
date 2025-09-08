# GAME/src/db/conn.py
from __future__ import annotations
import os
import sqlite3
from pathlib import Path

# You can point to an existing DB by setting GAME_DB_PATH
_DEFAULT = Path(__file__).parents[2] / "data" / "game.sqlite"
DB_PATH = Path(os.getenv("GAME_DB_PATH", str(_DEFAULT))).expanduser()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def get_conn() -> sqlite3.Connection:
    cx = sqlite3.connect(DB_PATH)
    cx.row_factory = sqlite3.Row
    return cx
