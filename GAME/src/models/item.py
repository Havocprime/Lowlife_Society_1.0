from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

class ItemClass(str, Enum):
    WEAPON = "weapon"
    ARMOR = "armor"
    CONSUMABLE = "consumable"
    MISC = "misc"

@dataclass(slots=True)
class Item:
    id: int
    name: str
    item_class: ItemClass
    created_at: datetime
    bind_on_pickup: bool = False
    durability: int = 100
    pitch_value: int = 0
    rune_value: int = 0
    scrap_value: int = 0
    hidden_trait: Optional[str] = None
    mint_index: Optional[int] = None
