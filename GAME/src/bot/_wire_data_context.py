
# ─────────────────────────────────────────────────────────────────────────────
# FILE: GAME/src/bot/_wire_data_context.py
# PURPOSE: Helper to initialize and attach DataContext to the bot
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

from typing import Any
from src.core.datacontext import DataContext


def init_data_context(bot: Any) -> DataContext:
    ctx = DataContext()
    # attach to bot for cogs to use (readonly attribute convention)
    setattr(bot, "data_ctx", ctx)
    return ctx

