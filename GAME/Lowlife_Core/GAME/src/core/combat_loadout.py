# FILE: src/core/combat_loadout.py  (NEW)
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple

from src.core.persist import load_player, save_player
from src.core.inventory import get_equipped_items, derived_equipped_mods

# very light per-class defaults; tune via YAML later
_CLASS = {
    "melee":   {"ranges": ["Close"],              "base_damage": 6, "base_accuracy": 85},
    "pistol":  {"ranges": ["Close","Near","Mid"], "base_damage": 5, "base_accuracy": 70},
    "smg":     {"ranges": ["Close","Near"],       "base_damage": 6, "base_accuracy": 65},
    "shotgun": {"ranges": ["Close","Near"],       "base_damage": 9, "base_accuracy": 60},
    "rifle":   {"ranges": ["Near","Mid","Far"],   "base_damage": 7, "base_accuracy": 75},
}

def _class_from_item(it: Dict[str, Any] | None) -> Optional[str]:
    if not it: return None
    tags = set(it.get("tags", []))
    def_id = it.get("def_id","")
    if "melee" in tags or def_id.startswith("melee.") or "bat" in tags: return "melee"
    if "pistol" in tags:  return "pistol"
    if "smg" in tags:     return "smg"
    if "shotgun" in tags: return "shotgun"
    if "rifle" in tags:   return "rifle"
    return None

@dataclass
class WeaponProfile:
    name: str
    slot: str
    wclass: str
    ranges: List[str]
    base_damage: int
    base_accuracy: int
    mods: Dict[str, int]
    inst_id: str
    def_id: str

def _profile_from_item(slot: str, it: Dict[str, Any] | None) -> Optional[WeaponProfile]:
    if not it: return None
    wcls = _class_from_item(it)
    if not wcls or wcls not in _CLASS: return None
    rule = _CLASS[wcls]
    return WeaponProfile(
        name=it["name"], slot=slot, wclass=wcls,
        ranges=list(rule["ranges"]),
        base_damage=int(rule["base_damage"]),
        base_accuracy=int(rule["base_accuracy"]),
        mods=dict(it.get("mods", {})),
        inst_id=it["inst_id"], def_id=it["def_id"]
    )

def get_combatkit(guild_id: int, user_id: int) -> Dict[str, Any]:
    state = load_player(guild_id, user_id)
    eq = get_equipped_items(state)
    kit = {
        "primary":   _profile_from_item("primary", eq.get("primary")),
        "secondary": _profile_from_item("secondary", eq.get("secondary")),
        "armor":     eq.get("armor"),
        "mods":      derived_equipped_mods(state),
        "preferred_slot": state.get("meta", {}).get("preferred_weapon_slot", "primary"),
    }
    return kit

def set_preferred_slot(guild_id: int, user_id: int, slot: str) -> None:
    st = load_player(guild_id, user_id)
    if "meta" not in st: st["meta"] = {}
    st["meta"]["preferred_weapon_slot"] = slot
    save_player(st)

def pick_weapon_for_range(range_state: str, kit: Dict[str, Any]) -> Tuple[str | None, WeaponProfile | None]:
    pref = kit.get("preferred_slot", "primary")
    cand = [pref, "primary" if pref == "secondary" else "secondary"]
    for slot in cand:
        wp: WeaponProfile | None = kit.get(slot)  # type: ignore
        if wp and range_state in wp.ranges:
            return slot, wp
    return None, None
