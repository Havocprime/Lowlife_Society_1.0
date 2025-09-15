# GAME/src/status/tag_spec.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Optional, Literal

StackingMode = Literal["sum", "max", "refresh"]

@dataclass(frozen=True)
class TagRule:
    key: str                     # canonical key: e.g., "bruise_3"
    family: str                  # family/group e.g., "bruise", "bleed", "fracture"
    tier: Optional[int]          # 1..10 where applicable
    hp_per_min: float            # negative drains HP per minute; positive heals
    duration_s: Optional[int]    # seconds; None = indefinite until removed
    priority: int                # higher prints first / breaks ties
    max_stacks: int              # how many identical keys can stack
    stacking_mode: StackingMode  # sum|max|refresh (for identical keys)
    lethal: bool                 # True = can kill; False = stops at floor
    min_hp_floor: Optional[int]  # if not lethal, clamp HP to ≥ this value
    icon: str                    # ui hint
    notes: str                   # freeform

# ---------- helpers ----------
def _mk_range(family: str, icon: str, base: float, step: float, dur_min: int,
              lethal: bool, floor: Optional[int], priority: int,
              max_stacks: int = 1, mode: StackingMode = "max",
              notes: str = "") -> Dict[str, TagRule]:
    items: Dict[str, TagRule] = {}
    for t in range(1, 11):
        k = f"{family}_{t}"
        hp_per_min = -(base + step * (t - 1))
        items[k] = TagRule(
            key=k, family=family, tier=t,
            hp_per_min=hp_per_min,
            duration_s=dur_min * 60,
            priority=priority,
            max_stacks=max_stacks,
            stacking_mode=mode,
            lethal=lethal,
            min_hp_floor=floor,
            icon=icon,
            notes=notes,
        )
    return items

REGISTRY: Dict[str, TagRule] = {}

# --- Non-lethal contusions / abrasions (floors at 1 HP) ---
REGISTRY |= _mk_range(
    family="bruise", icon="🟣", base=0.05, step=0.05, dur_min=360,  # 6h–long bruises
    lethal=False, floor=1, priority=10, max_stacks=3, mode="max",
    notes="Non-lethal blunt trauma; low drain; long duration."
)
REGISTRY |= _mk_range(
    family="scratch", icon="🩹", base=0.10, step=0.05, dur_min=240,  # 4h
    lethal=False, floor=1, priority=12, max_stacks=3, mode="max",
    notes="Surface cuts; low drain; floor at 1 HP."
)

# --- Lacerations (can bleed but floorable here; use 'bleed_*' for lethal) ---
REGISTRY |= _mk_range(
    family="laceration", icon="🩻", base=0.25, step=0.10, dur_min=480,  # 8h
    lethal=False, floor=1, priority=15, max_stacks=2, mode="max",
    notes="Deeper cuts; recommend pairing with a bleed tag for lethality."
)

# --- Generalized Wound severities (convenience families) ---
REGISTRY |= _mk_range(
    family="light_wound", icon="🟡", base=0.20, step=0.10, dur_min=180,  # 3h
    lethal=False, floor=1, priority=18, max_stacks=2, mode="max",
    notes="Aggregated light damage."
)
REGISTRY |= _mk_range(
    family="medium_wound", icon="🟠", base=0.40, step=0.15, dur_min=360,  # 6h
    lethal=False, floor=1, priority=20, max_stacks=2, mode="max",
    notes="Aggregated moderate damage."
)
REGISTRY |= _mk_range(
    family="heavy_wound", icon="🔴", base=0.75, step=0.25, dur_min=720,  # 12h
    lethal=False, floor=1, priority=22, max_stacks=2, mode="max",
    notes="Aggregated heavy damage."
)
REGISTRY |= _mk_range(
    family="critical_wound", icon="🟥", base=1.00, step=0.40, dur_min=1440,  # 24h
    lethal=False, floor=1, priority=24, max_stacks=1, mode="max",
    notes="Severe damage but non-lethal by itself (floor at 1 HP)."
)

# --- Bleeds (Lethal) ---
REGISTRY |= _mk_range(
    family="bleed", icon="🩸", base=0.30, step=0.20, dur_min=60,  # 1h default if untreated
    lethal=True, floor=None, priority=50, max_stacks=3, mode="sum",
    notes="Active bleeding; stacks and can kill. Use bandage/med to cancel."
)

# --- Toxins (Lethal; faster time courses) ---
REGISTRY |= _mk_range(
    family="toxin", icon="☣️", base=0.40, step=0.30, dur_min=45,  # 45m
    lethal=True, floor=None, priority=55, max_stacks=2, mode="sum",
    notes="Poisoning; short duration; high lethality potential."
)

# --- Burns (can be lethal depending on tier) ---
REGISTRY |= _mk_range(
    family="burn", icon="♨️", base=0.20, step=0.20, dur_min=240,  # 4h
    lethal=True, floor=None, priority=40, max_stacks=2, mode="max",
    notes="Thermal injuries; may combine with 'pain' type elsewhere."
)

# --- Fractures/Broken (non-lethal; long duration; mobility penalties left to other systems) ---
REGISTRY |= _mk_range(
    family="fracture", icon="🦴", base=0.15, step=0.10, dur_min=4320,  # 72h
    lethal=False, floor=5, priority=30, max_stacks=1, mode="max",
    notes="Non-lethal but debilitating; floor at 5 HP (pain/shock)."
)
REGISTRY |= _mk_range(
    family="broken", icon="🦴", base=0.25, step=0.15, dur_min=10080,  # 7d
    lethal=False, floor=10, priority=32, max_stacks=1, mode="max",
    notes="Serious break; non-lethal floor at 10 HP."
)

# --- Utility: fetch and family lookup ---
def get_rule(key: str) -> Optional[TagRule]:
    if key in REGISTRY:
        return REGISTRY[key]
    # family-only convenience: allow "bruise" to resolve to tier 1 as a fallback
    if "_" not in key and key in {r.family for r in REGISTRY.values()}:
        return REGISTRY.get(f"{key}_1")
    return None

def family_of(key: str) -> Optional[str]:
    r = get_rule(key)
    return r.family if r else None
