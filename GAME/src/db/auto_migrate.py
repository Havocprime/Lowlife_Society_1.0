# GAME/src/db/auto_migrate.py
from __future__ import annotations
import os
import sqlite3
from pathlib import Path

# If you store the DB somewhere else, set DB_PATH env; otherwise default below.
DB_PATH = Path(os.getenv("DB_PATH", "GAME/data/lowlife.sqlite")).resolve()

def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _migrations(
          id INTEGER PRIMARY KEY,
          name TEXT NOT NULL,
          applied_at TEXT NOT NULL
        )
    """)

def _next_migration_id(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COALESCE(MAX(id), 0) FROM _migrations").fetchone()
    return int(row[0] or 0) + 1

def _table_has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    names = {r[1] for r in rows}  # (cid, name, type, notnull, dflt_value, pk)
    return column in names

def ensure_items_subcategory(conn: sqlite3.Connection) -> bool:
    """
    Idempotent. Adds items.subcategory if missing, and records a row in _migrations.
    Returns True if it changed anything.
    """
    if not _table_has_column(conn, "items", "subcategory"):
        conn.execute("ALTER TABLE items ADD COLUMN subcategory TEXT")
        _ensure_migrations_table(conn)
        mid = _next_migration_id(conn)
        conn.execute(
            "INSERT INTO _migrations(id, name, applied_at) VALUES (?, ?, datetime('now'))",
            (mid, f"{mid:03d}_items_subcategory"),
        )
        conn.commit()
        return True
    return False

def ensure_all() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(DB_PATH)) as conn:
        changed = ensure_items_subcategory(conn)
        if changed:
            print(f"[auto-migrate] added items.subcategory to {DB_PATH}")
        else:
            print(f"[auto-migrate] OK: items.subcategory already present")
