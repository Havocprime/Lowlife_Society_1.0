from __future__ import annotations
import os, json
from pathlib import Path
from typing import Any, Optional

ROOT = Path(os.getenv("DATA_DIR", Path(__file__).resolve().parents[2] / "data"))
PLAYERS_DIR = ROOT / "players"
INVENTORY_DIR = ROOT / "inventory"
for d in (PLAYERS_DIR, INVENTORY_DIR):
    d.mkdir(parents=True, exist_ok=True)

def _p_user(user_id: int) -> Path:
    return PLAYERS_DIR / f"{user_id}.json"

def load_player(user_id: int) -> Optional[dict[str, Any]]:
    p = _p_user(user_id)
    if not p.exists(): return None
    return json.loads(p.read_text(encoding="utf-8"))

def save_player(user_id: int, data: dict[str, Any]) -> None:
    _p_user(user_id).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
