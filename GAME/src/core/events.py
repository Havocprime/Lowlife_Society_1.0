from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path("data") / "lowlife.db"

def _conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA journal_mode=WAL;")
    return con

def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def init():
    with _conn() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_utc   TEXT NOT NULL,
            user_id  INTEGER NOT NULL,
            guild_id INTEGER NOT NULL,
            kind     TEXT NOT NULL,      -- presence|message|roles|voice|join|leave|invite
            payload  TEXT
        )
        """)
        con.execute("""
        CREATE TABLE IF NOT EXISTS admin_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_utc   TEXT NOT NULL,
            guild_id INTEGER NOT NULL,
            user_id  INTEGER NOT NULL,
            author_id INTEGER NOT NULL,
            note     TEXT NOT NULL
        )
        """)
    return DB_PATH

# -------- event log queries --------
def recent_events(user_id: int, limit: int = 20):
    with _conn() as con:
        cur = con.execute(
            "SELECT ts_utc, kind, payload FROM events WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (int(user_id), int(limit)),
        )
        return list(cur.fetchall())

def last_event_time(user_id: int) -> str | None:
    with _conn() as con:
        cur = con.execute(
            "SELECT ts_utc FROM events WHERE user_id=? ORDER BY id DESC LIMIT 1",
            (int(user_id),),
        )
        row = cur.fetchone()
        return row[0] if row else None

def message_count(user_id: int, days: int, guild_id: int | None = None) -> int:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat().replace("+00:00","Z")
    q = "SELECT COUNT(*) FROM events WHERE user_id=? AND kind='message' AND ts_utc>=?"
    params: list[object] = [int(user_id), since]
    if guild_id:
        q += " AND guild_id=?"
        params.append(int(guild_id))
    with _conn() as con:
        cur = con.execute(q, tuple(params))
        return int(cur.fetchone()[0])

# -------- admin notes --------
def add_admin_note(guild_id: int, user_id: int, author_id: int, note: str) -> int:
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO admin_notes (ts_utc, guild_id, user_id, author_id, note) VALUES (?,?,?,?,?)",
            (_utcnow(), int(guild_id), int(user_id), int(author_id), note.strip()),
        )
        return int(cur.lastrowid)

def list_admin_notes(guild_id: int, user_id: int, limit: int | None = None):
    q = "SELECT id, ts_utc, author_id, note FROM admin_notes WHERE guild_id=? AND user_id=? ORDER BY id DESC"
    params: tuple[object, ...]
    if limit:
        q += " LIMIT ?"
        params = (int(guild_id), int(user_id), int(limit))
    else:
        params = (int(guild_id), int(user_id))
    with _conn() as con:
        cur = con.execute(q, params)
        return list(cur.fetchall())

def delete_admin_note(guild_id: int, note_id: int) -> bool:
    with _conn() as con:
        cur = con.execute("DELETE FROM admin_notes WHERE guild_id=? AND id=?", (int(guild_id), int(note_id)))
        return cur.rowcount > 0

# ensure tables exist at import time
init()
