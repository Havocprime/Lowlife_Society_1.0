from __future__ import annotations
from pathlib import Path
import sys

# make sure 'src' imports work when running as a script
THIS = Path(__file__).resolve()
GAME_DIR = THIS.parents[2]  # .../GAME
if str(GAME_DIR) not in sys.path:
    sys.path.insert(0, str(GAME_DIR))

from src.db.schema_version import ensure_schema, get_version, SCHEMA_VERSION, DB_PATH  # noqa: E402


def main() -> None:
    before = get_version(DB_PATH)
    after = ensure_schema(DB_PATH)
    print(f"DB OK — version={after} (expected {SCHEMA_VERSION}) @ {DB_PATH}")


if __name__ == "__main__":
    main()
