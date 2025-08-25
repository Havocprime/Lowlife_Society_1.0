
# ─────────────────────────────────────────────────────────────────────────────
# FILE: GAME/src/core/datacontext.py
# PURPOSE: Single import to construct context + domain facades
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

from src.data.repo._base import DataContext as _InnerContext
from src.data.repo.user_repo import UserRepo
from src.data.repo.character_repo import CharacterRepo
from src.data.repo.inventory_repo import InventoryRepo


class DataContext:
    def __init__(self):
        self._ctx = _InnerContext()
        self.users = UserRepo(self._ctx)
        self.characters = CharacterRepo(self._ctx)
        self.inventories = InventoryRepo(self._ctx)

