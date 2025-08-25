# scripts/dump_tree.py
import os
from pathlib import Path

ROOT = Path(".")
OUT = ROOT / "file_tree.txt"

with OUT.open("w", encoding="utf-8") as f:
    for root, _, files in os.walk(ROOT):
        for name in files:
            p = Path(root) / name
            # Normalize & skip venv/.git/artifacts
            if any(part in {".git", ".venv", "venv", "__pycache__"} for part in p.parts):
                continue
            f.write(str(p.as_posix()) + "\n")

print(f"Wrote {OUT}")
