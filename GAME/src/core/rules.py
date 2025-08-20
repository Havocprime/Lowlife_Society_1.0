

# =================================
# FILE: GAME/src/core/rules.py
# =================================
from __future__ import annotations
from pathlib import Path
import yaml


RULES_PATH = Path("GAME/data/rules.yml")
_CACHED: dict | None = None




def load_rules() -> dict:
global _CACHED
if _CACHED is not None:
return _CACHED
if RULES_PATH.exists():
_CACHED = yaml.safe_load(RULES_PATH.read_text(encoding="utf-8")) or {}
else:
_CACHED = {}
return _CACHED

