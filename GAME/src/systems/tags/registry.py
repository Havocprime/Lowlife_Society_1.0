# GAME/src/systems/tags/registry.py
from __future__ import annotations
import json
import logging
from typing import Any, Dict, Callable

from . import dal

log = logging.getLogger("tags.registry")

# --- optional health bridge (robust to missing/unknown API shape) ---
try:
    # Prefer a service function if you already have one
    from src.services.health import apply_damage as _apply_damage  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - absence is fine
    _apply_damage = None  # will fall back to logging only


def _hp_damage(owner_kind: str, owner_id: int, amount: int, *, kind: str, anchor_path: str) -> None:
    """Best-effort call into the health layer without hard coupling."""
    if amount <= 0:
        return
    if _apply_damage is None:
        log.info("[HealthBridge] (noop) would deal %s HP %s @ %s/%s", amount, kind, owner_kind, owner_id)
        return

    # Try a few likely signatures to avoid breaking if the local API differs.
    try:
        # Signature 1 (keyworded, rich):
        _apply_damage(owner_kind=owner_kind, owner_id=owner_id, amount=amount,
                      kind=kind, source="tag:bleeding", anchor_path=anchor_path)  # type: ignore
        return
    except TypeError:
        pass
    try:
        # Signature 2 (positional simple):
        _apply_damage(owner_id, amount, kind)  # type: ignore[misc]
        return
    except Exception as e:  # pragma: no cover
        log.warning("[HealthBridge] apply_damage call failed: %r", e)


# ---------------- Registry plumbing ----------------
Handler = dict[str, Callable[[Dict[str, Any]], None]]
REGISTRY: Dict[str, Handler] = {}


def register(key: str, **handlers: Callable[[Dict[str, Any]], None]) -> None:
    REGISTRY[key] = handlers


# ================== Built-in Tag Handlers ==================

# BLEEDING  -------------------------------------------------
def _tick_bleeding(ctx: Dict[str, Any]) -> None:
    """
    Called by the TagEngine every tick_ms for Bleeding instances.

    ctx keys (from engine):
      - instance_id, owner_kind, owner_id, anchor_path, stacks, intensity, metadata, state, script_key
    """
    stacks = int(ctx.get("stacks", 1) or 1)
    intensity = float(ctx.get("intensity", 1.0) or 1.0)
    owner_kind = ctx["owner_kind"]
    owner_id = int(ctx["owner_id"])
    anchor = ctx.get("anchor_path", "entity")

    # Damage model (MVP):
    #   1 HP per tick per stack, scaled by intensity (floored).
    #   This is conservative and easy to tune later or swap to % max_hp.
    amount = max(1, int(stacks * intensity))

    log.info("[Bleeding] tick → dmg=%s | stacks=%s intensity=%.2f | owner=%s/%s @ %s",
             amount, stacks, intensity, owner_kind, owner_id, anchor)

    _hp_damage(owner_kind, owner_id, amount, kind="bleed", anchor_path=anchor)


REGISTRY["bleeding"] = {"on_tick": _tick_bleeding}


# GUNSHOT WOUND  -------------------------------------------
def _on_apply_gunshot(ctx: Dict[str, Any]) -> None:
    """
    Optional hook when a Gunshot Wound is first applied.
    We can seed a Bleeding tag here based on severity metadata if provided.
    NOTE: This callback currently isn't invoked automatically by DAL.
          We'll wire "on-apply" triggers later when we add an apply pipeline.
    """
    meta = ctx.get("metadata") or {}
    severity = (meta.get("severity") or "medium").lower()
    owner_kind = ctx["owner_kind"]
    owner_id = int(ctx["owner_id"])
    anchor = ctx.get("anchor_path", "entity")

    bleed_stacks = {"light": 1, "medium": 2, "heavy": 3}.get(severity, 2)

    # Look up Bleeding in catalog; if present, add it on the same anchor.
    bleed = dal.get_tag_by_name("Bleeding")
    if bleed:
        try:
            dal.add_or_stack(
                owner_kind=owner_kind,
                owner_id=owner_id,
                anchor_path=anchor,
                tag_id=bleed["id"],
                stacks=bleed_stacks,
                intensity=1.0,
                polarity=bleed["polarity"],
                source_kind="tag",
                source_ref="Gunshot Wound:on_apply",
            )
            log.info("[Gunshot Wound] seeded Bleeding x%s @ %s", bleed_stacks, anchor)
        except Exception as e:
            log.warning("[Gunshot Wound] failed to seed Bleeding: %r", e)


REGISTRY["wound_gunshot"] = {"on_apply": _on_apply_gunshot}
