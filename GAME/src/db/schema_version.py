from __future__ import annotations
from pathlib import Path
import sqlite3

SCHEMA_VERSION = 1

# Anchor to .../GAME/var/db/lowlife.sqlite
BASE_DIR = Path(__file__).resolve().parents[2]  # .../GAME
DB_PATH = BASE_DIR / "var" / "db" / "lowlife.sqlite"


def _connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    cx = sqlite3.connect(db_path)
    cx.execute("PRAGMA foreign_keys = ON")
    return cx


def get_version(db_path: Path = DB_PATH) -> int | None:
    with _connect(db_path) as cx:
        cur = cx.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_meta'")
        if cur.fetchone() is None:
            return None
        row = cx.execute("SELECT version FROM schema_meta WHERE id=1").fetchone()
        return int(row[0]) if row else None


def ensure_schema(db_path: Path = DB_PATH) -> int:
    with _connect(db_path) as cx:
        cur = cx.cursor()

        # meta
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_meta (
                id INTEGER PRIMARY KEY CHECK (id=1),
                version INTEGER NOT NULL
            )
            """
        )

        # users
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_id INTEGER UNIQUE NOT NULL,
                created_at TEXT NOT NULL,
                is_frozen INTEGER NOT NULL DEFAULT 0,
                display_name TEXT
            )
            """
        )

        # items (catalog)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY,                 -- catalog id (we use timestamp for now)
                name TEXT NOT NULL,
                item_class TEXT NOT NULL,
                created_at TEXT NOT NULL,
                bind_on_pickup INTEGER NOT NULL DEFAULT 0,
                durability INTEGER NOT NULL DEFAULT 100,
                pitch_value INTEGER NOT NULL DEFAULT 0,
                rune_value INTEGER NOT NULL DEFAULT 0,
                scrap_value INTEGER NOT NULL DEFAULT 0,
                hidden_trait TEXT,
                mint_index INTEGER
            )
            """
        )

        # inventory (grants)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                qty INTEGER NOT NULL DEFAULT 1,
                equipped INTEGER NOT NULL DEFAULT 0,
                acquired_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE RESTRICT
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_inventory_user ON inventory(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_inventory_item ON inventory(item_id)")

        # set version
        row = cx.execute("SELECT version FROM schema_meta WHERE id=1").fetchone()
        if row is None:
            cur.execute("INSERT INTO schema_meta (id, version) VALUES (1, ?)", (SCHEMA_VERSION,))
        elif int(row[0]) != SCHEMA_VERSION:
            cur.execute("UPDATE schema_meta SET version=? WHERE id=1", (SCHEMA_VERSION,))

        cx.commit()
        return SCHEMA_VERSION
