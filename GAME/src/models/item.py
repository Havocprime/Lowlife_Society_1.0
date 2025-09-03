# === GAME/src/models/item.py  (FULL REPLACEMENT) ===
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ItemClass(str, Enum):
    misc = "misc"
    tool = "tool"
    weapon = "weapon"
    gear = "gear"
    consumable = "consumable"
    ammo = "ammo"
    currency = "currency"
    quest = "quest"
    junk = "junk"


@dataclass
class Item:
    id: int
    name: str
    item_class: ItemClass
    created_at: datetime

    bind_on_pickup: bool = False
    durability: int = 0

    # Canonical value column
    cash_value: int = 0

    # Optional/legacy/extra
    scrap_value: int = 0
    hidden_trait: str = ""
    mint_index: int = 0

    rarity: str = "common"
    stack_max: int = 1
    quality_float: float = 100.0
    equippable: bool = True