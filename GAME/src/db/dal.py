# GAME/src/db/dal.py
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# Reuse Custodian DB if available so everything lives together
try:
    from src.core.custodian import ledger  # type: ignore
    EVENTS_DB: Path = Path(getattr(ledger, "DB_PATH"))  # type: ignore[attr-defined]
except Exception:
    # fall back: GAME/data/audit.sqlite
    EVENTS_DB = Path(__file__).parents[2] / "data" / "audit.sqlite"


# ---------------- core: events ----------------
def ensure_events_schema() -> None:
    """Create/upgrade the events table and indexes."""
    EVENTS_DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(EVENTS_DB) as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS events(
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_utc      TEXT    NOT NULL,
                guild_id    INTEGER,
                channel_id  INTEGER,
                author_id   INTEGER,
                kind        TEXT    NOT NULL,
                content     TEXT,
                payload     TEXT
            );
            CREATE INDEX IF NOT EXISTS ix_events_guild_ts   ON events(guild_id, ts_utc);
            CREATE INDEX IF NOT EXISTS ix_events_author_ts  ON events(author_id, ts_utc);
            """
        )
        con.commit()


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def append_event(
    kind: str,
    author_id: int | str | None = None,
    channel_id: int | str | None = None,
    payload: dict | str | None = None,
    *,
    guild_id: int | str | None = None,
    content: str | None = None,
) -> None:
    """Insert one row into events."""
    ensure_events_schema()
    if isinstance(payload, dict):
        payload = json.dumps(payload, separators=(",", ":"))
    with sqlite3.connect(EVENTS_DB) as con:
        con.execute(
            """
            INSERT INTO events(ts_utc, guild_id, channel_id, author_id, kind, content, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _utc_iso(),
                int(guild_id) if guild_id is not None else None,
                int(channel_id) if channel_id is not None else None,
                int(author_id) if author_id is not None else None,
                kind,
                content,
                payload,
            ),
        )
        con.commit()


# ---------------- support for welcome cog ----------------
def ensure_npc_intro_table() -> None:
    """Table used by the welcome system to persist NPC intro cards."""
    EVENTS_DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(EVENTS_DB) as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS npc_intro(
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_utc      TEXT    NOT NULL,
                user_id     INTEGER NOT NULL,
                npc_name    TEXT    NOT NULL,
                content     TEXT    NOT NULL,
                image_url   TEXT,
                guild_id    INTEGER,
                channel_id  INTEGER
            );
            CREATE INDEX IF NOT EXISTS ix_npc_intro_user_ts ON npc_intro(user_id, ts_utc);
            """
        )
        con.commit()


def log_npc_intro(
    *,
    user_id: int | str,
    npc_name: str,
    content: str,
    image_url: str | None = None,
    guild_id: int | str | None = None,
    channel_id: int | str | None = None,
) -> None:
    """Record a welcome/intro card emission and mirror a lightweight event."""
    ensure_npc_intro_table()
    ts = _utc_iso()
    with sqlite3.connect(EVENTS_DB) as con:
        con.execute(
            """
            INSERT INTO npc_intro(ts_utc, user_id, npc_name, content, image_url, guild_id, channel_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts,
                int(user_id),
                npc_name,
                content,
                image_url,
                int(guild_id) if guild_id is not None else None,
                int(channel_id) if channel_id is not None else None,
            ),
        )
        con.commit()

    # also mirror into events for the unified timeline
    append_event(
        "welcome.intro",
        author_id=user_id,
        channel_id=channel_id,
        guild_id=guild_id,
        content=content[:400],
        payload={"npc": npc_name, "image_url": image_url},
    )
