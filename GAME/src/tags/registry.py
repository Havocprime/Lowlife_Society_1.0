# GAME/src/tags/registry.py
from __future__ import annotations
import math
import re
import logging
from dataclasses import dataclass
from typing import Callable, Iterable, Optional, Dict, Any, List, Tuple

log = logging.getLogger("tags.registry")

# --- Soft imports (graceful fallbacks) ----------------------------------------
try:
    from src.services import health as health_svc  # needs: get_state(...), and one of: set_hp/apply_delta/adjust_hp/set_state/modify_hp
except Exception:  # pragma: no cover
    health_svc = None

try:
    from src.services import playerlog as playerlog_svc  # needs: log_player_death, append_event
except Exception:  # pragma: no cover
    playerlog_svc = None


# --- Minimal protocol for a "tag record" you pass to on_tick ------------------
# Expecting: dict-like with keys: key:str, intensity:int (1..10), meta:dict (optional)
# Example tag: {"key": "wound.heavy", "intensity": 4, "meta": {"source": "knife"}}

@dataclass
class EffectSpec:
    pattern: re.Pattern
    # returns drain_per_second (>=0). Caller multiplies by elapsed_s
    dps_fn: Callable[[int, Dict[str, Any]], float]
    # optional text for logs
    label: str


def _clamp_intensity(n: int) -> int:
    return 1 if n is None else max(1, min(int(n), 10))


# --- Per-family DPS models ----------------------------------------------------
def _linear(base: float, per_int: float) -> Callable[[int, Dict[str, Any]], float]:
    def f(intensity: int, _meta: Dict[str, Any]) -> float:
        i = _clamp_intensity(intensity)
        return max(0.0, base + per_int * i)
    return f

def _zero(_: int, __: Dict[str, Any]) -> float:
    return 0.0


# Tuned baselines (feel free to tweak)
EFFECTS: List[EffectSpec] = [
    # Generic wound tiers
    EffectSpec(re.compile(r"^wound\.light$"),    _linear(0.00, 0.01), "Light Wound"),
    EffectSpec(re.compile(r"^wound\.medium$"),   _linear(0.01, 0.02), "Medium Wound"),
    EffectSpec(re.compile(r"^wound\.heavy$"),    _linear(0.03, 0.05), "Heavy Wound"),
    EffectSpec(re.compile(r"^wound\.critical$"), _linear(0.08, 0.10), "Critical Wound"),

    # Lacerations scale a bit higher than scratches/contusions
    EffectSpec(re.compile(r"^laceration(\.|$)"), _linear(0.02, 0.025), "Laceration"),

    # Scratches & bruises are mostly nuisance (tiny bleed/pain)
    EffectSpec(re.compile(r"^scratch(\.|$)"),    _linear(0.00, 0.004), "Scratch"),
    EffectSpec(re.compile(r"^bruise(\.|$)"),     _linear(0.00, 0.002), "Bruise"),

    # Fractures typically don’t bleed; broken bones may cause small systemic drain
    EffectSpec(re.compile(r"^fractured_bone(\.|$)"), _zero,              "Fractured Bone"),
    EffectSpec(re.compile(r"^broken_bone(\.|$)"),    _linear(0.002, 0.002), "Broken Bone"),

    # Add near other EFFECTS entries
    EffectSpec(re.compile(r"^bleeding$"), _linear(0.02, 0.015), "Bleeding"),

]


def _find_effect(tag_key: str) -> Optional[EffectSpec]:
    for spec in EFFECTS:
        if spec.pattern.search(tag_key):
            return spec
    return None


# --- HP plumbing --------------------------------------------------------------
def _apply_hp_delta(player_id: int, delta_hp: float) -> Tuple[float, float]:
    """
    Negative delta does damage. Returns (hp_before, hp_after).
    Tries multiple health service APIs to fit your install.
    """
    if health_svc is None:
        raise RuntimeError("health service missing")

    st = health_svc.get_state(player_id)
    hp_before = float(st.get("hp", 0))
    max_hp = float(st.get("max_hp", 100)) or 100.0

    # Prefer adjust/modify style if present
    applied = False
    for fn_name in ("adjust_hp", "apply_delta", "modify_hp"):
        fn = getattr(health_svc, fn_name, None)
        if callable(fn):
            hp_after = float(fn(player_id, delta_hp))
            applied = True
            break

    if not applied:
        # Fallback: set_hp / set_state
        new_hp = max(0.0, min(max_hp, hp_before + delta_hp))
        set_hp = getattr(health_svc, "set_hp", None)
        if callable(set_hp):
            set_hp(player_id, new_hp)
            hp_after = new_hp
        else:
            set_state = getattr(health_svc, "set_state", None)
            if not callable(set_state):
                raise RuntimeError("No compatible HP setter found in health service")
            st["hp"] = new_hp
            set_state(player_id, st)
            hp_after = new_hp

    return hp_before, hp_after


# --- Public API ---------------------------------------------------------------
def on_tick(
    player_id: int,
    active_tags: Iterable[Dict[str, Any]],
    elapsed_s: float,
    *,
    death_broadcast: bool = True,
) -> Dict[str, Any]:
    """
    Apply per-tag drains for elapsed_s seconds.

    active_tags: iterable of {"key": str, "intensity": int, "meta": {...}}.
    Returns a summary dict for optional logging/metrics.
    """
    total_damage = 0.0
    per_tag: List[Tuple[str, float]] = []

    for tag in active_tags:
        key = str(tag.get("key", ""))
        spec = _find_effect(key)
        if not spec:
            continue
        intensity = _clamp_intensity(tag.get("intensity", 1))
        dps = spec.dps_fn(intensity, tag.get("meta") or {})
        dmg = max(0.0, dps * float(elapsed_s))
        if dmg <= 0:
            continue
        total_damage += dmg
        per_tag.append((key, dmg))

    summary = {"player_id": player_id, "elapsed_s": elapsed_s, "total_damage": round(total_damage, 3), "by_tag": per_tag}

    if total_damage <= 0:
        return summary

    # Apply damage (negative delta)
    hp_before, hp_after = _apply_hp_delta(player_id, -total_damage)
    summary["hp_before"] = hp_before
    summary["hp_after"] = hp_after

    # Emit a compact playerlog line
    if playerlog_svc:
        playerlog_svc.append_event(
            player_id=player_id,
            event_type="hp.tick",
            payload={
                "elapsed_s": elapsed_s,
                "total_damage": round(total_damage, 3),
                "by_tag": [(k, round(v, 3)) for (k, v) in per_tag],
                "hp_before": round(hp_before, 3),
                "hp_after": round(hp_after, 3),
            },
        )

    # Death handling
    if hp_after <= 0 and playerlog_svc:
        playerlog_svc.log_player_death(player_id, cause="hp_drain", extra={"by_tag": per_tag})
        if death_broadcast:
            # The broadcast (if any) is handled inside log_player_death by your cog/service.
            pass

    return summary
