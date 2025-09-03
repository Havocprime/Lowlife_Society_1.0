# =========================================
# File: src/db/migrate.py
# =========================================
from __future__ import annotations

from .db_path import DB_PATH
from .schema_version import ensure_schema, migrate_to_latest, LATEST_VERSION

def main() -> None:
    ensure_schema(DB_PATH)
    final_v = migrate_to_latest(DB_PATH)
    print(f"OK - migrated to version={final_v} (expected {LATEST_VERSION}) @ {DB_PATH}")

if __name__ == "__main__":
    main()
