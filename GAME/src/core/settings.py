from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# NEW: load .env automatically
try:
    from dotenv import load_dotenv  # python-dotenv is already in your env per the log
except Exception:
    load_dotenv = None

GAME_DIR = Path(__file__).resolve().parents[2]  # .../GAME
REPO_DIR = GAME_DIR.parent
VAR = GAME_DIR / "var"
VAR.mkdir(exist_ok=True)

if load_dotenv:
    # Load repo root first, then GAME/.env (GAME overrides)
    load_dotenv(REPO_DIR / ".env")
    load_dotenv(GAME_DIR / ".env", override=True)


def _env_bool(key: str, default: bool = False) -> bool:
    v = os.getenv(key)
    if v is None:
        return default
    return v.strip() not in ("0", "false", "False", "")


@dataclass(frozen=True)
class Settings:
    discord_token: str
    guild_id: int
    db_path: Path
    app_env: str
    log_json: bool

    @staticmethod
    def load() -> "Settings":
        token = os.getenv("DISCORD_TOKEN", "").strip()
        gid = int(os.getenv("DISCORD_GUILD_ID", "0") or "0")
        dbp = Path(os.getenv("DB_PATH", str(VAR / "lowlife.db")))
        env = os.getenv("APP_ENV", "dev").lower()
        return Settings(
            discord_token=token,
            guild_id=gid,
            db_path=dbp,
            app_env=env,
            log_json=_env_bool("LOG_JSON", False),
        )


SETTINGS = Settings.load()

ROOT = Path(__file__).resolve().parents[2]  # .../GAME
VAR = ROOT / "var"
VAR.mkdir(exist_ok=True)


def _env_bool(key: str, default: bool = False) -> bool:
    v = os.getenv(key)
    if v is None:
        return default
    return v.strip() not in ("0", "false", "False", "")


@dataclass(frozen=True)
class Settings:
    discord_token: str
    guild_id: int
    db_path: Path
    app_env: str
    log_json: bool

    @staticmethod
    def load() -> "Settings":
        token = os.getenv("DISCORD_TOKEN", "").strip()
        gid = int(os.getenv("DISCORD_GUILD_ID", "0") or "0")
        dbp = Path(os.getenv("DB_PATH", str(VAR / "lowlife.db")))
        env = os.getenv("APP_ENV", "dev").lower()
        return Settings(
            discord_token=token,
            guild_id=gid,
            db_path=dbp,
            app_env=env,
            log_json=_env_bool("LOG_JSON", False),
        )


SETTINGS = Settings.load()
