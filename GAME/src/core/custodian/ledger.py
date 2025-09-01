from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import hashlib, json, sqlite3
from typing import Optional, Tuple

DB_PATH = Path(__file__).parents[2] / "db" / "audit.sqlite"

def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def _row_hash(payload: dict) -> str:
    core = (
        payload["ts_utc"],
        payload["actor_id"],
        payload["actor_type"],
        payload["action"],
        payload.get("target_id") or "",
        payload.get("guild_id") or "",
        payload.get("channel_id") or "",
        json.dumps(payload["context_json"], separators=(",", ":"), ensure_ascii=False),
        payload.get("evidence_sha256") or "",
    )
    return _sha256("|".join(core).encode("utf-8"))

def _last(conn: sqlite3.Connection) -> Tuple[Optional[int], Optional[str]]:
    row = conn.execute("SELECT id, chain_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    return (row[0], row[1]) if row else (None, None)

def log(
    *,
    actor_id: str,
    actor_type: str,
    action: str,
    context_json: dict,
    target_id: Optional[str] = None,
    guild_id: Optional[str] = None,
    channel_id: Optional[str] = None,
    evidence_id: Optional[int] = None,
    evidence_sha256: Optional[str] = None,
) -> int:
    payload = {
        "ts_utc": _iso_now(),
        "actor_id": str(actor_id),
        "actor_type": actor_type,
        "action": action,
        "target_id": target_id,
        "guild_id": guild_id,
        "channel_id": channel_id,
        "context_json": context_json,
        "evidence_sha256": evidence_sha256,
    }
    rh = _row_hash(payload)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        prev_id, prev_chain = _last(conn)
        ch = _sha256(((prev_chain or "") + rh).encode("utf-8"))
        cur = conn.execute(
            """INSERT INTO audit_log
               (ts_utc, actor_id, actor_type, action, target_id, guild_id, channel_id,
                context_json, evidence_id, row_hash, chain_hash, prev_chain_id, signature)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)""",
            (
                payload["ts_utc"], payload["actor_id"], payload["actor_type"], payload["action"],
                payload["target_id"], payload["guild_id"], payload["channel_id"],
                json.dumps(payload["context_json"], ensure_ascii=False),
                evidence_id, rh, ch, prev_id
            )
        )
        return cur.lastrowid

def verify_chain(limit: int = 10000) -> dict:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT id, row_hash, chain_hash FROM audit_log ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
    prev = None
    broken = []
    for rid, rh, ch in rows:
        expect = _sha256(((prev or "") + rh).encode("utf-8"))
        if expect != ch:
            broken.append(rid)
        prev = ch
    return {"checked": len(rows), "broken_ids": broken}


def verify_chain(limit: int = 10000) -> dict:
    # verify oldest → newest so the rolling 'prev' matches write-time behavior
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT id, row_hash, chain_hash FROM audit_log ORDER BY id ASC LIMIT ?",
            (limit,)
        ).fetchall()

    prev = ""  # empty prefix for the very first row
    broken = []
    for rid, rh, ch in rows:
        expect = _sha256((prev + rh).encode("utf-8"))
        if expect != ch:
            broken.append(rid)
        prev = ch  # advance the rolling chain

    return {"checked": len(rows), "broken_ids": broken}

def verify_chain_full(batch_size: int = 20000) -> dict:
    """
    Verify the entire audit chain oldest→newest in streaming batches.
    Returns: {"checked": int, "broken_ids": [ids]}
    """
    import sqlite3
    checked = 0
    broken: list[int] = []
    prev = ""          # first link uses empty prefix
    last_id = None

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        while True:
            rows = cur.execute(
                """
                SELECT id, row_hash, chain_hash
                FROM audit_log
                WHERE (? IS NULL OR id > ?)
                ORDER BY id ASC
                LIMIT ?
                """,
                (last_id, last_id, batch_size),
            ).fetchall()
            if not rows:
                break

            for rid, rh, ch in rows:
                expect = _sha256((prev + rh).encode("utf-8"))
                if expect != ch:
                    broken.append(rid)
                prev = ch
                last_id = rid
            checked += len(rows)

    return {"checked": checked, "broken_ids": broken}
