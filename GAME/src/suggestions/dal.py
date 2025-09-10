# ======================================================================
# FILE: GAME/src/suggestions/dal.py
# ======================================================================
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

DB_DIR = Path("GAME/data")
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "suggestions.sqlite"
SILENT_LOG = DB_DIR / "suggestions_denied_silent.log"

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS tickets(
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  guild_id        INTEGER NOT NULL,
  user_id         INTEGER NOT NULL,
  channel_id      INTEGER,
  message_id      INTEGER,
  content         TEXT NOT NULL,
  status          TEXT NOT NULL DEFAULT 'NEW',
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL,
  decided_by      INTEGER,
  decision_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
CREATE INDEX IF NOT EXISTS idx_tickets_guild ON tickets(guild_id);
CREATE INDEX IF NOT EXISTS idx_tickets_user  ON tickets(user_id);

CREATE TABLE IF NOT EXISTS ticket_events(
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  ticket_id  INTEGER NOT NULL,
  actor_id   INTEGER NOT NULL,
  old_status TEXT,
  new_status TEXT NOT NULL,
  note       TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY(ticket_id) REFERENCES tickets(id)
);
"""

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def ensure_schema() -> None:
    with connect() as con:
        con.executescript(SCHEMA)
        con.commit()

@dataclass
class Ticket:
    id: int
    guild_id: int
    user_id: int
    channel_id: Optional[int]
    message_id: Optional[int]
    content: str
    status: str
    created_at: str
    updated_at: str
    decided_by: Optional[int]
    decision_reason: Optional[str]

def create_ticket(guild_id: int, user_id: int, content: str, channel_id: int | None, message_id: int | None) -> int:
    with connect() as con:
        cur = con.execute(
            """INSERT INTO tickets (guild_id, user_id, channel_id, message_id, content, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'NEW', ?, ?)""",
            (guild_id, user_id, channel_id, message_id, content, _now_iso(), _now_iso()),
        )
        ticket_id = cur.lastrowid
        con.execute(
            "INSERT INTO ticket_events(ticket_id, actor_id, old_status, new_status, note, created_at) VALUES(?,?,?,?,?,?)",
            (ticket_id, user_id, None, "NEW", "submitted", _now_iso()),
        )
        con.commit()
        return ticket_id

def get_ticket(ticket_id: int) -> Optional[Ticket]:
    with connect() as con:
        row = con.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        if not row:
            return None
        return Ticket(**dict(row))

def list_tickets(guild_id: int, status: Optional[str]=None, limit: int=50, offset: int=0) -> list[Ticket]:
    with connect() as con:
        if status:
            rows = con.execute(
                "SELECT * FROM tickets WHERE guild_id=? AND status=? ORDER BY id DESC LIMIT ? OFFSET ?",
                (guild_id, status, limit, offset),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM tickets WHERE guild_id=? ORDER BY id DESC LIMIT ? OFFSET ?",
                (guild_id, limit, offset),
            ).fetchall()
        return [Ticket(**dict(r)) for r in rows]

def list_tickets_by_user(guild_id: int, user_id: int, limit: int=20, offset: int=0) -> list[Ticket]:
    with connect() as con:
        rows = con.execute(
            "SELECT * FROM tickets WHERE guild_id=? AND user_id=? ORDER BY id DESC LIMIT ? OFFSET ?",
            (guild_id, user_id, limit, offset),
        ).fetchall()
        return [Ticket(**dict(r)) for r in rows]

def set_status(ticket_id: int, actor_id: int, new_status: str, reason: Optional[str]) -> bool:
    with connect() as con:
        row = con.execute("SELECT status FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        if not row:
            return False
        old_status = row["status"]
        con.execute(
            "UPDATE tickets SET status=?, decided_by=?, decision_reason=?, updated_at=? WHERE id=?",
            (new_status, actor_id, reason, _now_iso(), ticket_id),
        )
        con.execute(
            "INSERT INTO ticket_events(ticket_id, actor_id, old_status, new_status, note, created_at) VALUES(?,?,?,?,?,?)",
            (ticket_id, actor_id, old_status, new_status, reason or "", _now_iso()),
        )
        con.commit()
        return True

def add_note(ticket_id: int, actor_id: int, note: str) -> bool:
    with connect() as con:
        row = con.execute("SELECT id FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        if not row:
            return False
        con.execute(
            "INSERT INTO ticket_events(ticket_id, actor_id, old_status, new_status, note, created_at) VALUES(?,?,?,?,?,?)",
            (ticket_id, actor_id, None, "NOTE", note, _now_iso()),
        )
        con.commit()
        return True

def stats_by_status(guild_id: int) -> dict[str, int]:
    with connect() as con:
        rows = con.execute(
            "SELECT status, COUNT(*) as c FROM tickets WHERE guild_id=? GROUP BY status",
            (guild_id,)
        ).fetchall()
        return {r["status"]: r["c"] for r in rows}

def export_rows(guild_id: int, status: Optional[str]=None) -> Iterable[sqlite3.Row]:
    with connect() as con:
        if status:
            cur = con.execute("SELECT * FROM tickets WHERE guild_id=? AND status=? ORDER BY id", (guild_id, status))
        else:
            cur = con.execute("SELECT * FROM tickets WHERE guild_id=? ORDER BY id", (guild_id,))
        for row in cur:
            yield row

def fetch_recent_for_duplicate_check(guild_id: int, limit: int = 100) -> list[tuple[int, str]]:
    with connect() as con:
        rows = con.execute(
            "SELECT id, content FROM tickets WHERE guild_id=? ORDER BY id DESC LIMIT ?",
            (guild_id, limit),
        ).fetchall()
        return [(r["id"], r["content"]) for r in rows]

def append_silent_log(ticket_id: int, user_id: int, content: str, actor_id: int, reason: str | None) -> None:
    SILENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{_now_iso()} | ticket={ticket_id} user={user_id} actor={actor_id} status=DENIED_SILENT reason={reason or ''} :: {content}\n"
    with open(SILENT_LOG, "a", encoding="utf-8") as f:
        f.write(line)

# NEW: simple LIKE search for admin command
def search_tickets(guild_id: int, query: str, limit: int = 25) -> list[Ticket]:
    like = f"%{query}%"
    with connect() as con:
        rows = con.execute(
            "SELECT * FROM tickets WHERE guild_id=? AND content LIKE ? ORDER BY id DESC LIMIT ?",
            (guild_id, like, limit),
        ).fetchall()
        return [Ticket(**dict(r)) for r in rows]
