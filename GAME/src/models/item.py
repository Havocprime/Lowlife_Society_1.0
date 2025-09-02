# GAME/src/models/item.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

class ItemClass(Enum):
    MISC = "misc"
    WEAPON = "weapon"
    ARMOR = "armor"
    TOOL = "tool"
    MEDICAL = "medical"

# simple rarity scale; extend anytime
RARITIES = ("common", "uncommon", "rare", "epic", "legendary", "unique")

@dataclass(slots=True)
class Item:
    id: int
    name: str
    item_class: ItemClass
    created_at: datetime

    # existing fields
    bind_on_pickup: bool = False
    durability: int = 100
    pitch_value: int = 0
    rune_value: int = 0
    scrap_value: int = 0
    hidden_trait: str = ""
    mint_index: int = 0

    # new catalog metadata
    category: str = "general"
    subcategory: str = ""
    stack_max: int = 1
    rarity: str = "common"            # one of RARITIES
    quality_float: float = 100.0      # e.g., 0.0–100.0 “condition”
