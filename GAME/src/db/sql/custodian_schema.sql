-- GAME/src/db/sql/custodian_schema.sql
CREATE TABLE IF NOT EXISTS audit_log (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  ts_utc         TEXT NOT NULL,                 -- ISO8601
  actor_id       TEXT NOT NULL,                 -- discord user id
  actor_type     TEXT NOT NULL,                 -- user|system|admin
  action         TEXT NOT NULL,                 -- command/event name
  target_id      TEXT,                          -- user/item/guild/etc.
  guild_id       TEXT,
  channel_id     TEXT,
  context_json   TEXT NOT NULL,                 -- minimal necessary context (redacted)
  evidence_id    INTEGER,                       -- nullable FK
  row_hash       TEXT NOT NULL,                 -- SHA256(row core fields)
  chain_hash     TEXT NOT NULL,                 -- SHA256(prev.chain_hash || row_hash)
  prev_chain_id  INTEGER,                       -- previous audit_log.id (null for genesis)
  signature      TEXT,                          -- optional Ed25519/HMAC of chain_hash
  UNIQUE(id)
);

CREATE TABLE IF NOT EXISTS audit_evidence (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  ts_utc        TEXT NOT NULL,
  kind          TEXT NOT NULL,                 -- image|json|text|bin
  mime          TEXT,
  bytes         BLOB,                          -- or a file path if using filesystem
  sha256        TEXT NOT NULL                  -- content hash
);

CREATE TABLE IF NOT EXISTS admin_flags (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  ts_utc        TEXT NOT NULL,
  subject_id    TEXT NOT NULL,
  reason        TEXT NOT NULL,
  severity      INTEGER NOT NULL,              -- 1..5
  opened_by     TEXT NOT NULL,                 -- admin id
  closed_ts_utc TEXT,
  closed_by     TEXT
);

CREATE TABLE IF NOT EXISTS account_freeze (
  user_id       TEXT PRIMARY KEY,
  ts_utc        TEXT NOT NULL,
  reason        TEXT NOT NULL,
  by_admin      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts_utc);
CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_log(actor_id);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);
