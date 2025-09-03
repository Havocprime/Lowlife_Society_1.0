# GAME/src/db/migrate.py
from __future__ import annotations

from pathlib import Path
from src.db.schema_version import ensure_schema, get_version, LATEST_VERSION
try:
    from src.db.db_path import DB_PATH
except Exception:
    DB_PATH = Path("var/db/lowlife.sqlite")

def main() -> None:
    ensure_schema(DB_PATH)
    v = get_version(DB_PATH)
    print(f"OK — migrated to version={v} (expected {LATEST_VERSION}) @ {DB_PATH}")

if __name__ == "__main__":
    main()
