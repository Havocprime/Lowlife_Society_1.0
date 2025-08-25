# FILE: src/core/items.py
from __future__ import annotations
import logging, random, time, uuid
from typing import Dict, Any, List, Tuple

log = logging.getLogger("items")

# ---------- Item templates (def_id -> template) ----------
TEMPLATES: Dict[str, Dict[str, Any]] = {
    # ----- MELEE -----
    "melee.bat": {
        "name": "Baseball Bat",
        "type": "weapon",
        "slot": "primary",
        "base_weight": 1.1,
        "base_value": 80,
        "tags": ["weapon", "melee", "blunt", "bat"],
        "mods": {"accuracy": 0, "damage": 2, "concealment": 0, "escape_bonus": 0},
        "fit_slots": ["primary", "secondary"],
    },

    # ----- FIREARMS -----
    "pistol.m9": {
        "name": "M9",
        "type": "weapon",
        "slot": "primary",
        "base_weight": 0.95,
        "base_value": 120,
        "tags": ["weapon","pistol","light"],
        "mods": {"accuracy": 1, "damage": 0, "concealment": 2, "escape_bonus": 0},
        "fit_slots": ["primary", "secondary"],
    },
    "smg.uzi": {
        "name": "Uzi",
        "type": "weapon",
        "slot": "primary",
        "base_weight": 3.5,
        "base_value": 350,
        "tags": ["weapon","smg"],
        "mods": {"accuracy": 0, "damage": 1, "concealment": -1, "escape_bonus": 0},
        "fit_slots": ["primary"],
    },
    "shotgun.m870": {
        "name": "M870",
        "type": "weapon",
        "slot": "primary",
        "base_weight": 3.2,
        "base_value": 450,
        "tags": ["weapon","shotgun","heavy"],
        "mods": {"accuracy": -1, "damage": 3, "concealment": -2, "escape_bonus": 0},
        "fit_slots": ["primary"],
    },
    "rifle.ar15": {
        "name": "AR-15",
        "type": "weapon",
        "slot": "primary",
        "base_weight": 3.1,
        "base_value": 700,
        "tags": ["weapon","rifle"],
        "mods": {"accuracy": 2, "damage": 2, "concealment": -2, "escape_bonus": 0},
        "fit_slots": ["primary"],
    },

    # ----- ARMOR -----
    "armor.leather": {
        "name": "Leather Jacket",
        "type": "armor",
        "slot": "armor",
        "base_weight": 2.8,
        "base_value": 150,
        "tags": ["armor","light"],
        "mods": {"accuracy": 0, "damage": 0, "concealment": 1, "escape_bonus": 0},
        "fit_slots": ["armor"],
    },
    "armor.plated": {
        "name": "Plated Vest",
        "type": "armor",
        "slot": "armor",
        "base_weight": 7.0,
        "base_value": 550,
        "tags": ["armor","heavy"],
        "mods": {"accuracy": 0, "damage": 0, "concealment": -2, "escape_bonus": -1},
        "fit_slots": ["armor"],
    },

    # ----- ACCESSORIES -----
    "acc.sling": {
        "name": "Tactical Sling",
        "type": "accessory",
        "slot": "accessory",
        "base_weight": 0.4,
        "base_value": 60,
        "tags": ["accessory"],
        "mods": {"accuracy": 1, "damage": 0, "concealment": 0, "escape_bonus": 0},
        "fit_slots": ["accessory"],
    },
    "acc.satchel": {
        "name": "Urban Satchel",
        "type": "accessory",
        "slot": "accessory",
        "base_weight": 0.9,
        "base_value": 90,
        "tags": ["accessory","carry"],
        "mods": {"accuracy": 0, "damage": 0, "concealment": -1, "escape_bonus": +1},
        "fit_slots": ["accessory"],
    },

    # ----- CONSUMABLES -----
    "med.basic": {
        "name": "Basic Medkit",
        "type": "consumable",
        "slot": None,
        "base_weight": 0.6,
        "base_value": 80,
        "tags": ["consumable","med"],
        "mods": {"accuracy": 0, "damage": 0, "concealment": 0, "escape_bonus": 0},
        "fit_slots": [],
    },
}

# ---------- Affixes ----------
# (name, tier_weights[common..epic], weight_delta, value_mult, mods_delta)
_AFFIXES: List[Tuple[str, Tuple[int,int,int,int], float, float, Dict[str, int]]] = [
    ("Lightweight",   (40, 25, 10,  5), -0.25, 1.10, {"concealment": +1, "accuracy": +1}),
    ("Compact",       (30, 25, 12,  8), -0.15, 1.10, {"concealment": +1}),
    ("Tuned",         (20, 25, 20, 15), +0.00, 1.15, {"accuracy": +2}),
    ("Reinforced",    (25, 25, 18, 12), +0.60, 1.15, {"damage": +1}),
    ("Overbuilt",     (15, 18, 15, 10), +0.90, 1.20, {"damage": +2, "concealment": -1}),
    ("Street",        (35, 25, 15, 10), +0.10, 1.05, {"concealment": +1}),
    ("Ghost",         ( 5,  8, 10,  6), -0.40, 1.25, {"concealment": +3, "escape_bonus": +1}),
    ("Sharps",        (10, 15, 20, 12), +0.10, 1.20, {"accuracy": +3}),
    ("Brutal",        (10, 15, 18, 12), +0.50, 1.20, {"damage": +3, "concealment": -1}),
]

_TIER_INDEX = {"common":0, "uncommon":1, "rare":2, "epic":3}

def _weighted_choice(rng: random.Random, weights: List[int]) -> int:
    total = sum(weights)
    roll = rng.randrange(total)
    upto = 0
    for i,w in enumerate(weights):
        if upto + w > roll:
            return i
        upto += w
    return len(weights)-1

def _pick_affix_for_tier(rng: random.Random, tier: str) -> Tuple[str, float, float, Dict[str,int]]:
    ti = _TIER_INDEX[tier]
    idx = _weighted_choice(rng, [t[1][ti] for t in _AFFIXES])
    name, _, weight_delta, value_mult, mods_delta = _AFFIXES[idx]
    return name, weight_delta, value_mult, mods_delta

def new_instance_id() -> str:
    return uuid.uuid4().hex[:10]

def instantiate_from_def(def_id: str, *, tier: str = "common", seed: int | None = None) -> Dict[str, Any]:
    assert def_id in TEMPLATES, f"unknown def_id {def_id}"
    tmpl = TEMPLATES[def_id]
    if seed is None:
        seed = random.randint(0, 2**31-1)
    rng = random.Random(seed)

    name = tmpl["name"]
    weight = float(tmpl["base_weight"])
    value  = int(tmpl["base_value"])
    mods   = dict(tmpl["mods"])
    tags   = list(tmpl["tags"])

    affix_count = {"common": 0, "uncommon": 1, "rare": 1, "epic": 2}[tier]
    affixes_applied: List[str] = []
    for _ in range(affix_count):
        aname, wdelta, vmult, mdelta = _pick_affix_for_tier(rng, tier)
        weight = max(0.05, weight + wdelta)
        value = int(round(value * vmult))
        for k, v in mdelta.items():
            mods[k] = mods.get(k, 0) + v
        affixes_applied.append(aname)

    if affixes_applied:
        name = f"{name} ({', '.join(affixes_applied)})"

    slot = tmpl["slot"]
    inst = {
        "inst_id": new_instance_id(),
        "def_id": def_id,
        "name": name,
        "type": tmpl["type"],
        "slot": slot,
        "fit_slots": list(tmpl.get("fit_slots") or ([slot] if slot else [])),
        "weight": round(weight, 2),
        "value": int(value),
        "tier": tier,
        "tags": tags,
        "mods": mods,
        "seed": seed,
        "created_at": time.time(),
    }
    return inst

def list_templates() -> List[str]:
    return sorted(TEMPLATES.keys())
