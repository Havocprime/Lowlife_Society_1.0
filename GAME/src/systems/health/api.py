# src/systems/health/api.py
from __future__ import annotations
from typing import Tuple, Optional

# Forward to the canonical service you already have
from src.services import health as health_svc


def apply_damage(
    owner_kind: str,
    owner_id: int,
    amount: int,
    *,
    source_kind: str = "tag",
    source_ref: Optional[str] = None,
) -> Tuple[int, int]:
    """
    Compatibility wrapper so callers that import `src.systems.health.api`
    keep working. Returns (hp, max_hp).
    """
    try:
        # Preferred signature in your service (with source metadata)
        res = health_svc.apply_damage(
            owner_kind, owner_id, amount,
            source_kind=source_kind, source_ref=source_ref
        )
    except TypeError:
        # Fallback if your service doesn't accept the extra kwargs
        res = health_svc.apply_damage(owner_kind, owner_id, amount)

    # Normalize return to (hp, max_hp)
    if isinstance(res, tuple) and len(res) >= 2:
        hp, max_hp = int(res[0]), int(res[1])
    elif isinstance(res, int):
        hp, max_hp = res, health_svc.get_state(owner_kind, owner_id)[1]
    else:
        hp, max_hp = health_svc.get_state(owner_kind, owner_id)

    return hp, max_hp


def get_hp(owner_kind: str, owner_id: int) -> int:
    """
    Another compatibility wrapper. Old code expects `get_hp()`.
    """
    hp, _max_hp = health_svc.get_state(owner_kind, owner_id)
    return int(hp)
