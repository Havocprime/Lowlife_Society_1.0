# src/models/item.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, List


# =========================
# Item Classes
# =========================
class ItemClass(str, Enum):
    misc = "misc"
    tool = "tool"
    weapon = "weapon"
    gear = "gear"
    consumable = "consumable"
    ammo = "ammo"
    currency = "currency"
    drugs = "drugs"
    # NOTE: quest/junk exist as top-level classes, but you also use them as Misc subcats.
    # Keeping them here for backward-compat, but prefer using misc->(Collectible/Quest/Junk).
    quest = "quest"
    junk = "junk"


# =========================
# Subcategory Enums
# =========================
class ConsumableSub(str, Enum):
    FOOD = "Food"
    DRINK = "Drink"
    MEDICAL = "Medical"
    OTHER = "Other"

class DrugsSub(str, Enum):
    DEPRESSANT = "Depressant"     # Alcohol/Beer/Wine/Liquor / Barbiturates / Tranqs / Xanax / GHB /Phenobarbital
    STIMULANT = "Stimulant"       # Cocaine / Crack / Amphetamines / Meth / Adderall
    HALLUCINOGEN = "Hallucinogen" # LSD / Peyote / Psilocybin / MDMA
    DISSOCIATIVE = "Dissociative" # PCP / DXM /
    NARCOTIC = "Narcotic"         # Opioid/Fentanyl/Oxy / Codeine / Heroin / Demerol / Morphine / Methadone / Vicodin / Oxycontin
    INHALANT = "Inhalant"         # Plastic Cement / Paint / Gasoline / Paint Thinner / Hair Spray / Whippits / Nail Polish

class AmmoSub(str, Enum):
    PISTOL = "Pistol"
    RIFLE = "Rifle"
    SHOTGUN = "Shotgun"
    OTHER = "Other"


class WeaponSub(str, Enum):
    MELEE = "Melee"
    PISTOL = "Pistol"
    REVOLVER = "Revolver"
    SMG = "SMG"
    SHOTGUN = "Shotgun"
    RIFLE = "Rifle"
    SNIPER = "Sniper"
    THROWN = "Thrown"
    TOOL = "Tool"        # e.g., crowbar-as-weapon (legacy/compat)


class GearSub(str, Enum):
    CLOTHING = "Clothing"
    ARMOR = "Armor"      # generic; keep for BC
    VEST = "Vest"
    CHESTRIG = "ChestRig"
    HELMET = "Helmet"
    FACE = "Face"
    BACKPACK = "Backpack"
    UTILITY = "Utility"  # belts, pouches, etc.


# =========================
# Allowed Subcategories Registry (canonical labels)
# Validation is case-insensitive and normalizes to these labels.
# =========================
ALLOWED_SUBCATEGORIES: Dict[ItemClass, List[str]] = {
    ItemClass.currency: ["USD", "$", "Cash", "Bitcoin", "BTC", "Crypto"],
    ItemClass.misc: ["Collectible", "Quest", "Junk"],
    ItemClass.tool: ["Lockpick", "Repair", "Utility", "Improvised"],
    # Expanded weapon taxonomy (granular)
    ItemClass.weapon: [s.value for s in WeaponSub],
    # Gear split kept compatible with your prior "Clothing/Armor/Utility"
    # while also supporting finer options used elsewhere in the project.
    ItemClass.gear: [s.value for s in GearSub],
    ItemClass.consumable: [s.value for s in ConsumableSub],
    ItemClass.ammo: [s.value for s in AmmoSub],
    # You can optionally add ItemClass.quest/junk mappings if you later decide
    # to have subcategories under those top-level classes.
    ItemClass.drugs: [s.value for s in DrugsSub],
}


def allowed_subcategories_for(item_class: ItemClass) -> List[str]:
    """Return the allowed (canonical) subcategories for a given ItemClass."""
    return ALLOWED_SUBCATEGORIES.get(item_class, [])


# -------------------------
# Synonym maps (case-insensitive keys)
# -------------------------
_CURRENCY_RELAX = {
    "usd": "USD",
    "$": "$",
    "cash": "Cash",
    "btc": "BTC",
    "bitcoin": "Bitcoin",
    "crypto": "Crypto",
}

_CONSUMABLE_RELAX = {
    "med": "Medical",
    "meds": "Medical",
    "heal": "Medical",
    "beverage": "Drink",
    "drinks": "Drink",
    "foodstuff": "Food",
}

_AMMO_RELAX = {
    "handgun": "Pistol",
    "hg": "Pistol",
    "pistol": "Pistol",
    "rifles": "Rifle",
    "shotty": "Shotgun",
    "shotshell": "Shotgun",
}

_WEAPON_RELAX = {
    "gun": "Rifle",          # generic -> Rifle (heuristic)
    "firearm": "Rifle",      # generic -> Rifle
    "ar": "Rifle",
    "carbine": "Rifle",
    "dmr": "Rifle",
    "sniper": "Sniper",
    "marksman": "Sniper",
    "smg": "SMG",
    "submachine": "SMG",
    "shotty": "Shotgun",
    "shotgun": "Shotgun",
    "sidearm": "Pistol",
    "handgun": "Pistol",
    "knife": "Melee",
    "bat": "Melee",
    "crowbar": "Tool",       # legacy/compat
    "throwable": "Thrown",
    "grenade": "Thrown",
}

_GEAR_RELAX = {
    "mask": "Face",
    "gasmask": "Face",
    "rig": "ChestRig",
    "chest rig": "ChestRig",
    "pack": "Backpack",
    "bag": "Backpack",
    "armor": "Armor",        # generic armor catch
    "vest": "Vest",
    "helmet": "Helmet",
    "utility": "Utility",
    "clothes": "Clothing",
}


def _canonicalize_subcategory(item_class: ItemClass, subcat: Optional[str]) -> Optional[str]:
    """
    Case-insensitive canonicalization; returns canonical label if valid.
    If the class has no registered subcats, return value unchanged.
    Raises ValueError when invalid for the class.
    """
    if subcat is None:
        return None

    canon_list = allowed_subcategories_for(item_class)
    if not canon_list:
        # No restrictions for this class; pass through
        return subcat

    # Primary case-insensitive match
    lookup = {c.lower(): c for c in canon_list}
    key = str(subcat).strip().lower()
    if key in lookup:
        return lookup[key]

    # Relaxed synonyms per class
    relax: Dict[str, str] = {}
    if item_class == ItemClass.currency:
        relax = _CURRENCY_RELAX
    elif item_class == ItemClass.consumable:
        relax = _CONSUMABLE_RELAX
    elif item_class == ItemClass.ammo:
        relax = _AMMO_RELAX
    elif item_class == ItemClass.weapon:
        relax = _WEAPON_RELAX
    elif item_class == ItemClass.gear:
        relax = _GEAR_RELAX

    if key in relax and relax[key].lower() in lookup:
        return lookup[relax[key].lower()]

    # Nothing matched
    raise ValueError(
        f"Invalid subcategory '{subcat}' for class '{item_class.value}'. "
        f"Allowed: {', '.join(canon_list)}"
    )


# =========================
# Item Dataclass
# =========================
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

    # fine-grained subcategory (e.g. weapon->Melee/Pistol/etc., currency->USD/Bitcoin)
    subcategory: Optional[str] = None

    def __post_init__(self) -> None:
        # Normalize/validate subcategory when provided (fail-fast keeps data clean)
        self.subcategory = _canonicalize_subcategory(self.item_class, self.subcategory)

    # -------- Optional helpers (non-breaking) --------
    @property
    def computed_cash_value(self) -> int:
        """
        Helper for callers that want a value even if 'cash_value' wasn't present historically.
        Mirrors your manager comment: falls back to scrap_value if cash_value is zero.
        """
        return self.cash_value or self.scrap_value

    def as_dict(self) -> Dict[str, object]:
        """Lightweight serializer for embeds/exports."""
        return {
            "id": self.id,
            "name": self.name,
            "item_class": self.item_class.value,
            "subcategory": self.subcategory,
            "rarity": self.rarity,
            "stack_max": self.stack_max,
            "equippable": self.equippable,
            "durability": self.durability,
            "quality_float": self.quality_float,
            "cash_value": self.cash_value,
            "scrap_value": self.scrap_value,
            "bind_on_pickup": self.bind_on_pickup,
            "mint_index": self.mint_index,
            "hidden_trait": self.hidden_trait,
            "created_at": self.created_at.isoformat(),
        }
