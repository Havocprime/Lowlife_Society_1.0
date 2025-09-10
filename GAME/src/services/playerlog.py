# ======================================================================
# FILE: GAME/src/services/playerlog.py   (robust _conn fallback)
# ======================================================================
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, Optional

from src.db import dal as core_dal

log = logging.getLogger("playerlog")


# ----------------------------- schema ---------------------------------
def _conn():
    """
    Get a DB connection from src.db.dal using several common patterns.
    Returns the first attribute/callable that yields an object with .execute.
    """
    # 1) Common callables/attributes that might return/hold a connection
    for name in ("_conn", "conn", "get_conn", "get_connection", "connection"):
        obj = getattr(core_dal, name, None)
        # attribute already is a connection
        if obj is not None and hasattr(obj, "execute"):
            return obj
        # callable that returns a connection
        if callable(obj):
            try:
                c = obj()
                if hasattr(c, "execute"):
                    return c
            except TypeError:
                # some projects expose a property-like callable taking no args;
                # ignore signature mismatches and keep probing
                pass

    # 2) Common module-level connection singletons
    for name in ("CONN", "DB", "SQL", "CONNECTION", "_CONN", "_DB"):
        obj = getattr(core_dal, name, None)
        if obj is not None and hasattr(obj, "execute"):
            return obj

    # 3) Constructors that open the default DB
    for name in ("connect", "open", "get_db"):
        fn = getattr(core_dal, name, None)
        if callable(fn):
            c = fn()
            if hasattr(c, "execute"):
                return c

    raise RuntimeError("playerlog: could not acquire DB connection from src.db.dal")

def ensure_playerlog_schema() -> None:
    """
    Player events + expiry watches for tags.
    """
    con = _conn()
    # main immutable log
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS player_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            owner_kind  TEXT    NOT NULL,
            owner_id    INTEGER NOT NULL,
            kind        TEXT    NOT NULL,
            anchor_path TEXT,
            tag_id      INTEGER,
            tag_name    TEXT,
            delta_hp    INTEGER,
            hp_after    INTEGER,
            source_kind TEXT,
            source_ref  TEXT,
            metadata    TEXT
        )
        """
    )
    con.execute("CREATE INDEX IF NOT EXISTS idx_pe_owner ON player_events(owner_kind, owner_id, id DESC)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_pe_kind  ON player_events(kind, id DESC)")

    # watches for tag expirations (engine-agnostic)
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS player_tag_watches (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            instance_id     INTEGER NOT NULL,
            owner_kind      TEXT    NOT NULL,
            owner_id        INTEGER NOT NULL,
            tag_id          INTEGER NOT NULL,
            tag_name        TEXT    NOT NULL,
            anchor_path     TEXT,
            expires_at      TEXT    NOT NULL,      -- ISO8601 UTC
            fatal_on_expire INTEGER NOT NULL DEFAULT 0,
            processed       INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    con.execute("CREATE INDEX IF NOT EXISTS idx_ptw_due ON player_tag_watches(processed, expires_at)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_ptw_owner ON player_tag_watches(owner_kind, owner_id)")
    try:
        con.commit()
    except Exception:
        # some DALs auto-commit; ignore if commit isn't needed
        pass


# ----------------------------- writer ---------------------------------
def append_event(
    *,
    owner_kind: str,
    owner_id: int,
    kind: str,
    anchor_path: Optional[str] = None,
    tag_id: Optional[int] = None,
    tag_name: Optional[str] = None,
    delta_hp: Optional[int] = None,
    hp_after: Optional[int] = None,
    source_kind: Optional[str] = None,
    source_ref: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> int:
    ensure_playerlog_schema()
    con = _conn()
    cur = con.execute(
        """
        INSERT INTO player_events
            (owner_kind, owner_id, kind, anchor_path, tag_id, tag_name,
             delta_hp, hp_after, source_kind, source_ref, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            owner_kind,
            int(owner_id),
            kind,
            anchor_path,
            int(tag_id) if tag_id is not None else None,
            tag_name,
            int(delta_hp) if delta_hp is not None else None,
            int(hp_after) if hp_after is not None else None,
            source_kind,
            source_ref,
            json.dumps(metadata or {}, ensure_ascii=False),
        ),
    )
    try:
        con.commit()
    except Exception:
        pass
    return int(cur.lastrowid)


def log_hp_delta(
    *,
    owner_kind: str,
    owner_id: int,
    delta_hp: int,
    hp_after: int,
    source_kind: Optional[str] = None,
    source_ref: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> int:
    return append_event(
        owner_kind=owner_kind,
        owner_id=owner_id,
        kind="hp.delta",
        delta_hp=int(delta_hp),
        hp_after=int(hp_after),
        source_kind=source_kind,
        source_ref=source_ref,
        metadata=metadata,
    )


def log_tag_tick(
    *,
    owner_kind: str,
    owner_id: int,
    tag_id: int,
    tag_name: str,
    anchor_path: Optional[str],
    delta_hp: Optional[int] = None,
    hp_after: Optional[int] = None,
    source_kind: Optional[str] = None,
    source_ref: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> int:
    return append_event(
        owner_kind=owner_kind,
        owner_id=owner_id,
        kind="tag.tick",
        anchor_path=anchor_path,
        tag_id=int(tag_id),
        tag_name=tag_name,
        delta_hp=int(delta_hp) if delta_hp is not None else None,
        hp_after=int(hp_after) if hp_after is not None else None,
        source_kind=source_kind,
        source_ref=source_ref,
        metadata=metadata,
    )


def log_tag_expired(
    *,
    owner_kind: str,
    owner_id: int,
    tag_id: int,
    tag_name: str,
    anchor_path: Optional[str],
    fatal_on_expire: bool,
    source_kind: Optional[str] = None,
    source_ref: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> int:
    meta = dict(metadata or {})
    meta["fatal_on_expire"] = bool(fatal_on_expire)
    return append_event(
        owner_kind=owner_kind,
        owner_id=owner_id,
        kind="tag.expired",
        anchor_path=anchor_path,
        tag_id=int(tag_id),
        tag_name=tag_name,
        source_kind=source_kind,
        source_ref=source_ref,
        metadata=meta,
    )


def log_player_death(
    *,
    owner_kind: str,
    owner_id: int,
    reason: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> int:
    meta = dict(metadata or {})
    meta["reason"] = reason
    return append_event(
        owner_kind=owner_kind,
        owner_id=owner_id,
        kind="player.death",
        metadata=meta,
    )


# ----------------------------- reader ---------------------------------
def list_events(
    owner_kind: str,
    owner_id: int,
    *,
    limit: int = 50,
    before_id: Optional[int] = None,
    kinds: Optional[Iterable[str]] = None,
) -> list[dict]:
    ensure_playerlog_schema()
    clauses = ["owner_kind = ?", "owner_id = ?"]
    args: list[Any] = [owner_kind, int(owner_id)]

    if before_id:
        clauses.append("id < ?")
        args.append(int(before_id))
    if kinds:
        ks = list(kinds)
        placeholders = ",".join("?" for _ in ks)
        clauses.append(f"kind IN ({placeholders})")
        args.extend(ks)

    sql = f"""
        SELECT id, ts, kind, anchor_path, tag_id, tag_name,
               delta_hp, hp_after, source_kind, source_ref, metadata
        FROM player_events
        WHERE {' AND '.join(clauses)}
        ORDER BY id DESC
        LIMIT ?
    """
    args.append(int(limit))
    con = _conn()
    rows = [dict(r) for r in con.execute(sql, args).fetchall()]
    for r in rows:
        try:
            r["metadata"] = json.loads(r.get("metadata") or "{}")
        except Exception:
            r["metadata"] = {}
    return rows


# --------------------- tag expiry watch API ---------------------------
def schedule_tag_expiry_watch(
    *,
    instance_id: int,
    owner_kind: str,
    owner_id: int,
    tag_id: int,
    tag_name: str,
    anchor_path: Optional[str],
    duration_ms: int,
    fatal_on_expire: bool,
) -> int:
    """
    Store a due-time for a tag instance so we can emit a tag.expired + optional death,
    independent of the engine.
    """
    ensure_playerlog_schema()
    expires_at = (datetime.now(timezone.utc) + timedelta(milliseconds=int(duration_ms))).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )
    con = _conn()
    cur = con.execute(
        """
        INSERT INTO player_tag_watches
            (instance_id, owner_kind, owner_id, tag_id, tag_name, anchor_path, expires_at, fatal_on_expire)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(instance_id),
            owner_kind,
            int(owner_id),
            int(tag_id),
            tag_name,
            anchor_path,
            expires_at,
            1 if fatal_on_expire else 0,
        ),
    )
    try:
        con.commit()
    except Exception:
        pass
    return int(cur.lastrowid)


def pull_due_expiries(now_iso: Optional[str] = None, *, limit: int = 200) -> list[dict]:
    """
    Fetch due-but-unprocessed watches.
    """
    ensure_playerlog_schema()
    con = _conn()
    if not now_iso:
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    rows = con.execute(
        """
        SELECT id, instance_id, owner_kind, owner_id, tag_id, tag_name, anchor_path, expires_at, fatal_on_expire
        FROM player_tag_watches
        WHERE processed = 0 AND expires_at <= ?
        ORDER BY id ASC
        LIMIT ?
        """,
        (now_iso, int(limit)),
    ).fetchall()
    return [dict(r) for r in rows]


def mark_expiry_processed(row_id: int) -> None:
    con = _conn()
    con.execute("UPDATE player_tag_watches SET processed = 1 WHERE id = ?", (int(row_id),))
    try:
        con.commit()
    except Exception:
        pass
# ======================================================================
