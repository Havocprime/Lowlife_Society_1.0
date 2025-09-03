# =========================================
# File: src/db/verify_db.py
# =========================================
from __future__ import annotations

from .db_path import DB_PATH
from .schema_version import ensure_schema, get_version, LATEST_VERSION

def main() -> None:
    ensure_schema(DB_PATH)
    v = get_version(DB_PATH)
    print(f"OK - version={v} (expected {LATEST_VERSION}) @ {DB_PATH}")

if __name__ == "__main__":
    main()