# src/cogs/util/owners.py
from __future__ import annotations
import discord
def owner_tuple(user: discord.abc.User) -> tuple[str, str]:
    # Unified owner id for tables: ("discord", "777039317918679070")
    return ("discord", str(user.id))
