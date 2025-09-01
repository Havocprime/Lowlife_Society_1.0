from __future__ import annotations
from pathlib import Path
import sqlite3


SCHEMA_VERSION = 1 # bump when models or tables change


DDL = [
# Version table
"""
CREATE TABLE IF NOT EXISTS schema_version (
id INTEGER PRIMARY KEY CHECK (id = 1),
version INTEGER NOT NULL
);
""",
# Core tables (minimal for v1 bootstrap)
"""
CREATE TABLE IF NOT EXISTS users (
id INTEGER PRIMARY KEY,
discord_id INTEGER UNIQUE NOT NULL,
created_at TEXT NOT NULL,
is_frozen INTEGER NOT NULL DEFAULT 0,
display_name TEXT
);
""",
"""
CREATE TABLE IF NOT EXISTS characters (
id INTEGER PRIMARY KEY,
user_id INTEGER NOT NULL REFERENCES users(id),
name TEXT NOT NULL,
created_at TEXT NOT NULL,
str INTEGER, vit INTEGER, end INTEGER, agi INTEGER,
dex INTEGER, wis INTEGER, intel INTEGER, cha INTEGER, luck INTEGER,
hp INTEGER
);
""",
"""
CREATE TABLE IF NOT EXISTS items (
id INTEGER PRIMARY KEY,
name TEXT NOT NULL,
item_class TEXT NOT NULL,
created_at TEXT NOT NULL,
bind_on_pickup INTEGER NOT NULL DEFAULT 0,
durability INTEGER,
pitch_value INTEGER NOT NULL DEFAULT 0,
rune_value INTEGER NOT NULL DEFAULT 0,
scrap_value INTEGER NOT NULL DEFAULT 0,
hidden_trait TEXT,
mint_index INTEGER
);
""",
"""
CREATE TABLE IF NOT EXISTS inventory (
id INTEGER PRIMARY KEY,
user_id INTEGER NOT NULL REFERENCES users(id),
item_id INTEGER NOT NULL REFERENCES items(id),
qty INTEGER NOT NULL,
equipped INTEGER NOT NULL DEFAULT 0,
acquired_at TEXT NOT NULL
);
""",
"""
CREATE TABLE IF NOT EXISTS audit (
id INTEGER PRIMARY KEY,
ts TEXT NOT NULL,
kind TEXT NOT NULL,
actor_discord_id INTEGER NOT NULL,
target_discord_id INTEGER,
ctx TEXT
);
""",
# Indexes
"CREATE INDEX IF NOT EXISTS idx_inv_user ON inventory(user_id);",
"CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit(actor_discord_id);",
]




def ensure_schema(db_path: Path) -> None:
db_path.parent.mkdir(parents=True, exist_ok=True)
with sqlite3.connect(db_path) as cx:
cur = cx.cursor()
for stmt in DDL:
cur.executescript(stmt)
# version row
cur.execute("SELECT version FROM schema_version WHERE id = 1")
row = cur.fetchone()
if row is None:
cur.execute("INSERT INTO schema_version (id, version) VALUES (1, ?)", (SCHEMA_VERSION,))
else:
cur.execute("UPDATE schema_version SET version = ? WHERE id = 1", (SCHEMA_VERSION,))
cx.commit()




def get_version(db_path: Path) -> int:
with sqlite3.connect(db_path) as cx:
cur = cx.cursor()
cur.execute("SELECT version FROM schema_version WHERE id = 1")
row = cur.fetchone()
return int(row[0]) if row else 0