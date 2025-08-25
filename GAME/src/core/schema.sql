-- players
CREATE TABLE IF NOT EXISTS players (
  discord_id           TEXT PRIMARY KEY,
  name                 TEXT,
  global_name          TEXT,
  nickname             TEXT,
  is_bot               BOOLEAN,
  is_system            BOOLEAN,
  created_at_utc       TEXT,
  joined_at_utc        TEXT,
  avatar_url           TEXT,
  banner_url           TEXT,
  accent_color         INTEGER,
  premium_since_utc    TEXT,
  top_role_id          TEXT,
  top_role_name        TEXT,
  status               TEXT,
  public_flags         INTEGER,
  communication_disabled_until_utc TEXT,
  veteran_rank         TEXT,
  portrait_asset       TEXT,
  invite_code          TEXT,
  inviter_id           TEXT,
  invite_channel_id    TEXT,
  risk_score           INTEGER,
  risk_reasons         TEXT,
  first_snapshot_json  TEXT,
  created_ts           TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS player_roles (
  discord_id  TEXT,
  role_id     TEXT,
  role_name   TEXT,
  PRIMARY KEY (discord_id, role_id)
);
CREATE TABLE IF NOT EXISTS join_events (
  id                   INTEGER PRIMARY KEY AUTOINCREMENT,
  discord_id           TEXT,
  guild_id             TEXT,
  joined_at_utc        TEXT,
  invite_code          TEXT,
  inviter_id           TEXT,
  pre_roles_json       TEXT,
  post_roles_json      TEXT,
  snapshot_json        TEXT
);