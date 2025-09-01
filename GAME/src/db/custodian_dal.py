from __future__ import annotations
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parents[1] / "db" / "audit.sqlite"

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS audit_log (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  ts_utc         TEXT NOT NULL,
  actor_id       TEXT NOT NULL,
  actor_type     TEXT NOT NULL,            -- user|system|admin
  action         TEXT NOT NULL,
  target_id      TEXT,
  guild_id       TEXT,
  channel_id     TEXT,
  context_json   TEXT NOT NULL,
  evidence_id    INTEGER,
  row_hash       TEXT NOT NULL,
  chain_hash     TEXT NOT NULL,
  prev_chain_id  INTEGER,
  signature      TEXT
);
CREATE TABLE IF NOT EXISTS audit_evidence (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  ts_utc   TEXT NOT NULL,
  kind     TEXT NOT NULL,                  -- image|json|text|bin
  mime     TEXT,
  bytes    BLOB,
  sha256   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS admin_flags (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  ts_utc        TEXT NOT NULL,
  subject_id    TEXT NOT NULL,
  reason        TEXT NOT NULL,
  severity      INTEGER NOT NULL,
  opened_by     TEXT NOT NULL,
  closed_ts_utc TEXT,
  closed_by     TEXT
);
CREATE TABLE IF NOT EXISTS account_freeze (
  user_id   TEXT PRIMARY KEY,
  ts_utc    TEXT NOT NULL,
  reason    TEXT NOT NULL,
  by_admin  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_ts     ON audit_log(ts_utc);
CREATE INDEX IF NOT EXISTS idx_audit_actor  ON audit_log(actor_id);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);
"""

def ensure_custodian_schema() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(SCHEMA_SQL)
