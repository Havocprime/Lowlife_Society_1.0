# GAME/src/inventory/serializers.py
from __future__ import annotations
from typing import Iterable, Mapping

# simple icons per item class
ICON = {
    "weapon": "ðŸ—¡ï¸",
    "armor": "ðŸ›¡ï¸",
    "consumable": "ðŸ§ª",
    "misc": "ðŸ“¦",
}

def as_embed_lines(rows: Iterable[Mapping]) -> list[str]:
    """
    Turn inventory rows (from manager.inventory_for_user) into short, readable lines.
    Expected keys per row: name, qty, equipped, item_class, durability, pitch_value, rune_value, scrap_value.
    """
    lines: list[str] = []
    for r in rows or []:
        name = str(r.get("name") or "Unknown")
        qty = int(r.get("qty") or 1)
        equipped = bool(r.get("equipped"))
        iclass = str(r.get("item_class") or "").lower()
        icon = ICON.get(iclass, "â€¢")

        parts = [icon, f"**{name}**"]
        if qty > 1:
            parts.append(f"x{qty}")
        if equipped:
            parts.append("(equipped)")

        dur = r.get("durability")
        if isinstance(dur, int):
            parts.append(f"dur {dur}")

        lines.append(" ".join(parts))
    return lines
