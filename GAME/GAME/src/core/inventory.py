# FILE: src/core/inventory.py
from __future__ import annotations
import logging
from typing import Dict, Any, List, Optional, Tuple

from src.core.persist import load_player, save_player
from src.core.items import instantiate_from_def

log = logging.getLogger("inventory")

VALID_SLOTS = ["primary","secondary","armor","accessory"]

def ensure_player(guild_id: int, user_id: int) -> Dict[str, Any]:
    return load_player(guild_id, user_id)

def _find_item(state: Dict[str, Any], inst_id: str) -> Optional[Dict[str, Any]]:
    for it in state["inventory"]:
        if it["inst_id"] == inst_id:
            return it
    for slot, iid in state["equipment"].items():
        if not iid:
            continue
        it = next((x for x in state["inventory"] if x["inst_id"] == iid), None)
        if it and it["inst_id"] == inst_id:
            return it
    return None

def grant_item(state: Dict[str, Any], item: Dict[str, Any]) -> None:
    state["inventory"].append(item)
    save_player(state)

def remove_item(state: Dict[str, Any], inst_id: str) -> bool:
    inv = state["inventory"]
    idx = next((i for i,it in enumerate(inv) if it["inst_id"] == inst_id), -1)
    if idx >= 0:
        inv.pop(idx)
        for slot, iid in list(state["equipment"].items()):
            if iid == inst_id:
                state["equipment"][slot] = None
        save_player(state)
        return True
    return False

def equip_item(state: Dict[str, Any], inst_id: str, slot: Optional[str] = None) -> Tuple[bool,str]:
    item = _find_item(state, inst_id)
    if not item:
        return False, "Item not found."
    if item["type"] == "consumable":
        return False, "Consumables cannot be equipped."
    if slot is None:
        slot = item.get("slot") or "primary"
    if slot not in VALID_SLOTS:
        return False, f"Invalid slot '{slot}'."
    if slot not in item.get("fit_slots", [slot]):
        return False, f"{item['name']} cannot be equipped to '{slot}'."
    state["equipment"][slot] = inst_id
    save_player(state)
    return True, f"Equipped {item['name']} to {slot}."

def unequip_slot(state: Dict[str, Any], slot: str) -> Tuple[bool,str]:
    if slot not in VALID_SLOTS:
        return False, f"Invalid slot '{slot}'."
    if state["equipment"].get(slot) is None:
        return False, f"Nothing equipped in {slot}."
    state["equipment"][slot] = None
    save_player(state)
    return True, f"Unequipped {slot}."

# ---------------- Weight / Capacity ----------------

def base_capacity(state: Dict[str, Any]) -> float:
    return float(state.get("limits", {}).get("carry_capacity", 25.0))

def capacity_bonus_from_equipment(state: Dict[str, Any]) -> float:
    """Each EQUIPPED item with tag 'carry' grants +5.0 kg."""
    bonus = 0.0
    for slot, iid in state["equipment"].items():
        if not iid:
            continue
        it = next((x for x in state["inventory"] if x["inst_id"] == iid), None)
        if it and "tags" in it and ("carry" in it["tags"]):
            bonus += 5.0
    return bonus

def current_capacity(state: Dict[str, Any]) -> float:
    return round(base_capacity(state) + capacity_bonus_from_equipment(state), 2)

def total_weight(state: Dict[str, Any]) -> float:
    w = sum(float(it.get("weight", 0)) for it in state["inventory"])
    return round(w, 2)

def is_overweight(state: Dict[str, Any]) -> bool:
    return total_weight(state) > current_capacity(state)

# ---------------- Derived Mods ----------------

def derived_equipped_mods(state: Dict[str, Any]) -> Dict[str, int]:
    mods: Dict[str, int] = {}
    for slot, iid in state["equipment"].items():
        if not iid:
            continue
        item = next((x for x in state["inventory"] if x["inst_id"] == iid), None)
        if not item:
            continue
        for k,v in item.get("mods", {}).items():
            mods[k] = mods.get(k, 0) + int(v)
    return mods

def get_equipped_ids(state: Dict[str, Any]) -> List[str]:
    return [iid for iid in state["equipment"].values() if iid]

def get_equipped_mods(state: Dict[str, Any]) -> Dict[str, int]:
    return derived_equipped_mods(state)

def get_equipped_items(state: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for slot, iid in state.get("equipment", {}).items():
        if not iid:
            out[slot] = None
            continue
        it = next((x for x in state["inventory"] if x["inst_id"] == iid), None)
        out[slot] = it
    return out

# ---------------- Item Generation Helpers ----------------

def generate_item(def_id: str, tier: str = "common") -> Dict[str, Any]:
    return instantiate_from_def(def_id, tier=tier)

def give_basic_loadout(state: Dict[str, Any]) -> None:
    for def_id, tier in [("melee.bat","common"), ("pistol.m9","common"), ("armor.leather","common"), ("med.basic","common")]:
        grant_item(state, generate_item(def_id, tier))

# ---------------- Consumables & Transfer ----------------

def use_consumable(state: Dict[str, Any], inst_id: str) -> Tuple[bool, str]:
    it = _find_item(state, inst_id)
    if not it:
        return False, "Item not found."
    if it.get("type") != "consumable":
        return False, "That item is not a consumable."
    effect_msg = f"You used **{it['name']}**."
    removed = remove_item(state, inst_id)
    if not removed:
        return False, "Failed to consume item."
    return True, effect_msg

def transfer_item(from_state: Dict[str, Any], to_state: Dict[str, Any], inst_id: str) -> Tuple[bool, str]:
    it = _find_item(from_state, inst_id)
    if not it:
        return False, "Item not found."
    if inst_id in from_state.get("equipment", {}).values():
        return False, "Unequip the item before transferring."
    ok = remove_item(from_state, inst_id)
    if not ok:
        return False, "Failed to remove from sender."
    to_state["inventory"].append(it)
    save_player(to_state)
    return True, f"Transferred **{it['name']}** to the recipient."
