from __future__ import annotations
from pathlib import Path
from typing import Dict, Any

# Optional import for PyYAML; fall back if missing
try:
    import yaml  # type: ignore
except Exception as e:  # pragma: no cover
    yaml = None  # we'll use defaults

ITEMS_DIR = Path(__file__).resolve().parents[2] / "data" / "items"
WEAPONS_FILE = ITEMS_DIR / "weapons.yml"

DEFAULTS: Dict[str, Any] = {
    "fists": {"name": "fists", "damage": {"CLOSE": 2, "NEAR": 1, "MID": 0, "FAR": 0, "OOR": 0}},
    "knife": {"name": "knife", "damage": {"CLOSE": 4, "NEAR": 2, "MID": 0, "FAR": 0, "OOR": 0}},
    "pistol": {"name": "pistol", "damage": {"CLOSE": 3, "NEAR": 3, "MID": 2, "FAR": 1, "OOR": 0}},
}

def _load_yaml(path: Path) -> Dict[str, Any]:
    if yaml is None:
        print("[LOWLIFE] WARNING: PyYAML not installed; using built-in defaults.")
        return {}
    if not path.exists():
        print(f"[LOWLIFE] WARNING: {path} not found; using defaults.")
        return {}
    try:
        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw) or {}
        if not isinstance(data, dict):
            raise ValueError("weapons.yml must be a mapping")
        return data
    except Exception as e:
        print(f"[LOWLIFE] WARNING: failed loading {path}: {e}; using defaults.")
        return {}

def _merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(a)
    for k, v in (b or {}).items():
        out[k.lower()] = v
    return out

# Load file then overlay with defaults to ensure we always have something
_FILE_WEAPONS = {k.lower(): v for k, v in _load_yaml(WEAPONS_FILE).items()}
_WEAPONS: Dict[str, Any] = _merge(DEFAULTS, _FILE_WEAPONS)

def get_weapon(name: str) -> Dict[str, Any]:
    return _WEAPONS.get(name.lower(), DEFAULTS["fists"])

def damage_for(weapon_name: str, range_band) -> int:
    w = get_weapon(weapon_name)
    dmg_map = (w or {}).get("damage", {})
    try:
        return int(dmg_map.get(range_band.name, 0))
    except Exception:
        return 0
