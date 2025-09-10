# GAME/src/models/character.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

@dataclass(slots=True)
class Character:
    """
    IMPORTANT: The first block of fields MUST match the SELECT order used in dal._row_to_character()
      id, user_id, name, char_id, pronouns, background, starting_district, archetypes,
      created_at, updated_at, str, vit, end, agi, dex, wis, intel, cha, luck, hp
    The extra fields below are convenience/forward-looking and default-only (not from DB yet).
    """

    # ----- DB-mapped columns (ORDER SENSITIVE) -----
    id: int
    user_id: int
    name: str
    char_id: str
    pronouns: Optional[str]
    background: Optional[str]
    starting_district: Optional[str]
    archetypes: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]
    # base stats (note: keep key 'intel', not 'int')
    str: int
    vit: int
    end: int
    agi: int
    dex: int
    wis: int
    intel: int
    cha: int
    luck: int
    hp: int

    # ----- Extras / QoL (defaults only; not persisted yet) -----
    # identity / presentation
    discord_id: Optional[str] = None
    char_first: Optional[str] = None
    char_last: Optional[str] = None
    alias: Optional[str] = None
    avatar_url: Optional[str] = None

    # progression
    level: int = 1
    xp: int = 0
    talent_points: int = 0

    # wallet / heat
    crypto: int = 0
    cash: int = 0
    dirty_cash: int = 0
    debt: int = 0
    heat: int = 0

    # status
    is_npc: bool = False
    state: str = "ACTIVE"          # ACTIVE|DOWNED|INCAPACITATED|DEAD
    conditions: Optional[str] = "[]"

    # privacy
    privacy_level: str = "PUBLIC"  # PUBLIC|FRIENDS|PRIVATE

    # ----- Back-compat convenience properties -----
    @property
    def player_id(self) -> int:
        """Legacy alias used by older code; maps to user_id."""
        return self.user_id

    @property
    def char_name(self) -> str:
        """Legacy alias for name."""
        return self.name

    @property
    def hp_max(self) -> int:
        """Until we split hp into current/max, treat DB 'hp' as both."""
        return self.hp

    @property
    def hp_current(self) -> int:
        return self.hp
