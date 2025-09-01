from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(slots=True)
class Character:
id: int
user_id: int
name: str
created_at: datetime
# Minimal core stats; expand later
str: int = 5
vit: int = 5
end: int = 5
agi: int = 5
dex: int = 5
wis: int = 5
intel: int = 5
cha: int = 5
luck: int = 5
hp: int = 100