# GAME/src/services/playerlog.py
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

# Reuse the same DB connection the tags system uses
from src.systems.tags.dal import _conn as _tags_conn

log = logging.getLogger("playerlog")

# ---------- schema ----------

def ensure_playerlog_schema() -> None:
    con = _tags_conn()
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS player_events (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_kind   TEXT    NOT NULL,
            owner_id     INTEGER NOT NULL,
            ts           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            event        TEXT    NOT NULL,
            source       TEXT,
            data_json    TEXT
        )
        """
    )
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_player_events_owner ON player_events(owner_kind, owner_id, ts DESC)"
    )
    con.commit()

# ---------- api ----------

def log_event(
    owner_kind: str,
    owner_id: int,
    event: str,
    *,
    source: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
) -> None:
    """Append a structured event row for a player."""
    con = _tags_conn()
    con.execute(
        "INSERT INTO player_events (owner_kind, owner_id, event, source, data_json) VALUES (?, ?, ?, ?, ?)",
        (owner_kind, int(owner_id), event, source, json.dumps(data or {}, ensure_ascii=False)),
    )
    con.commit()

def kill(
    owner_kind: str,
    owner_id: int,
    *,
    reason: str,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Mark a death event and emit a single CRITICAL console line.
    Use this whenever HP hits 0 or a tag expires fatally.
    """
    payload = {"reason": reason, **(extra or {})}
    log_event(owner_kind, owner_id, "death", source="system", data=payload)

    # The ONLY console/terminal output related to tags/HP.
    logging.getLogger("death").critical(
        "DEATH: %s/%s • reason=%s • extra=%s",
        owner_kind,
        int(owner_id),
        reason,
        json.dumps(extra or {}, ensure_ascii=False),
    )
