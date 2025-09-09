from __future__ import annotations
import json, sqlite3, os
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List

try:
    from src.db import dal as core_dal
except Exception:
    core_dal = None

DB_PATH = os.getenv("DB_PATH", os.path.join(os.getcwd(), "data", "lowlife.sqlite"))

def _conn() -> sqlite3.Connection:
    if core_dal and hasattr(core_dal, "get_conn"):
        return core_dal.get_conn()
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

# -------- catalog --------
def upsert_tag(*, name: str, kind: str = "dynamic", group: str | None = None,
               polarity: str | None = None, max_stacks: int = 1,
               tick_ms: int | None = None, duration_ms: int | None = None,
               visibility: str = "public", exclusivity: str | None = None,
               script_key: str | None = None,
               state_machine: Dict[str, Any] | None = None,
               modifiers: Dict[str, Any] | None = None) -> int:
    sm = json.dumps(state_machine) if state_machine else None
    mods = json.dumps(modifiers) if modifiers else None
    with _conn() as con:
        con.execute(
            """INSERT INTO tags(name,kind,"group",polarity,max_stacks,tick_ms,duration_ms,visibility,exclusivity,script_key,state_machine_json,modifiers_json)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(name) DO UPDATE SET
                 kind=excluded.kind, "group"=excluded."group", polarity=excluded.polarity,
                 max_stacks=excluded.max_stacks, tick_ms=excluded.tick_ms, duration_ms=excluded.duration_ms,
                 visibility=excluded.visibility, exclusivity=excluded.exclusivity, script_key=excluded.script_key,
                 state_machine_json=excluded.state_machine_json, modifiers_json=excluded.modifiers_json
            """,
            (name, kind, group, polarity, max_stacks, tick_ms, duration_ms, visibility, exclusivity, script_key, sm, mods),
        )
        row = con.execute("SELECT id FROM tags WHERE name=?", (name,)).fetchone()
        return int(row["id"])

def get_tag_by_name(name: str):
    with _conn() as con:
        return con.execute("SELECT * FROM tags WHERE name=?", (name,)).fetchone()

# -------- instances --------
def add_or_stack(*, owner_kind: str, owner_id: int, anchor_path: str,
                 tag_id: int, stacks: int = 1, intensity: float = 1.0,
                 polarity: str | None = None, confidence: float | None = None,
                 duration_ms: int | None = None, state: str | None = None,
                 source_kind: str | None = None, source_ref: str | None = None,
                 metadata: Dict[str, Any] | None = None) -> int:
    meta = json.dumps(metadata) if metadata else None
    expires_at = None
    if duration_ms:
        expires_at = (datetime.now(timezone.utc) + timedelta(milliseconds=duration_ms)).isoformat()

    with _conn() as con:
        cur = con.execute("""SELECT id, stacks FROM tag_instances
                             WHERE owner_kind=? AND owner_id=? AND anchor_path=? AND tag_id=?""",
                          (owner_kind, owner_id, anchor_path, tag_id))
        row = cur.fetchone()
        if row:
            new = max(1, row["stacks"] + stacks)
            con.execute("""UPDATE tag_instances SET stacks=?, intensity=?, polarity=COALESCE(?,polarity),
                           confidence=COALESCE(?,confidence), expires_at=? WHERE id=?""",
                        (new, intensity, polarity, confidence, expires_at, row["id"]))
            return int(row["id"])
        cur = con.execute("""INSERT INTO tag_instances(owner_kind, owner_id, anchor_path, tag_id, state, state_started_at,
                           stacks, intensity, polarity, confidence, source_kind, source_ref, metadata_json, expires_at)
                           VALUES(?,?,?,?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now'),?,?,?,?,?,?,?,?)""",
                          (owner_kind, owner_id, anchor_path, tag_id, state, stacks, intensity, polarity, confidence,
                           source_kind, source_ref, meta, expires_at))
        return int(cur.lastrowid)

def list_instances(owner_kind: str, owner_id: int) -> List[sqlite3.Row]:
    with _conn() as con:
        return con.execute(
            """SELECT ti.*, t.name, t.kind, t.tick_ms, t.exclusivity, t.state_machine_json, t.script_key
               FROM tag_instances ti JOIN tags t ON t.id = ti.tag_id
               WHERE ti.owner_kind=? AND ti.owner_id=?""",
            (owner_kind, owner_id)
        ).fetchall()

def clear_owner(owner_kind: str, owner_id: int) -> int:
    with _conn() as con:
        cur = con.execute("DELETE FROM tag_instances WHERE owner_kind=? AND owner_id=?", (owner_kind, owner_id))
        return cur.rowcount

# -------- ticking --------
def due_ticks(limit: int = 128):
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        return con.execute(
            """SELECT ti.*, t.name, t.tick_ms, t.script_key, t.state_machine_json
               FROM tag_instances ti JOIN tags t ON t.id = ti.tag_id
               WHERE t.tick_ms IS NOT NULL
                 AND (ti.last_tick_at IS NULL OR
                      (strftime('%s', ?) - strftime('%s', ti.last_tick_at)) * 1000 >= t.tick_ms)
                 AND (ti.expires_at IS NULL OR ti.expires_at > ?)
               LIMIT ?""",
            (now, now, limit)
        ).fetchall()

def mark_ticked(instance_id: int):
    with _conn() as con:
        con.execute("UPDATE tag_instances SET last_tick_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?", (instance_id,))

def set_state(instance_id: int, new_state: str):
    with _conn() as con:
        con.execute("""UPDATE tag_instances SET state=?, state_started_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
                       WHERE id=?""", (new_state, instance_id))
