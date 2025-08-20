from __future__ import annotations
import os, json, yaml
from pathlib import Path
from typing import Any, Dict

DATA_DIR = Path(os.getenv("LOWLIFE_DATA_DIR", "."))

def load_rules() -> Dict[str, Any]:
    with open(DATA_DIR / "combat_rules_v1.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def load_templates() -> Dict[str, Any]:
    with open(DATA_DIR / "embed_templates_v1.json", "r", encoding="utf-8") as f:
        return json.load(f)
