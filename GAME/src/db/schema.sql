-- migrations table
CREATE TABLE IF NOT EXISTS _migrations(
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  applied_at TEXT NOT NULL
);

-- players (Discord identity)
CREATE TABLE IF NOT EXISTS players(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  discord_id TEXT UNIQUE NOT NULL,
  username   TEXT,
  joined_at  TEXT,
  last_seen_at TEXT,
  flags INTEGER DEFAULT 0
);

-- characters (game persona linked to player)
CREATE TABLE IF NOT EXISTS characters(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  player_id INTEGER NOT NULL REFERENCES players(id),
  codename  TEXT,
  faction   TEXT,
  created_at TEXT,
  deleted_at TEXT
);

-- profiles (stats snapshot)
CREATE TABLE IF NOT EXISTS profiles(
  character_id INTEGER PRIMARY KEY REFERENCES characters(id),
  hp INTEGER DEFAULT 100,
  stamina INTEGER DEFAULT 100,
  notoriety INTEGER DEFAULT 0
);

-- item definitions
CREATE TABLE IF NOT EXISTS item_defs(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  rarity TEXT,
  class TEXT,
  tags TEXT,
  meta_json TEXT
);

-- inventory (stackable by default)
CREATE TABLE IF NOT EXISTS inventory(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  character_id INTEGER NOT NULL REFERENCES characters(id),
  item_def_id INTEGER NOT NULL REFERENCES item_defs(id),
  qty INTEGER NOT NULL DEFAULT 1,
  meta_json TEXT
);

-- wallets
CREATE TABLE IF NOT EXISTS wallets(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  owner_type TEXT NOT NULL, -- "player" | "character"
  owner_id   INTEGER NOT NULL,
  balance    INTEGER NOT NULL DEFAULT 0,
  UNIQUE(owner_type, owner_id)
);

-- transactions (immutable)
CREATE TABLE IF NOT EXISTS transactions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  owner_type TEXT NOT NULL,
  owner_id   INTEGER NOT NULL,
  amount     INTEGER NOT NULL,
  reason     TEXT,
  idempotency_key TEXT,
  meta_json  TEXT,
  created_at TEXT NOT NULL
);

-- events / audit trail (append-only)
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  type TEXT NOT NULL,
  actor_discord_id TEXT,
  subject TEXT,
  payload_json TEXT,
  created_at TEXT NOT NULL
);

-- items (FINAL desired shape)
CREATE TABLE IF NOT EXISTS items (
  id             INTEGER PRIMARY KEY,
  name           TEXT NOT NULL,                 -- no table-level UNIQUE; use partial index below
  item_class     TEXT NOT NULL,
  created_at     TEXT NOT NULL,
  durability     INTEGER NOT NULL DEFAULT 0,
  bind_on_pickup INTEGER NOT NULL DEFAULT 0,
  pitch_value    INTEGER NOT NULL DEFAULT 0,
  rune_value     INTEGER NOT NULL DEFAULT 0,
  scrap_value    INTEGER NOT NULL DEFAULT 0,
  hidden_trait   TEXT NOT NULL DEFAULT '',
  mint_index     INTEGER NOT NULL DEFAULT 0,
  rarity         TEXT NOT NULL DEFAULT 'common',
  stack_max      INTEGER NOT NULL DEFAULT 1,
  equippable     INTEGER NOT NULL DEFAULT 1,
  cash_value     INTEGER,                       -- optional; manager mirrors from scrap_value
  subcategory    TEXT,
  deleted_at     TEXT                           -- soft-delete flag (NULL = active)
);

-- Helpful indexes
CREATE INDEX IF NOT EXISTS idx_items_name ON items(name);
CREATE INDEX IF NOT EXISTS idx_items_equippable ON items(equippable);

-- Enforce name uniqueness only for *active* rows
CREATE UNIQUE INDEX IF NOT EXISTS idx_items_name_unique_active
ON items(name COLLATE NOCASE)
WHERE deleted_at IS NULL;


-- 005_account_character.sql
BEGIN;

CREATE TABLE IF NOT EXISTS players(
  id INTEGER PRIMARY KEY,
  discord_id TEXT NOT NULL UNIQUE,
  username TEXT,
  display_name TEXT,
  alias TEXT,
  onboarding_state TEXT DEFAULT 'NEW',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_players_discord_id ON players(discord_id);

CREATE TABLE IF NOT EXISTS characters(
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  char_id TEXT NOT NULL UNIQUE,
  pronouns TEXT,
  background TEXT,
  starting_district TEXT,
  archetypes TEXT,
  str INTEGER NOT NULL DEFAULT 5,
  vit INTEGER NOT NULL DEFAULT 5,
  end INTEGER NOT NULL DEFAULT 5,
  agi INTEGER NOT NULL DEFAULT 5,
  dex INTEGER NOT NULL DEFAULT 5,
  wis INTEGER NOT NULL DEFAULT 5,
  intel INTEGER NOT NULL DEFAULT 5,
  cha INTEGER NOT NULL DEFAULT 5,
  luck INTEGER NOT NULL DEFAULT 5,
  hp INTEGER NOT NULL DEFAULT 60,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY(user_id) REFERENCES players(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_characters_user_id ON characters(user_id);

CREATE TRIGGER IF NOT EXISTS trg_players_updated_at
AFTER UPDATE ON players
FOR EACH ROW BEGIN
  UPDATE players SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_characters_updated_at
AFTER UPDATE ON characters
FOR EACH ROW BEGIN
  UPDATE characters SET updated_at = datetime('now') WHERE id = NEW.id;
END;

INSERT INTO _migrations(name, applied_at)
VALUES ('005_account_character.sql', datetime('now'));

COMMIT;
