# =========================================
# File: src/db/db_path.py
# =========================================
from __future__ import annotations
from pathlib import Path

# Project root = .../GAME  (this file is .../GAME/src/db/db_path.py)
PROJECT_ROOT = Path(__file__).resolve().parents[2]

VAR_DIR = PROJECT_ROOT / "var"
DB_DIR = VAR_DIR / "db"
DB_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = str(DB_DIR / "lowlife.sqlite")

__all__ = ["DB_PATH", "DB_DIR", "VAR_DIR", "PROJECT_ROOT"]
