from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

@dataclass
class Player:
    id: int
    discord_id: str
    username: Optional[str] = None
    display_name: Optional[str] = None
    alias: Optional[str] = None
    onboarding_state: str = "NEW"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
