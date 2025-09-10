# src/config.py
from __future__ import annotations
import os

def getenv_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.lower() in {"1", "true", "t", "yes", "y"}

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
DEV_GUILD_ID = int(os.getenv("DEV_GUILD_ID", "0") or 0)

DATABASE_PATH = os.getenv("DATABASE_PATH", "./data/lowlife.sqlite3")

SYNC_ON_READY = getenv_bool("SYNC_ON_READY", True)
SAFE_SYNC = getenv_bool("SAFE_SYNC", True)
SYNC_FROM_SUGGESTIONS = getenv_bool("SYNC_FROM_SUGGESTIONS", False)

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
