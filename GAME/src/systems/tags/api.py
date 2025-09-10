
# ======================================================================
# FILE: GAME/src/systems/tags/api.py
# (Adds quiet "tag.applied" logging + expiry watch scheduling)
# ======================================================================
from __future__ import annotations

import json
import logging
import inspect
import os
from typing import Any, Dict, Optional

from . import dal
from .registry import REGISTRY

log = logging.getLogger("tags.api")

# Log the compat warning only once per process.
_COMPAT_LOGGED_ONCE = False

# Cache the DAL signature once at import (safe).
try:
    _DAL_ADD_OR_STACK_PARAMS = tuple(inspect.signature(dal.add_or_stack).parameters)
except Exception:
    _DAL_ADD_OR_STACK_PARAMS = ()


# --- compatibility wrapper for DAL calls ------------------------------
def _safe_add_or_stack(**kwargs):
    """
    Call dal.add_or_stack while stripping any kwargs that the current
    DAL implementation doesn't accept (e.g., 'polarity', 'kind').
    This keeps us compatible across older/newer DAL versions.
    """
    global _COMPAT_LOGGED_ONCE

    try:
        # Fast path if the DAL accepts everything we send
        return dal.add_or_stack(**kwargs)
    except TypeError:
        # Filter to the parameters actually supported by the DAL
        allowed = set(_DAL_ADD_OR_STACK_PARAMS) or set(
            inspect.signature(dal.add_or_stack).parameters
        )
        filtered = {k: v for k, v in kwargs.items() if k in allowed}

        # Optional one-time compat notice (opt-in)
        if not _COMPAT_LOGGED_ONCE and os.getenv("TAGS_COMPAT_LOG", "0") == "1":
            dropped = sorted(set(kwargs).difference(filtered))
            if dropped:
                log.warning("compat: add_or_stack dropped params %s", dropped)
                _COMPAT_LOGGED_ONCE = True

        return dal.add_or_stack(**filtered)


# --- public API --------------------------------------------------------
def apply_tag(
    *,
    owner_kind: str,
    owner_id: int,
    anchor_path: str,
    tag_name: str,
    stacks: int = 1,
    intensity: float = 1.0,
    duration_ms: Optional[int] = None,
    polarity: Optional[str] = None,
    confidence: Optional[float] = None,
    source_kind: Optional[str] = None,
    source_ref: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> int:
    """
    High-level tag applier:
      1) look up catalog row,
      2) insert/stack the instance (scheduling tick/expiry),
      3) invoke registry['on_apply'] if present,
      4) (quietly) store a playerlog 'tag.applied' and schedule an expiry watch.
    Returns tag_instance id.
    """
    tag = dal.get_tag_by_name(tag_name)
    if not tag:
        raise ValueError(f"Tag '{tag_name}' not found in catalog")

    # Optional state-machine initial state (safe if column missing/empty)
    initial_state: Optional[str] = None
    try:
        sm = json.loads(tag.get("state_machine_json") or "{}")
        initial_state = sm.get("initial") or None
    except Exception:
        initial_state = None

    # Effective scheduling values (catalog defaults unless overridden)
    eff_duration_ms: Optional[int] = (
        duration_ms if duration_ms is not None
        else (int(tag.get("duration_ms") or 0) or None)
    )
    eff_tick_ms: Optional[int] = int(tag.get("tick_ms") or 0) or None

    # Fold confidence into metadata (retained even if DAL has no column)
    meta = dict(metadata or {})
    if confidence is not None:
        meta["_confidence"] = float(confidence)

    # Use compatibility wrapper so older DALs (without 'polarity' etc.) still work.
    inst_id = _safe_add_or_stack(
        owner_kind=owner_kind,
        owner_id=owner_id,
        anchor_path=anchor_path,
        tag_id=int(tag["id"]),
        stacks=int(stacks),
        intensity=float(intensity),
        polarity=polarity or tag.get("polarity"),
        state=initial_state or "active",
        duration_ms=eff_duration_ms,
        tick_ms=eff_tick_ms,
        source_kind=source_kind,
        source_ref=source_ref,
        metadata=meta,
    )

    # ---- Quietly log & watch in the playerlog service ----------------
    try:
        from src.services import playerlog as plog  # lazy import to avoid cycles

        # 1) Immutable event row
        plog.append_event(
            owner_kind=owner_kind,
            owner_id=int(owner_id),
            kind="tag.applied",
            anchor_path=anchor_path,
            tag_id=int(tag["id"]),
            tag_name=tag_name,
            source_kind=source_kind,
            source_ref=source_ref,
            metadata={"instance_id": int(inst_id)},
        )

        # 2) Schedule expiry watch if duration exists
        if eff_duration_ms:
            eff_polarity = (polarity or tag.get("polarity") or "").strip().lower()
            fatal = eff_polarity == "negative"
            plog.schedule_tag_expiry_watch(
                instance_id=int(inst_id),
                owner_kind=owner_kind,
                owner_id=int(owner_id),
                tag_id=int(tag["id"]),
                tag_name=tag_name,
                anchor_path=anchor_path,
                duration_ms=int(eff_duration_ms),
                fatal_on_expire=bool(fatal),
            )
    except Exception:
        logging.getLogger("tags.api").debug("playerlog hook failed for %s", tag_name, exc_info=True)

    # ---- Fire on-apply hook (never fail the apply if the hook throws) -
    script_key = (tag.get("script_key") or dal.normalize_key(tag.get("name", "")))
    handler = REGISTRY.get(script_key, {}).get("on_apply")
    if handler:
        ctx = {
            "instance_id": inst_id,
            "owner_kind": owner_kind,
            "owner_id": int(owner_id),
            "anchor_path": anchor_path,
            "stacks": int(stacks),
            "intensity": float(intensity),
            "polarity": polarity or tag.get("polarity"),
            "confidence": confidence,
            "metadata": meta,
            "state": initial_state or "active",
            "script_key": script_key,
            "tag_name": tag_name,
            "tag_id": int(tag["id"]),
        }
        try:
            handler(ctx)
        except Exception:
            # Keep this quiet; per-player logs will carry context.
            logging.getLogger("tags.api").warning("on_apply failed for %s", script_key, exc_info=True)

    return inst_id
# ======================================================================