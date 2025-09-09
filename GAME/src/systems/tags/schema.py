from __future__ import annotations
import sqlite3
from . import dal

SQL_CREATE = """
CREATE TABLE IF NOT EXISTS tags (
  id              INTEGER PRIMARY KEY,
  name            TEXT NOT NULL UNIQUE,
  kind            TEXT NOT NULL DEFAULT 'dynamic',
  "group"         TEXT,
  polarity        TEXT,
  max_stacks      INTEGER NOT NULL DEFAULT 1,
  tick_ms         INTEGER,
  duration_ms     INTEGER,
  visibility      TEXT DEFAULT 'public',
  exclusivity     TEXT,
  script_key      TEXT,
  state_machine_json TEXT,
  modifiers_json  TEXT,
  created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS tag_instances (
  id              INTEGER PRIMARY KEY,
  owner_kind      TEXT NOT NULL DEFAULT 'player',
  owner_id        INTEGER NOT NULL,
  anchor_path     TEXT NOT NULL DEFAULT 'entity',
  tag_id          INTEGER NOT NULL,
  state           TEXT,
  state_started_at TEXT,
  stacks          INTEGER NOT NULL DEFAULT 1,
  intensity       REAL NOT NULL DEFAULT 1.0,
  polarity        TEXT,
  confidence      REAL,
  source_kind     TEXT,
  source_ref      TEXT,
  metadata_json   TEXT,
  created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  expires_at      TEXT,
  last_tick_at    TEXT,
  UNIQUE(owner_kind, owner_id, anchor_path, tag_id),
  FOREIGN KEY(tag_id) REFERENCES tags(id)
);

CREATE INDEX IF NOT EXISTS idx_tag_instances_owner ON tag_instances(owner_kind, owner_id);
CREATE INDEX IF NOT EXISTS idx_tag_instances_expiry ON tag_instances(expires_at);
CREATE INDEX IF NOT EXISTS idx_tag_instances_tick   ON tag_instances(last_tick_at);
"""

def ensure_tags_schema() -> None:
    """Idempotent: create tables/indexes if they don't exist, and record migration if _migrations exists."""
    con = dal._conn()
    with con:
        con.executescript(SQL_CREATE)
        # If your DB already has _migrations, record an entry (optional)
        try:
            con.execute("""
                INSERT INTO _migrations(id, name, applied_at)
                SELECT 5, '005_tags_runtime_ensure', strftime('%Y-%m-%dT%H:%M:%fZ','now')
                WHERE NOT EXISTS(SELECT 1 FROM _migrations WHERE id=5 OR name='005_tags' OR name='005_tags_runtime_ensure');
            """)
        except sqlite3.OperationalError:
            # _migrations table doesn't exist in some test DBs — ignore
            pass
