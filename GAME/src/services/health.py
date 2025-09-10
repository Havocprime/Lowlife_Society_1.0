from __future__ import annotations
import logging
from typing import Optional, Tuple

# We reuse the same sqlite connection as tags so everything lives in one DB.
from src.systems.tags import dal as tag_dal

log = logging.getLogger("health")

SQL_CREATE = """
CREATE TABLE IF NOT EXISTS health_state (
  owner_kind   TEXT NOT NULL,
  owner_id     INTEGER NOT NULL,
  hp           INTEGER NOT NULL,
  max_hp       INTEGER NOT NULL,
  updated_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY (owner_kind, owner_id)
);
"""

def _conn():
    return tag_dal._conn()

def ensure_schema() -> None:
    con = _conn()
    with con:
        con.executescript(SQL_CREATE)

def _get_row(owner_kind: str, owner_id: int):
    con = _conn()
    return con.execute(
        "SELECT owner_kind, owner_id, hp, max_hp FROM health_state WHERE owner_kind=? AND owner_id=?",
        (owner_kind, owner_id),
    ).fetchone()

def _upsert(owner_kind: str, owner_id: int, hp: int, max_hp: int) -> None:
    con = _conn()
    with con:
        con.execute(
            """
            INSERT INTO health_state (owner_kind, owner_id, hp, max_hp)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(owner_kind, owner_id) DO UPDATE SET
              hp=excluded.hp,
              max_hp=excluded.max_hp,
              updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
            """,
            (owner_kind, owner_id, hp, max_hp),
        )

def get_state(owner_kind: str, owner_id: int, *, default_max_hp: int = 60) -> Tuple[int, int]:
    """
    Returns (hp, max_hp). If the row doesn't exist yet, seeds it at full health.
    Default max is 60 (matches your profile card screenshot); override as needed.
    """
    row = _get_row(owner_kind, owner_id)
    if row:
        return int(row["hp"]), int(row["max_hp"])
    _upsert(owner_kind, owner_id, default_max_hp, default_max_hp)
    return default_max_hp, default_max_hp

def set_max_hp(owner_kind: str, owner_id: int, max_hp: int, *, set_current_to_max: bool = False) -> None:
    hp, _ = get_state(owner_kind, owner_id)
    if set_current_to_max:
        hp = max_hp
    _upsert(owner_kind, owner_id, hp, max_hp)

def heal(owner_kind: str, owner_id: int, amount: int) -> int:
    """Heals and returns new HP."""
    if amount <= 0:
        return get_state(owner_kind, owner_id)[0]
    hp, max_hp = get_state(owner_kind, owner_id)
    hp = min(max_hp, hp + amount)
    _upsert(owner_kind, owner_id, hp, max_hp)
    log.info("[Health] +%s HP (heal) owner=%s/%s -> %s/%s", amount, owner_kind, owner_id, hp, max_hp)
    return hp

def apply_damage(
    *,
    owner_kind: str,
    owner_id: int,
    amount: int,
    kind: str = "generic",
    source: Optional[str] = None,
    anchor_path: str = "entity",
) -> int:
    """
    Applies damage, clamps at 0, persists, logs, and returns new HP.
    Signature matches what the tag bridge already calls.
    """
    if amount <= 0:
        return get_state(owner_kind, owner_id)[0]

    hp, max_hp = get_state(owner_kind, owner_id)
    new_hp = max(0, hp - amount)
    _upsert(owner_kind, owner_id, new_hp, max_hp)
    log.info("[Health] -%s HP (%s) owner=%s/%s @ %s source=%s -> %s/%s",
             amount, kind, owner_kind, owner_id, anchor_path, source or "unknown", new_hp, max_hp)
    return new_hp

# Ensure table exists on import
ensure_schema()
