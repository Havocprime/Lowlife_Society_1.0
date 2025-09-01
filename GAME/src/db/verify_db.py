# GAME/src/db/verify_db.py
from __future__ import annotations
from pathlib import Path
import sys

# Try package import first
try:
    from .schema_version import ensure_schema, get_version, SCHEMA_VERSION
except ImportError:
    # Script mode fallback: add .../GAME to sys.path so "src" is importable
    THIS = Path(__file__).resolve()
    GAME_DIR = THIS.parents[2]  # .../GAME
    p = str(GAME_DIR)
    if p not in sys.path:
        sys.path.insert(0, p)
    from src.db.schema_version import ensure_schema, get_version, SCHEMA_VERSION  # type: ignore

DB_PATH = Path("var/db/lowlife.sqlite")

def main() -> None:
    ensure_schema(DB_PATH)
    ver = get_version(DB_PATH)
    print(f"DB OK — version={ver} (expected {SCHEMA_VERSION}) @ {DB_PATH}")
    assert ver == SCHEMA_VERSION, "Schema version mismatch! Run ensure_schema()."

if __name__ == "__main__":
    main()
