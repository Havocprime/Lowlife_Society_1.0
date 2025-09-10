# src/cogs/tags/schema.py
from __future__ import annotations
import sqlite3
from typing import Iterable
from .catalog import SEED_KEYS, LIVE_PRESETS, TagKey

TAG_KEYS_SQL = """
CREATE TABLE IF NOT EXISTS tag_keys (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT UNIQUE NOT NULL,
  family TEXT NOT NULL,
  kind TEXT NOT NULL,
  max_stacks INTEGER NOT NULL,
  negative INTEGER NOT NULL,
  duration_s INTEGER,
  fatal_on_expire INTEGER NOT NULL DEFAULT 0,
  tick_s INTEGER NOT NULL DEFAULT 60
);
"""

TAGS_SQL = """
CREATE TABLE IF NOT EXISTS tags (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  owner_type TEXT NOT NULL,          -- e.g. "discord"
  owner_id TEXT NOT NULL,            -- e.g. user id
  key TEXT NOT NULL,                 -- display key (e.g., "Bleeding")
  family TEXT NOT NULL,
  kind TEXT NOT NULL,
  stacks INTEGER NOT NULL DEFAULT 1,
  negative INTEGER NOT NULL,
  expires_at INTEGER,                -- unix ts for expiry
  fatal_on_expire INTEGER NOT NULL DEFAULT 0,
  UNIQUE(owner_type, owner_id, key)
);
CREATE INDEX IF NOT EXISTS idx_tags_owner ON tags(owner_type, owner_id);
"""

def ensure_schema(db: sqlite3.Connection):
    db.executescript(TAG_KEYS_SQL)
    db.executescript(TAGS_SQL)
    db.commit()

def _upsert_keys(db: sqlite3.Connection, keys: Iterable[TagKey]) -> int:
    cur = db.cursor()
    n = 0
    for k in keys:
        cur.execute(
            """
            INSERT INTO tag_keys (name, family, kind, max_stacks, negative, duration_s, fatal_on_expire, tick_s)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                family=excluded.family,
                kind=excluded.kind,
                max_stacks=excluded.max_stacks,
                negative=excluded.negative,
                duration_s=excluded.duration_s,
                fatal_on_expire=excluded.fatal_on_expire,
                tick_s=excluded.tick_s
            """,
            (k.name, k.family, k.kind, k.max_stacks, int(k.negative),
             k.duration_s, int(k.fatal_on_expire), k.tick_s),
        )
        n += 1
    db.commit()
    return n

def seed(db: sqlite3.Connection) -> tuple[int, int]:
    n_keys = _upsert_keys(db, SEED_KEYS)
    n_live = _upsert_keys(db, LIVE_PRESETS)
    return n_keys, n_live
