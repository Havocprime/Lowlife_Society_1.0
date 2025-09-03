# GAME/src/db/db_path.py
from __future__ import annotations
from pathlib import Path

# This file lives at GAME/src/db/db_path.py
# Project root is GAME/
ROOT = Path(__file__).resolve().parents[2]

VAR_DIR = ROOT / "var"
DB_DIR = VAR_DIR / "db"
DB_PATH = DB_DIR / "lowlife.sqlite"
BACKUP_PATH = DB_DIR / "lowlife.backup.sqlite"

def ensure_db_dir() -> Path:
    """Create var/db if needed and return the DB path."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    return DB_PATH
