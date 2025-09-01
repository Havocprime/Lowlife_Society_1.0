from __future__ import annotations
from pathlib import Path
from src.db.verify_db import DB_PATH
from src.db.schema_version import ensure_schema


if __name__ == "__main__":
ensure_schema(DB_PATH)
print("SMOKE: DB ensure_schema OK at", DB_PATH)