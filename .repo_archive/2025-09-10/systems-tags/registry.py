# GAME/src/systems/tags/registry.py
from __future__ import annotations
import logging
from typing import Any, Dict, Callable

from . import dal

log = logging.getLogger("tags.registry")

# src/systems/tags/registry.py
from src.systems.tags import dal
from src.systems.health.api import apply_damage, get_hp 


# ---------------------------------------------------------------------------
# Optional HEALTH BRIDGE (robust to local API differences)
# ---------------------------------------------------------------------------
try:
    # Prefer a service function if you already have one.
    # If it doesn't exist, we noop with informative logs.
    from src.services.health import apply_damage as _apply_damage  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - absence is fine
    _apply_damage = None


def _hp_damage(owner_kind: str, owner_id: int, amount: int, *, kind: str, anchor_path: str) -> None:
    """
    Best-effort call into the health layer without hard coupling.
    Tries a couple likely signatures; otherwise logs what would happen.
    """
    if amount <= 0:
        return

    if _apply_damage is None:
        log.info(
            "[HealthBridge] (noop) would deal %s HP %s @ %s/%s",
            amount, kind, owner_kind, owner_id,
        )
        return

    try:
        # Signature 1 (keyworded, rich)
        _apply_damage(
            owner_kind=owner_kind,
            owner_id=owner_id,
            amount=amount,
            kind=kind,
            source="tag:"+kind,
            anchor_path=anchor_path,
        )  # type: ignore
        return
    except TypeError:
        pass

    try:
        # Signature 2 (positional simple)
        _apply_damage(owner_id, amount, kind)  # type: ignore[misc]
        return
    except Exception as e:  # pragma: no cover
        log.warning("[HealthBridge] apply_damage call failed: %r", e)


# ---------------------------------------------------------------------------
# Registry plumbing
#   - REGISTRY is the stable interface the engine already uses:
#       { script_key: { "on_tick": fn, "on_apply": fn, ... } }
#   - New sugar: @handle(tag, phase) to register into REGISTRY.
# ---------------------------------------------------------------------------
PHASES = {"on_apply", "on_tick", "on_expire", "on_remove", "on_merge"}

Handler = Dict[str, Callable[[Dict[str, Any]], None]]
REGISTRY: Dict[str, Handler] = {}   # <- engine reads from here


def _norm_key(s: str) -> str:
    """normalize names like 'Bleeding' or 'Gunshot Wound' â‡’ script keys."""
    s = s.strip().lower()
    # keep underscores, convert spaces and non-alnum to underscores, collapse repeats
    out = []
    last_us = False
    for ch in s:
        if ch.isalnum():
            out.append(ch)
            last_us = False
        else:
            if not last_us:
                out.append("_")
                last_us = True
    return "".join(out).strip("_")


def register(key: str, **handlers: Callable[[Dict[str, Any]], None]) -> None:
    """
    Back-compat imperative registration:
        register("bleeding", on_tick=fn, on_apply=fn2)
    """
    k = _norm_key(key)
    entry = REGISTRY.setdefault(k, {})
    for phase, fn in handlers.items():
        if phase not in PHASES:
            raise ValueError(f"Unknown phase '{phase}'")
        entry[phase] = fn


def handle(tag: str, phase: str):
    """
    Decorator sugar:
        @handle("Bleeding", "on_tick")
        def bleed_tick(ctx): ...
    Registers into REGISTRY under the normalized script key.
    """
    if phase not in PHASES:
        raise ValueError(f"Unknown phase '{phase}'")

    def deco(fn: Callable[[Dict[str, Any]], None]):
        k = _norm_key(tag)
        REGISTRY.setdefault(k, {})[phase] = fn
        return fn

    return deco


# ---------------------------------------------------------------------------
# Built-in Tag Handlers (current behavior preserved)
#   ctx keys expected by these handlers (from TagEngine):
#     - instance_id, owner_kind, owner_id, anchor_path
#     - stacks, intensity, metadata, state, script_key
# ---------------------------------------------------------------------------

# --- BLEEDING ---------------------------------------------------------------
@handle("Bleeding", "on_tick")
def _tick_bleeding(ctx: Dict[str, Any]) -> None:
    """
    Every tick_ms:
      - Base model: 1 HP per stack per tick, scaled by intensity (floored to â‰¥1).
      - Easy to rebalance later or flip to % MaxHP if desired.
    """
    stacks = max(1, int(ctx.get("stacks") or 1))
    intensity = float(ctx.get("intensity") or 1.0)
    owner_kind = str(ctx["owner_kind"])
    owner_id = int(ctx["owner_id"])
    anchor = str(ctx.get("anchor_path") or "entity")

    amount = max(1, int(stacks * intensity))

    log.info(
        "[Bleeding] tick -> dmg=%s | stacks=%s intensity=%.2f | owner=%s/%s @ %s",
        amount, stacks, intensity, owner_kind, owner_id, anchor,
    )
    _hp_damage(owner_kind, owner_id, amount, kind="bleed", anchor_path=anchor)


# --- GUNSHOT WOUND ----------------------------------------------------------
@handle("wound_gunshot", "on_apply")
def _on_apply_gunshot(ctx: Dict[str, Any]) -> None:
    """
    When Gunshot Wound is applied, seed Bleeding automatically.
    Severity â†’ stacks curve: light=1, medium=2, heavy=3.
    """
    meta = ctx.get("metadata") or {}
    severity = str(meta.get("severity") or "medium").lower()
    owner_kind = str(ctx["owner_kind"])
    owner_id = int(ctx["owner_id"])
    anchor = str(ctx.get("anchor_path") or "entity")

    bleed_stacks = {"light": 1, "medium": 2, "heavy": 3}.get(severity, 2)

    bleed = dal.get_tag_by_name("Bleeding")
    if not bleed:
        log.warning("[Gunshot Wound] Bleeding not found in catalog; skipping seed.")
        return

    try:
        dal.add_or_stack(
            owner_kind=owner_kind,
            owner_id=owner_id,
            anchor_path=anchor,
            tag_id=int(bleed["id"]),
            stacks=int(bleed_stacks),
            intensity=1.0,
            polarity=str(bleed.get("polarity") or "negative"),
            source_kind="tag",
            source_ref="Gunshot Wound:on_apply",
        )
        log.info("[Gunshot Wound] seeded Bleeding x%s @ %s", bleed_stacks, anchor)
    except Exception as e:
        log.warning("[Gunshot Wound] failed to seed Bleeding: %r", e)

def tick_bleeding(row: dict) -> None:
    iid = int(row["id"])
    owner = (row["owner_kind"], int(row["owner_id"]))
    stacks = int(row.get("stacks", 1))
    dmg = max(1, stacks)  # your formula; logs showed 4 @ 4 stacks

    # Apply damage; your function may already clamp to 0
    new_hp = apply_damage(owner, dmg, reason="bleed", source="tag:bleed")

    # If dead/at 0, end the tag and stop ticking
    if new_hp <= 0:
        dal.set_state(iid, "ended")
        dal.touch_tick(iid, next_tick_at=None)
        return

    # Otherwise, schedule next tick
    tick_ms = int(row.get("tick_ms") or 1500)
    dal.touch_tick(iid, next_tick_at=dal.now_ms() + tick_ms)


__all__ = ["REGISTRY", "register", "handle"]
