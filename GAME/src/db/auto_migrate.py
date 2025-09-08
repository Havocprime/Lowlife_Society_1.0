# =========================================
# FILE: GAME/src/db/auto_migrate.py
# =========================================
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

def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)
    ).fetchone() is not None

def _column_exists(conn: sqlite3.Connection, table: str, col: str) -> bool:
    return any(r[1] == col for r in conn.execute(f"PRAGMA table_info({table})"))

def _add_column_if_missing(conn: sqlite3.Connection, table: str, col_def: str) -> None:
    col_name = col_def.split()[0]
    if _table_exists(conn, table) and not _column_exists(conn, table, col_name):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")

# ---------------- existing items tweak ----------------
def ensure_items_subcategory(conn: sqlite3.Connection) -> None:
    # If items table hasn't been created yet, skip quietly.
    if not _table_exists(conn, "items"):
        return
    if not _column_exists(conn, "items", "subcategory"):
        conn.execute("ALTER TABLE items ADD COLUMN subcategory TEXT")

# ---------------- NEW: MVP character schema ----------------
def ensure_characters_mvp_schema(conn: sqlite3.Connection) -> None:
    """Add MVP character columns (idempotent). Safe to run any time."""
    if not _table_exists(conn, "characters"):
        return

    # Identity / denormalized
    _add_column_if_missing(conn, "characters", "discord_id TEXT")
    _add_column_if_missing(conn, "characters", "char_first TEXT")
    _add_column_if_missing(conn, "characters", "char_last TEXT")
    _add_column_if_missing(conn, "characters", "alias TEXT")
    _add_column_if_missing(conn, "characters", "avatar_url TEXT")

    # Stats — keep your existing 'hp' but also add split max/current
    _add_column_if_missing(conn, "characters", "luck INTEGER DEFAULT 5")  # in case older rows missed it
    _add_column_if_missing(conn, "characters", "hp_max INTEGER DEFAULT 60")
    _add_column_if_missing(conn, "characters", "hp_current INTEGER DEFAULT 60")

    # Progression
    _add_column_if_missing(conn, "characters", "level INTEGER DEFAULT 1")
    _add_column_if_missing(conn, "characters", "xp INTEGER DEFAULT 0")
    _add_column_if_missing(conn, "characters", "talent_points INTEGER DEFAULT 0")

    # Economy & heat
    _add_column_if_missing(conn, "characters", "crypto INTEGER DEFAULT 0")
    _add_column_if_missing(conn, "characters", "cash INTEGER DEFAULT 0")
    _add_column_if_missing(conn, "characters", "dirty_cash INTEGER DEFAULT 0")
    _add_column_if_missing(conn, "characters", "debt INTEGER DEFAULT 0")
    _add_column_if_missing(conn, "characters", "heat INTEGER DEFAULT 0")

    # Status / meta
    _add_column_if_missing(conn, "characters", "is_npc INTEGER DEFAULT 0")
    _add_column_if_missing(conn, "characters", "state TEXT DEFAULT 'ACTIVE'")           # ACTIVE|DOWNED|INCAPACITATED|DEAD
    _add_column_if_missing(conn, "characters", "conditions TEXT DEFAULT '[]'")         # JSON text
    _add_column_if_missing(conn, "characters", "privacy_level TEXT DEFAULT 'PUBLIC'")  # PUBLIC|FRIENDS|PRIVATE

    # Backfill NULLs to defaults for existing rows (SQLite applies DEFAULT to new rows only)
    conn.executescript(
        """
        UPDATE characters SET hp_max      = COALESCE(hp_max,      COALESCE(hp, 60));
        UPDATE characters SET hp_current  = COALESCE(hp_current,  COALESCE(hp, 60));
        UPDATE characters SET level       = COALESCE(level,       1);
        UPDATE characters SET xp          = COALESCE(xp,          0);
        UPDATE characters SET talent_points = COALESCE(talent_points, 0);
        UPDATE characters SET crypto      = COALESCE(crypto,      0);
        UPDATE characters SET cash        = COALESCE(cash,        0);
        UPDATE characters SET dirty_cash  = COALESCE(dirty_cash,  0);
        UPDATE characters SET debt        = COALESCE(debt,        0);
        UPDATE characters SET heat        = COALESCE(heat,        0);
        UPDATE characters SET is_npc      = COALESCE(is_npc,      0);
        UPDATE characters SET state       = COALESCE(state,       'ACTIVE');
        UPDATE characters SET conditions  = COALESCE(conditions,  '[]');
        UPDATE characters SET privacy_level = COALESCE(privacy_level, 'PUBLIC');
        """
    )
    conn.commit()

# ---------------- entrypoint ----------------
def ensure_all() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(DB_PATH)) as conn:
        ensure_items_subcategory(conn)
        ensure_characters_mvp_schema(conn)
        print(f"[auto-migrate] OK: items + characters MVP columns ensured in {DB_PATH}")
