# scripts/export_players.py  (repo root /scripts)
from __future__ import annotations

import csv
import datetime as dt
import sqlite3
from pathlib import Path

from GAME.src.core.settings import SETTINGS  # PYTHONPATH doesn't include repo root here

OUTDIR = Path("GAME/var/exports")
OUTDIR.mkdir(parents=True, exist_ok=True)

con = sqlite3.connect(SETTINGS.db_path)
con.row_factory = sqlite3.Row
rows = con.execute(
    """SELECT id, discord_id, username, joined_at, last_seen_at, flags FROM players"""
).fetchall()
ts = dt.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
out = OUTDIR / f"players-{ts}.csv"
with out.open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["id", "discord_id", "username", "joined_at", "last_seen_at", "flags"])
    for r in rows:
        w.writerow(
            [r["id"], r["discord_id"], r["username"], r["joined_at"], r["last_seen_at"], r["flags"]]
        )
print(out)
