from __future__ import annotations
import shutil
import sqlite3
from .db_path import DB_PATH, BACKUP_PATH, ensure_db_dir

def _safe_exec(cx: sqlite3.Connection, sql: str) -> None:
    try:
        cx.execute(sql)
    except sqlite3.Error:
        pass

def main() -> None:
    ensure_db_dir()
    # Auto-backup if DB exists
    try:
        if DB_PATH.exists():
            shutil.copyfile(DB_PATH, BACKUP_PATH)
    except Exception:
        # best-effort backup; continue either way
        pass

    with sqlite3.connect(str(DB_PATH)) as cx:
        cx.execute("PRAGMA foreign_keys = OFF")
        # Clear data
        _safe_exec(cx, "DELETE FROM inventory")
        _safe_exec(cx, "DELETE FROM items")
        # Reset AUTOINCREMENT counters
        _safe_exec(cx, "DELETE FROM sqlite_sequence WHERE name IN ('items','inventory')")
        cx.commit()
        # Repack file
        _safe_exec(cx, "VACUUM")

    print("OK — catalog cleared, inventory cleared, ID counters reset.")

if __name__ == "__main__":
    main()
