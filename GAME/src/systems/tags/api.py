from __future__ import annotations
import json
from typing import Any, Dict, Optional

from . import dal
from .registry import REGISTRY

def apply_tag(
    *,
    owner_kind: str,
    owner_id: int,
    anchor_path: str,
    tag_name: str,
    stacks: int = 1,
    duration_ms: Optional[int] = None,
    intensity: float = 1.0,
    polarity: Optional[str] = None,
    confidence: Optional[float] = None,
    source_kind: Optional[str] = None,
    source_ref: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> int:
    """
    High-level tag applier that:
      - looks up the catalog row by name,
      - inserts/stacks the instance,
      - triggers the registry 'on_apply' hook if present.
    Returns the tag_instance id.
    """
    row = dal.get_tag_by_name(tag_name)
    if not row:
        raise ValueError(f"Tag '{tag_name}' not found in catalog")

    tag = dict(row)
    # initial state (if dynamic)
    initial_state = None
    try:
        sm = json.loads(tag.get("state_machine_json") or "{}")
        initial_state = sm.get("initial")
    except Exception:
        initial_state = None

    inst_id = dal.add_or_stack(
        owner_kind=owner_kind,
        owner_id=owner_id,
        anchor_path=anchor_path,
        tag_id=tag["id"],
        stacks=stacks,
        intensity=intensity,
        polarity=polarity or tag.get("polarity"),
        confidence=confidence,
        duration_ms=duration_ms,
        state=initial_state,
        source_kind=source_kind,
        source_ref=source_ref,
        metadata=metadata,
    )

    # Fire on-apply if defined
    script_key = tag.get("script_key")
    if script_key and script_key in REGISTRY:
        cb = REGISTRY[script_key].get("on_apply")
        if cb:
            ctx = {
                "instance_id": inst_id,
                "owner_kind": owner_kind,
                "owner_id": owner_id,
                "anchor_path": anchor_path,
                "stacks": stacks,
                "intensity": intensity,
                "polarity": polarity or tag.get("polarity"),
                "confidence": confidence,
                "metadata": metadata or {},
                "state": initial_state,
                "script_key": script_key,
                "tag_name": tag_name,
                "tag_id": tag["id"],
            }
            try:
                cb(ctx)
            except Exception:
                # Never fail the apply for a bad hook
                import logging, traceback
                logging.getLogger("tags.api").warning("on_apply failed for %s:\n%s", script_key, traceback.format_exc())

    return inst_id
