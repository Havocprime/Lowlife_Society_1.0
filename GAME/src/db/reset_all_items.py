from __future__ import annotations
import sqlite3
from .db_path import DB_PATH, ensure_db_dir

def main() -> None:
    ensure_db_dir()
    with sqlite3.connect(str(DB_PATH)) as cx:
        cx.execute("PRAGMA foreign_keys = OFF")
        try:
            cx.execute("DELETE FROM inventory")
            cx.execute("DELETE FROM sqlite_sequence WHERE name = 'inventory'")
            cx.commit()
            cx.execute("VACUUM")
        except sqlite3.Error:
            pass
    print("OK â€” inventory wiped and inventory.id reset.")

if __name__ == "__main__":
    main()
