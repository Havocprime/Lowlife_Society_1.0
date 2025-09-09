# GAME/scripts/seed_tags.py
from __future__ import annotations

# Make "src" importable whether run as a module (-m GAME.scripts.seed_tags)
# or as a file (python GAME/scripts/seed_tags.py).
import sys
from pathlib import Path

GAME_DIR = Path(__file__).resolve().parents[1]  # .../GAME
if str(GAME_DIR) not in sys.path:
    sys.path.insert(0, str(GAME_DIR))

from src.systems.tags.schema import ensure_tags_schema
from src.systems.tags.dal import upsert_tag


def main():
    # Ensure schema (idempotent)
    ensure_tags_schema()

    # ---- Catalog seeds ----
    upsert_tag(
        name="Bleeding",
        kind="dynamic",
        group="injury",
        polarity="-",
        max_stacks=3,
        tick_ms=1500,
        exclusivity="bleed_family",
        script_key="bleeding",
        state_machine={
            "initial": "active",
            "states": {"active": {}, "stopped": {"terminal": True}},
            "transitions": []
        }
    )

    upsert_tag(
        name="Gunshot Wound",
        kind="dynamic",
        group="injury",
        polarity="-",
        max_stacks=1,
        tick_ms=2000,
        exclusivity="wound_gunshot",
        script_key="wound_gunshot",
        state_machine={
            "initial": "fresh",
            "states": {"fresh": {}, "stabilized": {}, "scar": {"terminal": True}},
            "transitions": []
        }
    )

    print("Seeded: Bleeding, Gunshot Wound")


if __name__ == "__main__":
    main()
