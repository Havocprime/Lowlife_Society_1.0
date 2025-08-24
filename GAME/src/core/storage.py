from __future__ import annotations
import os, json
from pathlib import Path
from typing import Any, Optional, List

ROOT = Path(os.getenv("DATA_DIR", Path(__file__).resolve().parents[2] / "data"))
PLAYERS_DIR = ROOT / "players"
PLAYERS_DIR.mkdir(parents=True, exist_ok=True)

def _p_user(user_id: int) -> Path:
    return PLAYERS_DIR / f"{user_id}.json"

DEFAULT_PLAYER = {"cls": "wanderer", "lvl": 1, "hp": 10, "inv": ["fists"], "equipped": "fists"}

def load_player(user_id: int) -> Optional[dict[str, Any]]:
    p = _p_user(user_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

def save_player(user_id: int, data: dict[str, Any]) -> None:
    _p_user(user_id).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def ensure_player(user_id: int) -> dict[str, Any]:
    data = load_player(user_id)
    if not data:
        data = DEFAULT_PLAYER.copy()
        save_player(user_id, data)
    data.setdefault("inv", ["fists"])
    data.setdefault("equipped", "fists")
    return data

def delete_player(user_id: int) -> None:
    p = _p_user(user_id)
    if p.exists():
        p.unlink()

def add_item(user_id: int, item: str) -> bool:
    data = ensure_player(user_id)
    inv = data.setdefault("inv", [])
    item = item.lower()
    if item not in inv:
        inv.append(item)
        save_player(user_id, data)
        return True
    return False

def equip_item(user_id: int, item: str) -> bool:
    data = ensure_player(user_id)
    item = item.lower()
    if item not in data.get("inv", []):
        return False
    data["equipped"] = item
    save_player(user_id, data)
    return True

def get_equipped(user_id: int) -> str:
    return ensure_player(user_id).get("equipped", "fists")

def get_inventory(user_id: int) -> List[str]:
    return list(ensure_player(user_id).get("inv", []))
