# =========================================
# File: src/db/schema_version.py
# =========================================
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from .db_path import DB_PATH as DEFAULT_DB_PATH

# Keep this in sync with your latest migration number
LATEST_VERSION = 3

_THIS_DIR = Path(__file__).resolve().parent
_SQL_SCHEMA_V1 = _THIS_DIR / "schema.sql"                  # v0 -> v1
_SQL_V2_FILE   = _THIS_DIR / "0002_txn_idem_unique.sql"    # v1 -> v2 (optional/conditional)

def _exec_sql_file(cx: sqlite3.Connection, sql_path: Path) -> None:
    if not sql_path.exists():
        return
    with sql_path.open("r", encoding="utf-8") as f:
        cx.executescript(f.read())

def _ensure_meta(cx: sqlite3.Connection) -> None:
    cx.execute("""
        CREATE TABLE IF NOT EXISTS schema_meta (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            version INTEGER NOT NULL
        )
    """)
    row = cx.execute("SELECT version FROM schema_meta WHERE id = 1").fetchone()
    if row is None:
        cx.execute("INSERT INTO schema_meta (id, version) VALUES (1, 0)")

def _table_exists(cx: sqlite3.Connection, name: str) -> bool:
    row = cx.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None

def get_version(db_path: str = DEFAULT_DB_PATH) -> int:
    Path(db_path).touch(exist_ok=True)
    with sqlite3.connect(db_path) as cx:
        _ensure_meta(cx)
        (v,) = cx.execute("SELECT version FROM schema_meta WHERE id = 1").fetchone()
        return int(v)

def _set_version(cx: sqlite3.Connection, v: int) -> None:
    cx.execute("UPDATE schema_meta SET version = ? WHERE id = 1", (v,))

def ensure_schema(db_path: str = DEFAULT_DB_PATH) -> int:
    Path(db_path).touch(exist_ok=True)
    return get_version(db_path)

def migrate_to_latest(db_path: str = DEFAULT_DB_PATH) -> int:
    """
    Bring DB to LATEST_VERSION. Safe/Idempotent.
    - v0 -> v1 executes schema.sql
    - v1 -> v2 executes 0002_txn_idem_unique.sql only if the referenced
      table(s) exist (e.g., 'transactions'); otherwise we skip and still
      bump the version because this repo variant doesn't need that step.
    - v2 -> v3 is currently a no-op placeholder.
    """
    Path(db_path).touch(exist_ok=True)

    with sqlite3.connect(db_path) as cx:
        # We manage our own transaction boundaries explicitly.
        try:
            cx.execute("BEGIN")
            _ensure_meta(cx)

            (v,) = cx.execute("SELECT version FROM schema_meta WHERE id = 1").fetchone()
            v = int(v)

            # --- v0 -> v1 ---
            if v < 1:
                _exec_sql_file(cx, _SQL_SCHEMA_V1)
                _set_version(cx, 1)
                v = 1

            # --- v1 -> v2 (conditional) ---
            if v < 2:
                # Only run if the migration's target table(s) exist in this repo.
                # The failing line in your run referenced main.transactions, which
                # does not exist here. If it's missing, skip the SQL and bump.
                needs_v2 = _table_exists(cx, "transactions") or _table_exists(cx, "txn")
                if needs_v2:
                    _exec_sql_file(cx, _SQL_V2_FILE)
                _set_version(cx, 2)
                v = 2

            # --- v2 -> v3 ---
            if v < 3:
                # Placeholder for future changes
                _set_version(cx, 3)
                v = 3

            cx.execute("COMMIT")
            return v

        except Exception:
            # Roll back only if a transaction is actually open.
            try:
                if cx.in_transaction:
                    cx.execute("ROLLBACK")
            except Exception:
                pass
            raise