from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass(slots=True)
class User:
    id: int  # internal numeric id
    discord_id: int
    created_at: datetime
    is_frozen: bool = False
    display_name: Optional[str] = None
