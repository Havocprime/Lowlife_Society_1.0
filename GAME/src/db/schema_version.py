# GAME/src/db/schema_version.py
from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Iterable
from typing import Union



try:
    # Single source of truth for DB file location
    from src.db.db_path import DB_PATH  # noqa: F401
except Exception:
    DB_PATH = Path("var/db/lowlife.sqlite")

LATEST_VERSION = 3  # bump when we add schema

# ---------- small helpers

def _cx(db_like: Union[str, Path, sqlite3.Connection]):
    if isinstance(db_like, sqlite3.Connection):
        return db_like, False
    return sqlite3.connect(str(db_like)), True

def get_version(db_like: Union[str, Path, sqlite3.Connection]) -> int:
    cx, close = _cx(db_like)
    try:
        cur = cx.execute("PRAGMA user_version;")
        row = cur.fetchone()
        return int(row[0] or 0)
    finally:
        if close:
            cx.close()

def _exec(cx: sqlite3.Connection, sql: str, params: Iterable | None = None) -> None:
    cur = cx.cursor()
    if params is None:
        cur.execute(sql)
    else:
        cur.execute(sql, params)

def _column_exists(cx: sqlite3.Connection, table: str, column: str) -> bool:
    cur = cx.execute(f"PRAGMA table_info({table})")
    return any(r[1] == column for r in cur.fetchall())

def _add_column_if_missing(cx: sqlite3.Connection, table: str, column: str, decl: str) -> None:
    if not _column_exists(cx, table, column):
        _exec(cx, f"ALTER TABLE {table} ADD COLUMN {column} {decl}")

# ---------- version table

def _ensure_version_table(cx: sqlite3.Connection) -> None:
    _exec(
        cx,
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            version INTEGER NOT NULL
        )
        """
    )
    cur = cx.execute("SELECT version FROM schema_version WHERE id = 1")
    row = cur.fetchone()
    if row is None:
        _exec(cx, "INSERT INTO schema_version (id, version) VALUES (1, 0)")

def get_version(db_path: Path) -> int:
    with sqlite3.connect(db_path) as cx:
        _ensure_version_table(cx)
        cur = cx.execute("SELECT version FROM schema_version WHERE id = 1")
        (v,) = cur.fetchone()
        return int(v)

def _set_version(cx: sqlite3.Connection, v: int) -> None:
    _exec(cx, "UPDATE schema_version SET version = ? WHERE id = 1", (v,))

# ---------- base schema + migrations

def _create_base(cx: sqlite3.Connection) -> None:
    # Minimal tables used by game features
    _exec(
        cx,
        """
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            item_class TEXT NOT NULL,
            created_at TEXT NOT NULL,
            bind_on_pickup INTEGER NOT NULL DEFAULT 0,
            durability INTEGER NOT NULL DEFAULT 0,
            pitch_value INTEGER NOT NULL DEFAULT 0,
            rune_value INTEGER NOT NULL DEFAULT 0,
            scrap_value INTEGER NOT NULL DEFAULT 0,
            hidden_trait TEXT NOT NULL DEFAULT '',
            mint_index INTEGER NOT NULL DEFAULT 0,

            -- catalog fields (added for v3 but included in base create for new DBs)
            category TEXT NOT NULL DEFAULT 'misc',
            subcategory TEXT NOT NULL DEFAULT '',
            stack_max INTEGER NOT NULL DEFAULT 1,
            rarity TEXT NOT NULL DEFAULT 'common',
            quality_float REAL NOT NULL DEFAULT 100.0,
            deleted_at TEXT
        )
        """
    )
    _exec(
        cx,
        """
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            item_id INTEGER NOT NULL,
            qty INTEGER NOT NULL DEFAULT 1,
            equipped INTEGER NOT NULL DEFAULT 0,
            acquired_at TEXT NOT NULL
        )
        """
    )
    _exec(cx, "CREATE UNIQUE INDEX IF NOT EXISTS idx_items_name ON items(name)")
    _exec(cx, "CREATE INDEX IF NOT EXISTS idx_inventory_user ON inventory(user_id)")
    _exec(cx, "CREATE INDEX IF NOT EXISTS idx_inventory_item ON inventory(item_id)")

def _migrate_to_v3(cx: sqlite3.Connection) -> None:
    # Add catalog columns if they don't exist (safe to re-run)
    _add_column_if_missing(cx, "items", "category", "TEXT NOT NULL DEFAULT 'misc'")
    _add_column_if_missing(cx, "items", "subcategory", "TEXT NOT NULL DEFAULT ''")
    _add_column_if_missing(cx, "items", "stack_max", "INTEGER NOT NULL DEFAULT 1")
    _add_column_if_missing(cx, "items", "rarity", "TEXT NOT NULL DEFAULT 'common'")
    _add_column_if_missing(cx, "items", "quality_float", "REAL NOT NULL DEFAULT 100.0")
    _add_column_if_missing(cx, "items", "deleted_at", "TEXT")

def ensure_schema(db_path: Path) -> None:
    with sqlite3.connect(db_path) as cx:
        cx.execute("PRAGMA journal_mode=WAL")
        _ensure_version_table(cx)
        cur = cx.execute("SELECT version FROM schema_version WHERE id = 1")
        (version,) = cur.fetchone()

        with sqlite3.connect(db_path) as cx:
            -    version = get_version(cx)
            +    version = get_version(db_path)

        # Always ensure base tables exist
        _create_base(cx)

        # idempotent migration to v3 (adds missing columns)
        if version < 3:
            _migrate_to_v3(cx)
            _set_version(cx, 3)

        cx.commit()


# src/db/schema_version.py

SCHEMA_VERSION = 4  # bump

def _create_v4(cx):
    cx.execute("ALTER TABLE items ADD COLUMN equippable INTEGER NOT NULL DEFAULT 1;")
    cx.execute("CREATE INDEX IF NOT EXISTS idx_items_equippable ON items(equippable);")

def ensure_schema(db_path):
    with sqlite3.connect(db_path) as cx:
        cx.row_factory = sqlite3.Row
        version = get_version(cx)

        # … existing creators (v1, v2, v3)

        if version < 4:
            _create_v4(cx)
            set_version(cx, 4)
