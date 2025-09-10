from __future__ import annotations
import json, sqlite3, os, time
from typing import Optional, Dict, Any, List

from datetime import datetime, timezone, timedelta

# Optional import; not required here.
try:
    from src.db import dal as core_dal  # noqa: F401
except Exception:
    core_dal = None

# --- Add near your other DAL helpers ---
from typing import List, Tuple

from pathlib import Path

DB_PATH = "data/game.db"  # or your existing DB_PATH



# ---------- DB plumbing ----------



def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def _now_ms() -> int:
    return int(time.time() * 1000)

# --- NEW: catalog helpers ----------------------------------------------------
def get_tag_id_by_name(con: sqlite3.Connection, name: str) -> int:
    row = con.execute("SELECT id FROM tags WHERE name=?", (name,)).fetchone()
    if not row:
        raise ValueError(f"Unknown tag name: {name}")
    return int(row["id"])

def get_effective_tick_ms(con: sqlite3.Connection, tag_id: int, override_tick_ms: int | None) -> int | None:
    if override_tick_ms is not None:
        return override_tick_ms
    row = con.execute("SELECT tick_ms FROM tags WHERE id=?", (tag_id,)).fetchone()
    return int(row["tick_ms"]) if row and row["tick_ms"] is not None else None

# --- NEW: instances helpers --------------------------------------------------
def upsert_instance_by_name(
    owner_kind: str,
    owner_id: int,
    anchor_path: str,
    tag_name: str,
    *,
    stacks: int = 1,
    intensity: float = 1.0,
    tick_ms: int | None = None,
    duration_ms: int | None = None,
    metadata: dict | None = None,
    source_kind: str | None = None,
    source_ref: str | None = None,
) -> None:
    """
    Create or refresh a logical singleton instance per (owner, anchor, tag).
    Uses UNIQUE INDEX uq_tag_anchor_singleton(owner_kind, owner_id, anchor_path, tag_id).
    """
    with _conn() as con:
        tag_id = get_tag_id_by_name(con, tag_name)
        now = _now_ms()
        eff_tick = get_effective_tick_ms(con, tag_id, tick_ms)  # may be None (non-ticking)
        next_tick_at = (now + eff_tick) if eff_tick else None
        expires_at = (now + duration_ms) if duration_ms else None
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)

        con.execute(
            """
            INSERT INTO tag_instances (
              owner_kind, owner_id, anchor_path, tag_id,
              stacks, intensity, state, metadata,
              source_kind, source_ref,
              created_at, next_tick_at, last_tick_at, expires_at, tick_ms
            ) VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, NULL, ?, ?)
            ON CONFLICT(owner_kind, owner_id, anchor_path, tag_id)
            DO UPDATE SET
              stacks      = excluded.stacks,
              intensity   = excluded.intensity,
              state       = 'active',
              metadata    = excluded.metadata,
              source_kind = excluded.source_kind,
              source_ref  = excluded.source_ref,
              next_tick_at= excluded.next_tick_at,
              expires_at  = excluded.expires_at,
              tick_ms     = COALESCE(excluded.tick_ms, tag_instances.tick_ms)
            """,
            (
                owner_kind, owner_id, anchor_path, tag_id,
                stacks, intensity, meta_json,
                source_kind, source_ref,
                now, next_tick_at, expires_at, eff_tick,
            ),
        )
        con.commit()


# (optional) tiny read helper used by /tag_list or debugging
def list_instances_for(owner_kind: str, owner_id: int) -> list[sqlite3.Row]:
    with _conn() as con:
        return con.execute(
            """
            SELECT ti.*, t.name AS tag_name
            FROM tag_instances ti
            JOIN tags t ON t.id = ti.tag_id
            WHERE ti.owner_kind=? AND ti.owner_id=?
            ORDER BY ti.anchor_path, t.name
            """,
            (owner_kind, owner_id),
        ).fetchall()
    

    


def utc_now() -> datetime:
    return datetime.now(timezone.utc)

def archive_inactive_older_than(cutoff: datetime) -> int:
    """
    Set state='archived' for non-active tag instances whose last tick (or created)
    is older than `cutoff`. Returns number of rows touched.
    """
    res = db.execute("""
        UPDATE tags_instances
           SET state='archived', archived_at=?
         WHERE state!='active'
           AND COALESCE(last_tick_at, created_at) < ?
    """, (utc_now(), cutoff))
    return res.rowcount

def delete_inactive_older_than(cutoff: datetime) -> int:
    res = db.execute("""
        DELETE FROM tags_instances
         WHERE state!='active'
           AND COALESCE(last_tick_at, created_at) < ?
    """, (cutoff,))
    return res.rowcount

DB_PATH = os.getenv("DB_PATH", os.path.join(os.getcwd(), "data", "lowlife.sqlite"))

def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def now_ms() -> int:
    return int(time.time() * 1000)

def normalize_key(name: str) -> str:
    s = name.strip().lower()
    out, last_us = [], False
    for ch in s:
        if ch.isalnum():
            out.append(ch); last_us = False
        else:
            if not last_us:
                out.append("_"); last_us = True
    return "".join(out).strip("_")

# ---------- catalog ----------
def get_tag_by_name(name: str) -> Optional[dict]:
    """Look up by exact name OR normalized script_key."""
    k = normalize_key(name)
    with _conn() as con:
        r = con.execute(
            "SELECT * FROM tags WHERE script_key=? OR name=?",
            (k, name),
        ).fetchone()
        return dict(r) if r else None

def upsert_tag(
    *,
    name: str,
    kind: str = "dynamic",
    polarity: Optional[str] = None,
    tick_ms: Optional[int] = 1500,
    base_intensity: float = 1.0,
    max_stacks: int = 5,
    stack_policy: str = "add",
    exclusivity_key: str = "",
    refresh_policy: str = "full",
    duration_ms: int = 0,
    script_key: Optional[str] = None,
) -> int:
    """Upserts into the current schema columns only."""
    sk = script_key or normalize_key(name)
    with _conn() as con:
        con.execute(
            """
            INSERT INTO tags(
                name, script_key, kind, polarity, tick_ms, base_intensity,
                max_stacks, stack_policy, exclusivity_key, refresh_policy, duration_ms
            )
            VALUES(?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(name) DO UPDATE SET
                script_key      = excluded.script_key,
                kind            = excluded.kind,
                polarity        = excluded.polarity,
                tick_ms         = excluded.tick_ms,
                base_intensity  = excluded.base_intensity,
                max_stacks      = excluded.max_stacks,
                stack_policy    = excluded.stack_policy,
                exclusivity_key = excluded.exclusivity_key,
                refresh_policy  = excluded.refresh_policy,
                duration_ms     = excluded.duration_ms
            """,
            (
                name, sk, kind, polarity, tick_ms, base_intensity,
                max_stacks, stack_policy, exclusivity_key, refresh_policy, duration_ms,
            ),
        )
        row = con.execute("SELECT id FROM tags WHERE name=?", (name,)).fetchone()
        return int(row["id"])

# ---------- instances ----------
def add_or_stack(
    *,
    owner_kind: str,
    owner_id: int,
    anchor_path: str,
    tag_id: int,
    stacks: int = 1,
    intensity: float = 1.0,
    state: Optional[str] = None,
    duration_ms: Optional[int] = None,
    tick_ms: Optional[int] = None,
    source_kind: Optional[str] = None,
    source_ref: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> int:
    """
    Singleton per (owner,anchor,tag) â€” if present, stack; else insert. Returns instance id.
    """
    meta_json = None if metadata is None else json.dumps(metadata)
    now = now_ms()

    with _conn() as con:
        cur = con.execute(
            """SELECT * FROM tag_instances
               WHERE owner_kind=? AND owner_id=? AND anchor_path=? AND tag_id=?""",
            (owner_kind, owner_id, anchor_path, tag_id),
        )
        row = cur.fetchone()

        if row:
            iid = int(row["id"])
            new_stacks = max(1, int(row["stacks"]) + int(stacks))

            # Only schedule a tick if the tag is ticking and we don't already have one
            next_tick = row["next_tick_at"]
            if tick_ms and not next_tick:
                next_tick = now + int(tick_ms)

            # Extend expiry if a duration is specified
            new_expires = row["expires_at"]
            if duration_ms:
                base = int(row["expires_at"]) if row["expires_at"] else now
                new_expires = base + int(duration_ms)

            con.execute(
                """UPDATE tag_instances
                     SET stacks=?,
                         intensity=?,
                         state=COALESCE(?, 'active'),
                         next_tick_at=?,
                         expires_at=?
                   WHERE id=?""",
                (new_stacks, float(intensity), state, next_tick, new_expires, iid),
            )
            return iid

        # insert fresh
        next_tick_at = (now + int(tick_ms)) if tick_ms else None
        expires_at = (now + int(duration_ms)) if duration_ms else None

        cur = con.execute(
            """INSERT INTO tag_instances
                 (owner_kind, owner_id, anchor_path, tag_id,
                  stacks, intensity, state, metadata,
                  source_kind, source_ref, created_at,
                  next_tick_at, expires_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                owner_kind, owner_id, anchor_path, tag_id,
                max(1, int(stacks)), float(intensity), state or "active", meta_json,
                source_kind, source_ref, now,
                next_tick_at, expires_at
            ),
        )
        return int(cur.lastrowid)

def list_instances(owner_kind: str, owner_id: int) -> List[sqlite3.Row]:
    with _conn() as con:
        return con.execute(
            """SELECT ti.*, t.name, t.kind, t.tick_ms, t.exclusivity_key, t.script_key
               FROM tag_instances ti
               JOIN tags t ON t.id = ti.tag_id
               WHERE ti.owner_kind=? AND ti.owner_id=?""",
            (owner_kind, owner_id)
        ).fetchall()

def clear_owner(owner_kind: str, owner_id: int) -> int:
    with _conn() as con:
        cur = con.execute(
            "DELETE FROM tag_instances WHERE owner_kind=? AND owner_id=?",
            (owner_kind, owner_id),
        )
        return int(cur.rowcount)

# ---------- ticking ----------
def due_ticks(now_ms_val: int | None = None, limit: int = 500):
    """
    Return active instances whose next_tick_at is due, oldest first.
    Keys are shaped for the engine (expects 'id' and may read 'state_machine_json').
    """
    if now_ms_val is None:
        now_ms_val = now_ms()
    with _conn() as con:
        rows = con.execute(
            """
            SELECT
                i.id                           AS id,          -- engine expects this
                i.owner_kind,
                i.owner_id,
                i.anchor_path,
                i.stacks,
                i.intensity,
                i.state,
                COALESCE(i.metadata,'{}')      AS metadata_json,
                t.tick_ms                      AS tick_ms,
                t.name                         AS tag_name,
                t.polarity                     AS polarity,
                t.script_key                   AS script_key,
                NULL                           AS state_machine_json,  -- always present for engine
                i.next_tick_at                 AS next_tick_at,
                i.last_tick_at                 AS last_tick_at,
                i.expires_at                   AS expires_at
            FROM tag_instances i
            JOIN tags t ON t.id = i.tag_id
            WHERE i.state='active'
              AND i.next_tick_at IS NOT NULL
              AND i.next_tick_at <= :now_ms
            ORDER BY i.next_tick_at ASC
            LIMIT :limit
            """,
            {"now_ms": now_ms_val, "limit": limit},
        ).fetchall()
        return rows

def touch_tick(iid: int, *, next_tick_at: Optional[int], last_error: Optional[str] = None) -> None:
    with _conn() as con:
        con.execute(
            """UPDATE tag_instances
                  SET last_tick_at=?,
                      next_tick_at=?,
                      last_error=?
                WHERE id=?""",
            (now_ms(), next_tick_at, last_error, iid),
        )

def mark_ticked(instance_id: int):
    """Legacy helper: keep it numeric to match schema."""
    with _conn() as con:
        con.execute(
            "UPDATE tag_instances SET last_tick_at=? WHERE id=?",
            (now_ms(), instance_id),
        )

def set_state(instance_id: int, new_state: str):
    """Donâ€™t touch non-existent columns; keep it simple."""
    with _conn() as con:
        con.execute("UPDATE tag_instances SET state=? WHERE id=?", (new_state, instance_id))


def search_catalog_names(prefix: str, limit: int = 25) -> List[str]:
    """
    Return up to `limit` tag names whose names fuzzy-match `prefix`.
    Works with SQLite; adjust SQL if you use another DB.
    """
    # sanitize wildcards so user input can't go wild
    safe = (prefix or "").replace("%", "").replace("_", "")
    like = f"%{safe}%"
    rows = db.fetchall(
        "SELECT name FROM tags_catalog WHERE name LIKE ? ORDER BY name LIMIT ?",
        (like, limit),
    )
    return [r["name"] for r in rows]
