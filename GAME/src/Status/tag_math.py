# GAME/src/status/tag_math.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from .tag_spec import TagRule, get_rule, family_of

@dataclass
class ActiveTag:
    key: str
    stacks: int = 1
    remaining_s: Optional[int] = None   # None = infinite
    # You can add applied_at, source, etc., if you already track them.

@dataclass
class TickResult:
    net_hp_delta: float                 # delta for *this tick* (negative drains)
    lethal_enabled: bool                # if any lethal tag is active
    min_hp_floor: Optional[int]         # highest floor among non-lethal rules
    expired_keys: List[str]

def _combine_identicals(tags: List[ActiveTag]) -> List[ActiveTag]:
    # merge identical keys per stacking_mode in spec
    merged: Dict[str, ActiveTag] = {}
    for t in tags:
        r = get_rule(t.key)
        if not r:
            continue
        at = merged.get(t.key)
        if not at:
            merged[t.key] = ActiveTag(key=t.key, stacks=min(t.stacks, r.max_stacks), remaining_s=t.remaining_s)
            continue
        # stacking behavior
        if r.stacking_mode == "sum":
            at.stacks = min(at.stacks + t.stacks, r.max_stacks)
        elif r.stacking_mode == "max":
            at.stacks = max(at.stacks, t.stacks, r.max_stacks)
        elif r.stacking_mode == "refresh":
            at.stacks = min(max(at.stacks, t.stacks), r.max_stacks)
            # refresh duration by taking the max remaining
            if at.remaining_s is not None and t.remaining_s is not None:
                at.remaining_s = max(at.remaining_s, t.remaining_s)
        merged[t.key] = at
    return list(merged.values())

def aggregate(tags: List[ActiveTag], tick_seconds: int) -> TickResult:
    """Compute net delta for this tick from active tags; handle floors and lethality."""
    # Step 1: merge identical-tag stacking
    tags = _combine_identicals(tags)

    # Step 2: if multiple tiers of the same family exist, prefer the highest tier (max) unless family stacks
    by_family: Dict[str, List[Tuple[TagRule, ActiveTag]]] = {}
    for t in tags:
        r = get_rule(t.key)
        if not r:
            continue
        fam = r.family
        by_family.setdefault(fam, []).append((r, t))

    net_per_min = 0.0
    lethal = False
    floor: Optional[int] = None

    for fam, group in by_family.items():
        group.sort(key=lambda rt: (rt[0].tier or 0), reverse=True)
        # default family policy: take the highest-tier only
        r_top, t_top = group[0]

        # families that *sum* inside family (bleed, toxin): sum their stacks
        if fam in {"bleed", "toxin"}:
            s = 0
            for r, t in group:
                s += min(t.stacks, r.max_stacks)
            net_per_min += r_top.hp_per_min * s
        else:
            net_per_min += r_top.hp_per_min * min(t_top.stacks, r_top.max_stacks)

        # lethality & floors
        if r_top.lethal:
            lethal = True
        if not r_top.lethal and r_top.min_hp_floor is not None:
            floor = max(floor or r_top.min_hp_floor, r_top.min_hp_floor)

    # Convert per-minute to this tick
    net_for_tick = (net_per_min / 60.0) * tick_seconds

    # Step 3: decrement durations and mark expirations
    expired: List[str] = []
    for fam, group in by_family.items():
        for r, t in group:
            if t.remaining_s is None:
                continue
            t.remaining_s -= tick_seconds
            if t.remaining_s <= 0:
                expired.append(t.key)

    return TickResult(net_hp_delta=net_for_tick, lethal_enabled=lethal, min_hp_floor=floor, expired_keys=expired)
