from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import hashlib, json, sqlite3, typing as t

DB_PATH = Path(__file__).parents[2] / "db" / "audit.sqlite"

def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

@dataclass
class EvidenceRef:
    id: int
    sha256: str

def ensure_tables() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS audit_evidence(
          id       INTEGER PRIMARY KEY AUTOINCREMENT,
          ts_utc   TEXT NOT NULL,
          kind     TEXT NOT NULL,  -- image|json|text|bin
          mime     TEXT,
          bytes    BLOB,
          sha256   TEXT NOT NULL
        );
        """)
        c.commit()

def save_bytes(*, kind: str, mime: str|None, data: bytes) -> EvidenceRef:
    ensure_tables()
    digest = _sha256(data)
    with sqlite3.connect(DB_PATH) as c:
        cur = c.execute(
            "INSERT INTO audit_evidence(ts_utc, kind, mime, bytes, sha256) VALUES (?,?,?,?,?)",
            (_iso_now(), kind, mime, data, digest)
        )
        evid = cur.lastrowid
    return EvidenceRef(id=evid, sha256=digest)

def save_json(obj: t.Any) -> EvidenceRef:
    data = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return save_bytes(kind="json", mime="application/json", data=data)

def save_text(text: str) -> EvidenceRef:
    return save_bytes(kind="text", mime="text/plain; charset=utf-8", data=text.encode("utf-8"))
