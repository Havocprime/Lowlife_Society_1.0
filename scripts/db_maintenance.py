# scripts/db_maintenance.py
from __future__ import annotations
import os, sqlite3, subprocess, sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

REPO = Path(__file__).resolve().parents[1]
VAR  = REPO / "GAME" / "var"
LOGDIR = VAR / "maintenance"
LOGDIR.mkdir(parents=True, exist_ok=True)
stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
LOG = LOGDIR / f"maint-{stamp}.log"

# Ensure GAME is importable
os.environ.setdefault("PYTHONPATH", str(REPO))
from GAME.src.core.settings import SETTINGS  # type: ignore


def log(line: str) -> None:
    s = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") + " " + line
    print(s)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(s + "\n")


def run_export(name: str) -> None:
    p = subprocess.run([sys.executable, str(REPO / "scripts" / name)],
                       capture_output=True, text=True)
    if p.returncode == 0:
        log(f"export {name} OK: {p.stdout.strip()}")
    else:
        log(f"export {name} FAIL: {p.stderr.strip()}")


def vacuum(db: Path) -> None:
    con = sqlite3.connect(str(db))
    try:
        con.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        con.execute("VACUUM;")
        con.execute("ANALYZE;")
        con.execute("PRAGMA optimize;")
        con.commit()
        log("VACUUM+ANALYZE done")
    finally:
        con.close()


def rotate(d: Path, days: int = 30) -> None:
    d.mkdir(parents=True, exist_ok=True)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    removed = 0
    for p in d.glob("*.csv"):
        if datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc) < cutoff:
            p.unlink(missing_ok=True)
            removed += 1
    log(f"rotate exports: removed {removed} files > {days}d")


if __name__ == "__main__":
    db = Path(SETTINGS.db_path)
    log(f"start maintenance: db={db}")
    vacuum(db)
    run_export("export_players.py")
    run_export("export_events.py")
    rotate(VAR / "exports", days=30)
    log("done")
