from __future__ import annotations
import os
from typing import Iterable, List, Any, Dict, Optional
from types import SimpleNamespace

from src.tags.registry import TagRegistry
from src.tags.engine import TagEngine
from src.tags.models import TagInstance

TAGS_DIR = os.getenv("TAGS_DIR", os.path.join("GAME", "content", "tags"))

# --- compat/writer connection for callers like services.health -----------------
def _conn():
    """
    Best-effort writer connection used by systems that don't know the core DAL.
    1) Try to borrow a connection from src.db.dal (write_conn/conn/_conn/get_conn).
    2) Fallback: open a local sqlite DB with Row row_factory.
    """
    try:
        from src.db import dal as core_dal  # prefer your canonical DAL
        for name in ("write_conn", "conn", "_conn", "get_conn"):
            fn = getattr(core_dal, name, None)
            if callable(fn):
                con = fn()
                try:
                    # Ensure sqlite rows behave like dicts for existing code
                    import sqlite3  # noqa: F401
                    if getattr(con, "row_factory", None) is None:
                        con.row_factory = sqlite3.Row
                except Exception:
                    pass
                return con
    except Exception:
        pass

    # Fallback: local sqlite file
    import sqlite3
    default_db = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "data", "lowlife.db")
    )
    db_path = os.getenv("DB_FILE", default_db)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    return con


# --- engine wiring -------------------------------------------------------------
_registry = TagRegistry(TAGS_DIR)
_registry.load_all()
_engine = TagEngine(_registry)


def ensure_tags_schema(*_args, **_kwargs) -> bool:
    # No-op for the file-backed engine, kept for legacy callers
    return True


def engine() -> TagEngine:
    return _engine


# --- helpers ------------------------------------------------------------------
def _entity_id(owner_kind_or_entity: str, owner_id: Optional[str] = None) -> str:
    """
    Normalize an entity identifier. Accepts either a fully-qualified entity_id
    or a legacy (owner_kind, owner_id) pair.
    """
    if owner_id is None:
        return str(owner_kind_or_entity)
    return f"{owner_kind_or_entity}:{owner_id}"


class _Row(dict):
    """Tiny row shim that behaves like a sqlite3.Row for dict-style access."""
    __getattr__ = dict.get


# --- new-style convenience API ------------------------------------------------
def list_entity_tags(entity_id: str) -> List[TagInstance]:
    return _engine.list(entity_id)


def apply_tag(*args, **kwargs) -> TagInstance:
    """
    Compat wrapper:
      - apply_tag(entity_id, key, **kwargs)
      - apply_tag(owner_kind, owner_id, key, **kwargs)
    """
    if len(args) == 2:
        entity_id, key = args  # type: ignore[misc]
    elif len(args) == 3:
        okind, oid, key = args  # type: ignore[misc]
        entity_id = _entity_id(okind, str(oid))
    else:
        raise TypeError("apply_tag() expects (entity_id, key) or (owner_kind, owner_id, key)")
    return _engine.apply(entity_id, str(key), **kwargs)


def remove_tag(*args) -> bool:
    """
    Compat wrapper:
      - remove_tag(entity_id, key)
      - remove_tag(owner_kind, owner_id, key)
    """
    if len(args) == 2:
        entity_id, key = args  # type: ignore[misc]
    elif len(args) == 3:
        okind, oid, key = args  # type: ignore[misc]
        entity_id = _entity_id(okind, str(oid))
    else:
        raise TypeError("remove_tag() expects (entity_id, key) or (owner_kind, owner_id, key)")
    return _engine.remove(entity_id, str(key))


def has_tag(*args) -> bool:
    """
    Compat wrapper:
      - has_tag(entity_id, key)
      - has_tag(owner_kind, owner_id, key)
    """
    if len(args) == 2:
        entity_id, key = args  # type: ignore[misc]
    elif len(args) == 3:
        okind, oid, key = args  # type: ignore[misc]
        entity_id = _entity_id(okind, str(oid))
    else:
        raise TypeError("has_tag() expects (entity_id, key) or (owner_kind, owner_id, key)")
    return _engine.has(entity_id, str(key))


def iter_entities_with_tag_prefix(prefix: str):
    for ent, tags in _engine.active.items():
        if any(k.startswith(prefix) for k in tags.keys()):
            yield ent


# --- legacy DAL surface kept for older cogs -----------------------------------
def list_instances(owner_kind: str, owner_id: str):
    """
    Return a list of row-like dicts representing active tag instances for an entity.
    Keys provided for compatibility: 'key', 'tag', 'props', 'entity_id', 'owner_kind', 'owner_id', 'created_at', 'source'
    """
    ent = _entity_id(owner_kind, owner_id)
    items = _engine.list(ent)
    rows = []
    for inst in items:
        key = getattr(inst, "key", None) or getattr(inst, "tag", None)
        props = getattr(inst, "props", None) or {}
        created_at = getattr(inst, "created_at", None)
        rows.append(
            _Row(
                {
                    "entity_id": ent,
                    "owner_kind": owner_kind,
                    "owner_id": owner_id,
                    "key": key,
                    "tag": key,  # old code sometimes looked for 'tag'
                    "props": props,
                    "created_at": created_at,
                    "source": "engine",
                }
            )
        )
    return rows


def clear_owner(owner_kind: str, owner_id: str) -> int:
    """
    Remove all active tags for the (owner_kind, owner_id) entity.
    Returns the number of tags removed.
    """
    ent = _entity_id(owner_kind, owner_id)
    keys = list(_engine.active.get(ent, {}).keys())
    removed = 0
    for k in keys:
        if _engine.remove(ent, k):
            removed += 1
    return removed
