
# =========================================
# File: src/db/reset_catalog.py
# (optional convenience script to clear catalog & counters)
# =========================================
from __future__ import annotations

import sqlite3
from .db_path import DB_PATH
from .schema_version import ensure_schema

def main() -> None:
    ensure_schema(DB_PATH)
    with sqlite3.connect(DB_PATH) as cx:
        # Wipe item catalog & inventory; keep meta/migrations intact
        cx.executescript("""
        DELETE FROM items;
        DELETE FROM inventory;
        DELETE FROM inventory_equipped;
        UPDATE sqlite_sequence SET seq = 0 WHERE name IN ('items','inventory');
        """)
    print("Catalog cleared, inventory cleared, ID counters reset.")

if __name__ == "__main__":
    main()
