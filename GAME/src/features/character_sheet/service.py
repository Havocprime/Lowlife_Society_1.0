from __future__ import annotations

from typing import Optional

from src.db import dal


def upsert_player_from_discord(discord_id: int, username: str) -> int:
    return dal.upsert_player(str(discord_id), username)


def ensure_character(player_id: int, codename: str, faction: str | None = None) -> int:
    # choose first existing or create new
    chars = dal.get_characters(player_id)
    if chars:
        return chars[0]["id"]
    return dal.create_character(player_id, codename, faction)


def get_profile_rows(player_id: int):
    chars = dal.get_characters(player_id)
    if not chars:
        return None, None
    cid = chars[0]["id"]
    # profiles has defaults; join lightweight bits
    return cid, None  # placeholder for future profile details
