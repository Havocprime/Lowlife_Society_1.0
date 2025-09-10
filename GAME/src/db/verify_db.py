# ===== FILE: GAME/src/db/verify_db.py ========================================
from __future__ import annotations

from .schema_version import get_version, EXPECTED_VERSION, _connect  # type: ignore
from .db_path import DB_PATH

def main() -> None:
    with _connect(DB_PATH) as cx:
        v = get_version(cx)
    status = "OK" if v == EXPECTED_VERSION else "WARN"
    print(f"{status} - version={v} (expected {EXPECTED_VERSION}) @ {DB_PATH}")

if __name__ == "__main__":
    main()
