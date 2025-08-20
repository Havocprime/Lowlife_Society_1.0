# FILE: src/core/persist.py
from __future__ import annotations
import json, logging, time
from pathlib import Path
from typing import Any, Dict

log = logging.getLogger("persist")

DATA_DIR = Path("data")
PLAYERS_DIR = DATA_DIR / "players"
PLAYERS_DIR.mkdir(parents=True, exist_ok=True)

def _player_path(guild_id: int, user_id: int) -> Path:
    gdir = PLAYERS_DIR / str(guild_id)
    gdir.mkdir(parents=True, exist_ok=True)
    return gdir / f"{user_id}.json"

def load_player(guild_id: int, user_id: int) -> Dict[str, Any]:
    p = _player_path(guild_id, user_id)
    if not p.exists():
        return {
            "guild_id": guild_id,
            "user_id": user_id,
            "created_at": time.time(),
            "profile": {"name": None},
            "inventory": [],        # list of item instances
            "equipment": {          # slot -> item instance id or None
                "primary": None,
                "secondary": None,
                "armor": None,
                "accessory": None,
            },
            "limits": {
                "carry_capacity": 25.0  # soft kg cap; tweak in balance later
            },
            "meta": {"version": 1},
        }
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        log.exception("persist: failed to read %s; starting fresh", p)
        return load_player(guild_id, user_id)  # fresh

def save_player(state: Dict[str, Any]) -> None:
    p = _player_path(state["guild_id"], state["user_id"])
    try:
        p.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        log.exception("persist: failed to write %s", p)
