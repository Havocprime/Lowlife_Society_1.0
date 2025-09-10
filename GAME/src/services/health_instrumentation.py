# ======================================================================
# FILE: GAME/src/services/health_instrumentation.py   (NEW)
# ======================================================================
from __future__ import annotations

import inspect
import logging
from typing import Callable, Optional, Tuple

from src.services import health as health_svc
from src.services.playerlog import log_hp_delta, log_player_death, list_events

log = logging.getLogger("health.instrument")


def _resolve_owner_from_args(args, kwargs) -> Optional[Tuple[str, int]]:
    """
    Best-effort extraction of (owner_kind, owner_id) from arbitrary signatures.
    Looks for common names: owner_kind/owner_id or kind/id or similar.
    """
    # Accept keyword-style first
    for k in ("owner_kind", "kind", "o_kind"):
        if k in kwargs:
            ok = kwargs[k]
            break
    else:
        ok = None
    for k in ("owner_id", "id", "o_id", "player_id"):
        if k in kwargs:
            oid = kwargs[k]
            break
    else:
        oid = None

    if ok is not None and oid is not None:
        return str(ok), int(oid)

    # Positional fallback: many of our fns start with (owner_kind, owner_id, ...)
    if len(args) >= 2:
        try:
            return str(args[0]), int(args[1])
        except Exception:
            pass
    return None


def _already_marked_dead(owner_kind: str, owner_id: int) -> bool:
    rows = list_events(owner_kind, owner_id, limit=5, kinds=["player.death"])
    return len(rows) > 0


def _declare_death(owner_kind: str, owner_id: int, reason: str) -> None:
    if _already_marked_dead(owner_kind, owner_id):
        return
    log_player_death(owner_kind=owner_kind, owner_id=owner_id, reason=reason)
    logging.getLogger("death").critical(
        "DEAD owner=%s:%s reason=%s", owner_kind, owner_id, reason
    )


def _wrap_hp_func(fn: Callable) -> Callable:
    sig = inspect.signature(fn)

    def wrapper(*args, **kwargs):
        ident = _resolve_owner_from_args(args, kwargs)
        before = None
        if ident:
            try:
                before = health_svc.get_state(ident[0], int(ident[1]))[0]
            except Exception:
                before = None

        result = fn(*args, **kwargs)

        if ident:
            try:
                after, _maxhp = health_svc.get_state(ident[0], int(ident[1]))
            except Exception:
                return result

            delta = None
            if before is not None:
                delta = after - before
            try:
                log_hp_delta(
                    owner_kind=ident[0],
                    owner_id=int(ident[1]),
                    delta_hp=int(delta) if delta is not None else 0,
                    hp_after=int(after),
                    source_kind="health",
                    source_ref=getattr(fn, "__name__", "hp_fn"),
                )
            except Exception:
                pass

            if after <= 0:
                _declare_death(ident[0], int(ident[1]), reason="hp_zero")
        return result

    wrapper.__name__ = getattr(fn, "__name__", "wrapped_hp_fn")
    return wrapper


def install() -> None:
    """
    Wrap common HP mutators if they exist.
    This is intentionally tolerant; it won't raise if shapes differ.
    """
    candidates = [
        "damage",
        "heal",
        "apply_delta",
        "adjust_hp",
        "set_hp",
        "set_state",  # if it changes hp
        "modify_hp",
    ]
    installed = []
    for name in candidates:
        fn = getattr(health_svc, name, None)
        if callable(fn):
            try:
                wrapped = _wrap_hp_func(fn)
                setattr(health_svc, name, wrapped)  # type: ignore[assignment]
                installed.append(name)
            except Exception:
                pass

    if installed:
        log.info("health instrumentation installed for: %s", ", ".join(installed))
    else:
        log.info("health instrumentation found no targets to wrap.")
# ======================================================================


