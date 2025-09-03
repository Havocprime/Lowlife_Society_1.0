# ===== FILE: GAME/src/db/schema_version.py ===================================
from __future__ import annotations

import sqlite3
from pathlib import Path

from .db_path import DB_PATH  # unchanged in your repo

# Bump this whenever we add a schema change.
EXPECTED_VERSION = 4


def _connect(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    cx = sqlite3.connect(db_path)
    cx.row_factory = sqlite3.Row
    return cx


def get_version(cx: sqlite3.Connection) -> int:
    """Read the schema version from PRAGMA user_version."""
    return int(cx.execute("PRAGMA user_version").fetchone()[0])


def set_version(cx: sqlite3.Connection, version: int) -> None:
    cx.execute(f"PRAGMA user_version = {int(version)}")


def _has_column(cx: sqlite3.Connection, table: str, column: str) -> bool:
    rows = cx.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == column for r in rows)


def _migrate_to_v4_add_equippable(cx: sqlite3.Connection) -> None:
    """
    v4: add items.equippable (INTEGER NOT NULL DEFAULT 0).
    Safe to run more than once.
    """
    # If the items table is missing entirely we do nothing here;
    # your existing bootstrap created it earlier migrations.
    tables = {r[0] for r in cx.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "items" not in tables:
        return

    if not _has_column(cx, "items", "equippable"):
        cx.execute("ALTER TABLE items ADD COLUMN equippable INTEGER NOT NULL DEFAULT 0")
        # Backfill existing rows to default 0 (the ALTER already supplies default for new rows)
        cx.execute("UPDATE items SET equippable = 0 WHERE equippable IS NULL")


def migrate_to_latest(db_path: str = DB_PATH) -> int:
    """
    Apply migrations until EXPECTED_VERSION. Returns the final version.
    """
    with _connect(db_path) as cx:
        cx.execute("BEGIN")
        try:
            v = get_version(cx)
            # Step through versions explicitly so we can add more later.
            if v < 4:
                _migrate_to_v4_add_equippable(cx)
                set_version(cx, 4)
                v = 4
            cx.execute("COMMIT")
        except Exception:
            cx.execute("ROLLBACK")
            raise
        return v


def ensure_schema(db_path: str = DB_PATH) -> int:
    """
    Convenience helper used by verify/migrate scripts: ensures we're at
    least EXPECTED_VERSION by running migrations if needed.
    """
    return migrate_to_latest(db_path)