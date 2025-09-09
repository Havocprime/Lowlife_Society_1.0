-- 005_tags.sql — Tag catalog + instances (idempotent)
BEGIN;

CREATE TABLE IF NOT EXISTS tags (
  id              INTEGER PRIMARY KEY,
  name            TEXT NOT NULL UNIQUE,
  kind            TEXT NOT NULL DEFAULT 'dynamic', -- 'static' | 'dynamic'
  "group"         TEXT,
  polarity        TEXT,              -- '+', '-', '0' (neutral)
  max_stacks      INTEGER NOT NULL DEFAULT 1,
  tick_ms         INTEGER,           -- NULL = no ticking
  duration_ms     INTEGER,           -- NULL = permanent until removed
  visibility      TEXT DEFAULT 'public', -- public|hidden|dev
  exclusivity     TEXT,              -- family key for merges
  script_key      TEXT,              -- optional handler
  state_machine_json TEXT,           -- JSON definition for dynamic tags
  modifiers_json  TEXT,              -- optional baked modifiers
  created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS tag_instances (
  id              INTEGER PRIMARY KEY,
  owner_kind      TEXT NOT NULL DEFAULT 'player', -- 'player' | 'character' | 'area'
  owner_id        INTEGER NOT NULL,
  anchor_path     TEXT NOT NULL DEFAULT 'entity', -- e.g., 'body:Left Bicep'
  tag_id          INTEGER NOT NULL,
  state           TEXT,             -- current SM state (dynamic); optional for static
  state_started_at TEXT,            -- iso
  stacks          INTEGER NOT NULL DEFAULT 1,
  intensity       REAL NOT NULL DEFAULT 1.0,
  polarity        TEXT,             -- snapshot for quick reads
  confidence      REAL,             -- 0..1 (for ? tags)
  source_kind     TEXT,
  source_ref      TEXT,
  metadata_json   TEXT,
  created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  expires_at      TEXT,             -- NULL = no expiry
  last_tick_at    TEXT,
  UNIQUE(owner_kind, owner_id, anchor_path, tag_id),
  FOREIGN KEY(tag_id) REFERENCES tags(id)
);

CREATE INDEX IF NOT EXISTS idx_tag_instances_owner ON tag_instances(owner_kind, owner_id);
CREATE INDEX IF NOT EXISTS idx_tag_instances_expiry ON tag_instances(expires_at);
CREATE INDEX IF NOT EXISTS idx_tag_instances_tick   ON tag_instances(last_tick_at);

INSERT INTO _migrations(id, name, applied_at)
SELECT 5, '005_tags', strftime('%Y-%m-%dT%H:%M:%fZ','now')
WHERE NOT EXISTS(SELECT 1 FROM _migrations WHERE id=5);

COMMIT;
