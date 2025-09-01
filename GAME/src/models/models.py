from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum
from datetime import datetime
from typing import Optional


class AuditKind(StrEnum):
INFO = "INFO"
WARNING = "WARNING"
ERROR = "ERROR"
ECON_TX = "ECON_TX"
ITEM_MUT = "ITEM_MUT"
DUEL_EVT = "DUEL_EVT"


@dataclass(slots=True)
class AuditEvent:
id: int
ts: datetime
kind: AuditKind
actor_discord_id: int
target_discord_id: Optional[int]
ctx: str # freeform JSON string