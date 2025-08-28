from __future__ import annotations
from pathlib import Path

FREEZE_FLAG = Path(__file__).resolve().parents[2] / "var" / "freeze_econ.flag"

def econ_frozen() -> bool:
    return FREEZE_FLAG.exists()
