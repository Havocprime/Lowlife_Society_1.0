from __future__ import annotations

from typing import Dict, Any
from src.core import emotes as EM

def hp_bar(cur: int, maxv: int, width: int = 20) -> str:
    cur = max(0, min(cur, maxv))
    ratio = cur / maxv if maxv > 0 else 0
    filled = int(round(ratio * width))
    return "█" * filled + "░" * (width - filled) + f" ({cur}/{maxv})"



def hp_bar(cur: int, maxv: int, width: int = 20) -> str:
    cur = max(0, min(cur, maxv))
    ratio = cur / maxv if maxv > 0 else 0
    filled = int(round(ratio * width))
    return "▮" * filled + "▯" * (width - filled) + f" ({cur}/{maxv})"


# --- NEW: distance row renderer using active tileset ---
def render_distance_row(slots: int, cover_indices: list[int]) -> str:
    """Return a row of tiles for the Distance line using the active tileset."""
    cells = [EM.cover("transparent") for _ in range(slots)]
    for i in cover_indices:
        if 0 <= i < slots:
            cells[i] = EM.cover("sandbag")  # change to "barricade"/"dumpster"/"blank" if desired
    return " ".join(cells)


def build_combat_embed(
    
    tpl: Dict[str, Any], *,
    attacker: str,
    defender: str,
    range_state: str,
    round_summary: str,
    hp_a: tuple[int, int],
    hp_b: tuple[int, int],
    statuses: str
) -> Dict[str, Any]:

    # Read distance/cover config from template dict (with safe fallbacks)
    range_label: str = str(tpl.get("range_label", range_state))
    distance_slots: int = int(tpl.get("distance_slots", 12))
    cover_indices: list[int] = list(tpl.get("cover_indices", []))  # e.g., [2, 3, 7]

    distance_line = render_distance_row(distance_slots, cover_indices)

    return {
        "title": tpl["title"].format(attacker=attacker, defender=defender, range_state=range_state),
        "color": tpl["color"],
        "description": round_summary,
        "fields": [
            {"name": f"{attacker} HP", "value": hp_bar(*hp_a), "inline": True},
            {"name": f"{defender} HP", "value": hp_bar(*hp_b), "inline": True},

            # --- NEW: Distance field (uses tileset-driven tiles) ---
            {"name": f"Distance: {range_label}", "value": distance_line, "inline": False},

            {"name": "Statuses", "value": statuses, "inline": False},
        ],
    }

tpl = {
    "title": "⚔️ Combat {range_state}",
    "color": 0x2F3136,
    # Optional; these drive the distance row:
    "range_label": "Mid 11–30m (≈20m)",
    "distance_slots": 12,
    "cover_indices": [2, 3, 7],  # positions that should render as sandbags
}

# anywhere in src/core/embeds.py (near other helpers)
def render_distance_row(slots: int, cover_indices: list[int]) -> str:
    """Return a row of tiles for the Distance line using the active tileset."""
    cells = [EM.cover("transparent") for _ in range(slots)]
    for i in cover_indices:
        if 0 <= i < slots:
            cells[i] = EM.cover("sandbag")  # change to "barricade"/"dumpster"/"blank" if needed
    return " ".join(cells)
