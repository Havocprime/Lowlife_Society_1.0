from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, List
from enum import Enum


class ItemClass(str, Enum):
    misc = "misc"
    tool = "tool"
    weapon = "weapon"
    gear = "gear"
    consumable = "consumable"
    ammo = "ammo"
    currency = "currency"
    # NOTE: quest/junk exist as top-level classes, but you also use them as Misc subcats.
    # Keeping them here for backward-compat, but prefer using misc->(Collectible/Quest/Junk).
    quest = "quest"
    junk = "junk"


# ----------------------------
# Subcategory Enums (new ones for Consumable / Ammo)
# ----------------------------

class ConsumableSub(str, Enum):
    FOOD = "Food"
    DRINK = "Drink"
    MEDICAL = "Medical"
    OTHER = "Other"


class AmmoSub(str, Enum):
    PISTOL = "Pistol"
    RIFLE = "Rifle"
    SHOTGUN = "Shotgun"
    OTHER = "Other"


# ----------------------------
# Central registry of allowed subcategories per ItemClass
# NOTE: labels here are the canonical display strings.
# Validation is case-insensitive and normalizes to these labels.
# ----------------------------
ALLOWED_SUBCATEGORIES: Dict[ItemClass, List[str]] = {
    ItemClass.currency: ["USD", "$", "Cash", "Bitcoin", "BTC", "Crypto"],
    ItemClass.misc: ["Collectible", "Quest", "Junk"],
    ItemClass.tool: ["Lockpick", "Repair", "Utility", "Improvised"],
    ItemClass.weapon: ["Melee", "Firearm", "Thrown", "Tool"],
    ItemClass.gear: ["Clothing", "Armor", "Utility"],
    # NEW:
    ItemClass.consumable: [s.value for s in ConsumableSub],  # ["Food", "Drink", "Medical", "Other"]
    ItemClass.ammo: [s.value for s in AmmoSub],              # ["Pistol", "Rifle", "Shotgun", "Other"]
    # You can optionally add ItemClass.quest/junk mappings if you later decide to
    # have subcategories under those top-level classes.
}


def allowed_subcategories_for(item_class: ItemClass) -> List[str]:
    """Return the allowed (canonical) subcategories for a given ItemClass."""
    return ALLOWED_SUBCATEGORIES.get(item_class, [])


def _canonicalize_subcategory(item_class: ItemClass, subcat: Optional[str]) -> Optional[str]:
    """Case-insensitive check; returns canonical label if valid, else raises ValueError."""
    if subcat is None:
        return None
    canon_list = allowed_subcategories_for(item_class)
    if not canon_list:
        return subcat  # no restrictions for this class
    # Case-insensitive match to canonical
    lookup = {c.lower(): c for c in canon_list}
    key = str(subcat).strip().lower()
    if key in lookup:
        return lookup[key]
    # Also allow relaxed synonyms for some common cases (optional)
    relax = {
        "usd": "USD",
        "cash": "Cash",
        "btc": "BTC",
        "bitcoin": "Bitcoin",
        "crypto": "Crypto",
        "$": "$",
    }
    if key in relax and relax[key] in canon_list:
        return relax[key]
    raise ValueError(f"Invalid subcategory '{subcat}' for class '{item_class.value}'. "
                     f"Allowed: {', '.join(canon_list)}")


@dataclass
class Item:
    id: int
    name: str
    item_class: ItemClass
    created_at: datetime

    bind_on_pickup: bool = False
    durability: int = 0

    # Canonical cash value; manager falls back to scrap_value if DB lacks this column
    cash_value: int = 0

    # Legacy/extra
    scrap_value: int = 0
    hidden_trait: str = ""
    mint_index: int = 0

    rarity: str = "common"
    stack_max: int = 1
    quality_float: float = 100.0
    equippable: bool = True

    # fine-grained subcategory (e.g. weapon->melee/firearm, currency->usd/bitcoin)
    subcategory: Optional[str] = None

    def __post_init__(self) -> None:
        # Normalize/validate subcategory when provided.
        try:
            self.subcategory = _canonicalize_subcategory(self.item_class, self.subcategory)
        except ValueError as e:
            # If you prefer soft-fail, swap to a log warning and keep original value.
            # For now we fail fast to keep data clean:
            raise
