# ===== FILE: GAME/src/db/migrate.py ==========================================
from __future__ import annotations

from .schema_version import migrate_to_latest, EXPECTED_VERSION
from .db_path import DB_PATH

def main() -> None:
    final = migrate_to_latest(DB_PATH)
    print(f"migrated to version={final} (expected {EXPECTED_VERSION}) @ {DB_PATH}")

if __name__ == "__main__":
    main()