# src/cogs/tags_catalog.py  (or src/tags/catalog.py)
from __future__ import annotations

def get_seed_catalog() -> dict[str, dict]:
    # Canonical keys used by HP-drain / wounds; tweak as you like.
    return {
        # status
        "status.bleeding": {"family": "status", "max_intensity": 10},

        # wound families (generic severities)
        "wound.light":    {"family": "wound", "max_intensity": 10},
        "wound.medium":   {"family": "wound", "max_intensity": 10},
        "wound.heavy":    {"family": "wound", "max_intensity": 10},
        "wound.critical": {"family": "wound", "max_intensity": 10},

        # concrete wound types (capped at 3 by design)
        "wound.gunshot":  {"family": "wound", "max_intensity": 3},
        "wound.bruise":   {"family": "wound", "max_intensity": 3},
        "wound.scratch":  {"family": "wound", "max_intensity": 3},

        # extra “minor” keys used by your UI/sim
        "bruise.minor":         {"family": "bruise",    "max_intensity": 10},
        "scratch.minor":        {"family": "scratch",   "max_intensity": 10},
        "laceration.minor":     {"family": "laceration","max_intensity": 10},

        # fracture examples from your screenshot
        "broken_bone.arm":      {"family": "fracture",  "max_intensity": 10},
        "fractured_bone.arm":   {"family": "fracture",  "max_intensity": 10},
    }
