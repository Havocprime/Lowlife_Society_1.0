from __future__ import annotations
from pathlib import Path
from .schema_version import ensure_schema, get_version, SCHEMA_VERSION


DB_PATH = Path("var/db/lowlife.sqlite")


if __name__ == "__main__":
ensure_schema(DB_PATH)
ver = get_version(DB_PATH)
print(f"DB OK — version={ver} (expected {SCHEMA_VERSION}) @ {DB_PATH}")
assert ver == SCHEMA_VERSION, "Schema version mismatch! Run ensure_schema()."