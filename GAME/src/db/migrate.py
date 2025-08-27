from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path

from src.core.settings import SETTINGS

MIGRATIONS = [
    ("0001_init", "schema.sql"),
    ("0002_txn_idem_unique", "0002_txn_idem_unique.sql"),
]


def _apply(conn: sqlite3.Connection, name: str, sql_path: Path):
    with open(sql_path, "r", encoding="utf-8") as f:
        sql = f.read()
    conn.executescript(sql)
    conn.execute(
        "INSERT INTO _migrations(name, applied_at) VALUES(?, ?)",
        (name, dt.datetime.utcnow().isoformat() + "Z"),
    )
    conn.commit()


def migrate(db_path: Path | None = None):
    dbp = db_path or SETTINGS.db_path
    dbp.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(dbp)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    # Ensure migrations table exists
    conn.execute(
        """CREATE TABLE IF NOT EXISTS _migrations(
        id INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL
    );"""
    )
    applied = {r[0] for r in conn.execute("SELECT name FROM _migrations")}
    for name, file in MIGRATIONS:
        if name not in applied:
            _apply(conn, name, Path(__file__).with_name(file))
    conn.close()


if __name__ == "__main__":
    migrate()
    print(f"DB ready at {SETTINGS.db_path}")
