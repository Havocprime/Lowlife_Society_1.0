# GAME/src/core/settings.py
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# --- .env loading (repo root first, then GAME/.env overrides) ---
try:
    from dotenv import load_dotenv  # python-dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

THIS_FILE = Path(__file__).resolve()
GAME_DIR  = THIS_FILE.parents[2]
REPO_DIR  = GAME_DIR.parent
VAR_DIR   = GAME_DIR / "var"
VAR_DIR.mkdir(exist_ok=True)

if load_dotenv:
    load_dotenv(REPO_DIR / ".env")
    load_dotenv(GAME_DIR / ".env", override=True)


def _env_bool(key: str, default: bool = False) -> bool:
    v = os.getenv(key)
    if v is None:
        return default
    return v.strip().lower() not in ("0", "false", "")


def _env_int(key: str) -> int | None:
    v = os.getenv(key)
    if not v:
        return None
    try:
        return int(v)
    except ValueError:
        return None


@dataclass(frozen=True)
class Settings:
    # Auth
    discord_token: str

    # Guild wiring
    guild_id: int | None
    welcome_channel_id: int | None
    active_work_channel_id: int | None   # <— NEW

    # Asset / images
    welcome_images_dir: str | None

    # Persistence / misc
    db_path: Path
    app_env: str
    log_json: bool

    @staticmethod
    def load() -> "Settings":
        gid = _env_int("GUILD_ID") or _env_int("DISCORD_GUILD_ID")
        return Settings(
            discord_token=os.getenv("DISCORD_TOKEN", "").strip(),
            guild_id=gid,
            welcome_channel_id=_env_int("WELCOME_CHANNEL_ID"),
            active_work_channel_id=_env_int("ACTIVE_WORK_CHANNEL_ID"),   # <— NEW
            welcome_images_dir=os.getenv("WELCOME_IMAGES_DIR") or os.getenv("MUGSHOT_DIR"),
            db_path=Path(os.getenv("DB_PATH", str(VAR_DIR / "lowlife.db"))),
            app_env=os.getenv("APP_ENV", "dev").lower(),
            log_json=_env_bool("LOG_JSON", False),
        )


SETTINGS = Settings.load()
