# GAME/src/tags/catalog.py
from __future__ import annotations

# Put ONLY definitions here; no DB writes/imports. Other code can import this safely.
SEED_CATALOG: dict[str, dict] = {
    # Nuisance
    "bruise.minor":         {"family": "bruise",     "max_intensity": 10},
    "scratch.minor":        {"family": "scratch",    "max_intensity": 10},

    # Cuts
    "laceration.minor":     {"family": "laceration", "max_intensity": 10},

    # Generic wound tiers
    "wound.light":          {"family": "wound",      "max_intensity": 10},
    "wound.medium":         {"family": "wound",      "max_intensity": 10},
    "wound.heavy":          {"family": "wound",      "max_intensity": 10},
    "wound.critical":       {"family": "wound",      "max_intensity": 10},

    # Bones
    "fractured_bone.arm":   {"family": "fracture",   "max_intensity": 10},
    "broken_bone.arm":      {"family": "fracture",   "max_intensity": 10},
}

def get_seed_catalog() -> dict[str, dict]:
    """Accessor so callers can override/extend later if desired."""
    return dict(SEED_CATALOG)
