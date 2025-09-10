from __future__ import annotations
import sqlite3
from pathlib import Path

def _default_db_path() -> Path:
    # .../GAME/var/db/lowlife.sqlite
    return Path(__file__).resolve().parents[2] / "var" / "db" / "lowlife.sqlite"

try:
    from .db_path import get_db_path  # optional helper if present
    DB_PATH = get_db_path()
except Exception:
    DB_PATH = _default_db_path()

def dedupe_items_by_name() -> None:
    with sqlite3.connect(DB_PATH) as cx:
        cx.row_factory = sqlite3.Row
        cur = cx.cursor()

        # Find names with duplicates
        cur.execute("SELECT name FROM items GROUP BY name HAVING COUNT(*) > 1")
        dup_names = [r[0] for r in cur.fetchall()]

        for name in dup_names:
            cur.execute("SELECT id FROM items WHERE name = ? ORDER BY id ASC", (name,))
            ids = [row[0] for row in cur.fetchall()]
            keep, rest = ids[0], ids[1:]
            if not rest:
                continue

            marks = ",".join("?" * len(rest))

            # Re-point inventory entries
            cur.execute(
                f"UPDATE inventory SET item_id = ? WHERE item_id IN ({marks})",
                (keep, *rest),
            )
            # Remove duplicate item rows
            cur.execute(f"DELETE FROM items WHERE id IN ({marks})", (*rest,))

            print(f"[dedupe] {name!r}: kept id={keep}; removed {rest}")

        cx.commit()

if __name__ == "__main__":
    print(f"DB: {DB_PATH}")
    dedupe_items_by_name()
    print("Done.")
