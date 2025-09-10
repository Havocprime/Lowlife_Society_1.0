# scripts/export_events.py
from __future__ import annotations

import csv
import datetime as dt
import sqlite3
from pathlib import Path

from GAME.src.core.settings import SETTINGS

OUTDIR = Path("GAME/var/exports")
OUTDIR.mkdir(parents=True, exist_ok=True)

con = sqlite3.connect(SETTINGS.db_path)
con.row_factory = sqlite3.Row
rows = con.execute(
    """SELECT id,type,actor_discord_id,subject,payload_json,created_at FROM events ORDER BY id"""
).fetchall()
ts = dt.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
out = OUTDIR / f"events-{ts}.csv"
with out.open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["id", "type", "actor_discord_id", "subject", "payload_json", "created_at"])
    for r in rows:
        w.writerow(
            [
                r["id"],
                r["type"],
                r["actor_discord_id"],
                r["subject"],
                r["payload_json"],
                r["created_at"],
            ]
        )
print(out)
