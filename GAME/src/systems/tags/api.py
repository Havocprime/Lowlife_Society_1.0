# GAME/src/systems/tags/api.py
from __future__ import annotations
from typing import Any, Iterable, Dict, Optional

from .engine import TagEngine  # your existing engine

_engine: Optional[TagEngine] = None

def configure(engine: TagEngine) -> None:
    """Set the global engine used by the lightweight API helpers below."""
    global _engine
    _engine = engine

def _eng() -> TagEngine:
    if _engine is None:
        raise RuntimeError("Tag API not configured. Call api.configure(TagEngine(...)) once at startup.")
    return _engine

# --- thin helpers used by cogs ------------------------------------------------
def apply_tag(entity_id: str, tag: str, **props: Any) -> None:
    _eng().apply(entity_id, tag, **props)

def remove_tag(entity_id: str, tag: str) -> None:
    _eng().remove(entity_id, tag)

def has_tag(entity_id: str, tag: str) -> bool:
    return _eng().has(entity_id, tag)

def get_tags(entity_id: str):
    eng = _eng()
    if hasattr(eng, "get_all"):
        return eng.get_all(entity_id)
    if hasattr(eng, "list"):
        return eng.list(entity_id)
    return []
