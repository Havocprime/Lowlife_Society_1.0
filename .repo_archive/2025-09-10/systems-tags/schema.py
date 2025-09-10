# GAME/src/systems/tags/schema.py
from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path

from . import dal as tag_dal  # local DAL

log = logging.getLogger("tags.schema")
DB_PATH = tag_dal.DB_PATH


# ---------- small helpers ----------
def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def _table_cols(con: sqlite3.Connection, table: str) -> set[str]:
    cur = con.execute(f"PRAGMA table_info({table})")
    return {row["name"] for row in cur.fetchall()}

def _add_column_if_missing(con: sqlite3.Connection, table: str, col: str, ddl: str) -> None:
    if col not in _table_cols(con, table):
        con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
        log.info("tags schema: added %s.%s", table, col)

def _create_if_not_exists(con: sqlite3.Connection, ddl: str) -> None:
    con.execute(ddl)

def _now_ms() -> int:
    return int(time.time() * 1000)


# ---------- main entry ----------
def ensure_tags_schema() -> None:
    """
    Idempotent & backward-compatible.
    Creates/extends:
      - tags (catalog)
      - tag_instances (live instances)
      - helpful indices
    """
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with _conn() as con:
        # sane defaults
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA foreign_keys=ON")

        # ---- Catalog -------------------------------------------------------
        _create_if_not_exists(
            con,
            """
            CREATE TABLE IF NOT EXISTS tags (
              id              INTEGER PRIMARY KEY,
              name            TEXT NOT NULL UNIQUE,
              kind            TEXT DEFAULT 'dynamic',
              polarity        TEXT,

              -- script/engine knobs
              script_key      TEXT NOT NULL,
              tick_ms         INTEGER DEFAULT 1500,
              base_intensity  REAL    DEFAULT 1.0,
              max_stacks      INTEGER DEFAULT 5,
              stack_policy    TEXT    DEFAULT 'add',
              exclusivity_key TEXT    DEFAULT '',
              refresh_policy  TEXT    DEFAULT 'full',
              duration_ms     INTEGER DEFAULT 0
            )
            """
        )

        # Back-compat columns for older code paths/seeds
        _add_column_if_missing(con, "tags", "config_json",   "TEXT")                  # <-- fixes your error
        _add_column_if_missing(con, "tags", "script_key",    "TEXT NOT NULL DEFAULT ''")
        _add_column_if_missing(con, "tags", "tick_ms",       "INTEGER DEFAULT 1500")
        _add_column_if_missing(con, "tags", "base_intensity","REAL DEFAULT 1.0")
        _add_column_if_missing(con, "tags", "max_stacks",    "INTEGER DEFAULT 5")
        _add_column_if_missing(con, "tags", "stack_policy",  "TEXT DEFAULT 'add'")
        _add_column_if_missing(con, "tags", "exclusivity_key","TEXT DEFAULT ''")
        _add_column_if_missing(con, "tags", "refresh_policy","TEXT DEFAULT 'full'")
        _add_column_if_missing(con, "tags", "duration_ms",   "INTEGER DEFAULT 0")

        _create_if_not_exists(
            con,
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_tags_script_key ON tags(script_key)"
        )

        # ---- Instances -----------------------------------------------------
        _create_if_not_exists(
            con,
            """
            CREATE TABLE IF NOT EXISTS tag_instances (
              id            INTEGER PRIMARY KEY,
              owner_kind    TEXT NOT NULL,
              owner_id      INTEGER NOT NULL,
              anchor_path   TEXT    DEFAULT 'entity',
              tag_id        INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,

              stacks        INTEGER DEFAULT 1,
              intensity     REAL    DEFAULT 1.0,
              tick_ms       INTEGER,                -- per-instance override (nullable)

              state         TEXT    DEFAULT 'active',  -- 'active'|'paused'|'expired'
              metadata      TEXT,                      -- JSON blob
              last_error    TEXT,

              source_kind   TEXT,
              source_ref    TEXT,

              created_at    INTEGER NOT NULL,
              next_tick_at  INTEGER,  -- nullable (non-ticking tags)
              last_tick_at  INTEGER,
              expires_at    INTEGER   -- nullable (permanent)
            )
            """
        )

        # add missing columns for older DBs
        _add_column_if_missing(con, "tag_instances", "anchor_path",  "TEXT DEFAULT 'entity'")
        _add_column_if_missing(con, "tag_instances", "stacks",       "INTEGER DEFAULT 1")
        _add_column_if_missing(con, "tag_instances", "intensity",    "REAL DEFAULT 1.0")
        _add_column_if_missing(con, "tag_instances", "tick_ms",      "INTEGER")
        _add_column_if_missing(con, "tag_instances", "state",        "TEXT DEFAULT 'active'")
        _add_column_if_missing(con, "tag_instances", "metadata",     "TEXT")
        _add_column_if_missing(con, "tag_instances", "last_error",   "TEXT")
        _add_column_if_missing(con, "tag_instances", "source_kind",  "TEXT")
        _add_column_if_missing(con, "tag_instances", "source_ref",   "TEXT")
        _add_column_if_missing(con, "tag_instances", "created_at",   f"INTEGER DEFAULT {_now_ms()}")
        _add_column_if_missing(con, "tag_instances", "next_tick_at", "INTEGER")
        _add_column_if_missing(con, "tag_instances", "last_tick_at", "INTEGER")
        _add_column_if_missing(con, "tag_instances", "expires_at",   "INTEGER")

        # helpful lookups
        _create_if_not_exists(
            con,
            """CREATE INDEX IF NOT EXISTS idx_tag_owner_anchor
                 ON tag_instances(owner_kind, owner_id, anchor_path)"""
        )
        _create_if_not_exists(
            con,
            """CREATE INDEX IF NOT EXISTS idx_tag_active_due
                 ON tag_instances(next_tick_at)"""
        )
        _create_if_not_exists(
            con,
            """CREATE INDEX IF NOT EXISTS idx_tag_active_state
                 ON tag_instances(state)"""
        )
        _create_if_not_exists(
            con,
            """CREATE UNIQUE INDEX IF NOT EXISTS uq_tag_anchor_singleton
                 ON tag_instances(owner_kind, owner_id, anchor_path, tag_id)"""
        )
        _create_if_not_exists(
            con,
            """CREATE INDEX IF NOT EXISTS idx_tag_instances_gc
                 ON tag_instances(state, last_tick_at)"""
        )

        con.commit()

    log.info("tags.schema: ensured tables + indices (migrations applied if needed).")
