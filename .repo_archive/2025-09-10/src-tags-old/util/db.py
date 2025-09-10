# src/cogs/util/db.py
from __future__ import annotations
import sqlite3, os
from ...config import DATABASE_PATH

def get_db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn
