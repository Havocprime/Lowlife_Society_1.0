from __future__ import annotations
import json
from pathlib import Path
from typing import Iterable

CONF = Path(__file__).resolve().parents[2] / "var" / "config.json"
CONF.parent.mkdir(parents=True, exist_ok=True)

def _load() -> dict:
    if CONF.exists():
        try: return json.loads(CONF.read_text(encoding="utf-8"))
        except Exception: return {}
    return {}

def _save(d: dict) -> None:
    CONF.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")

def get_role_ids(key: str) -> set[int]:
    d = _load(); raw = d.get(key, [])
    return {int(x) for x in raw if str(x).isdigit()}

def set_role_ids(key: str, role_ids: Iterable[int]) -> None:
    d = _load(); d[key] = [int(x) for x in role_ids]; _save(d)
