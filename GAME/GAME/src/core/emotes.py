# FILE: src/core/emotes.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Union

# Type for an emoji spec:
# - str: a literal Unicode emoji like "🔷" or "🛡️"
# - int: a custom Discord emoji ID (uploaded to your server)
EmojiSpec = Union[str, int]

# ----------------------------
# Tileset definition
# ----------------------------

@dataclass
class Tileset:
    """A named palette of emoji specs by category and key."""
    name: str
    categories: Dict[str, Dict[str, EmojiSpec]] = field(default_factory=dict)
    # optional prefix for custom emoji names when rendering <:{prefix+key}:{id}>
    custom_prefix: str = "ll_"

    def get(self, category: str, key: str) -> Optional[EmojiSpec]:
        return self.categories.get(category, {}).get(key)

# ----------------------------
# Built-in Unicode fallback tileset
# ----------------------------

UNICODE_TILESET = Tileset(
    name="unicode",
    categories={
        # You’re already using 🔶 (orange diamond) and 🔷 (blue diamond)
        "players": {
            "p1": "🔶",
            "p2": "🔷",
            "p3": "🔺",
            "p4": "🔻",
        },
        "enemies": {
            "default": "✖",      # defeat marker / enemy
            "boss": "☠️",
            "npc": "◼️",
        },
        "cover": {
            "sandbag": "🧱",
            "barricade": "🚧",
            "dumpster": "🗑️",
            "blank": "🗑️",       # placeholder tile (visible)
            "transparent": ":blank_square_emoji:", # stand-in; real “blank” should be a custom transparent emoji
        },
        "hazards": {
            "fire": "🔥",
            "explosion": "💥",
            "electric": "⚡",
            "toxic": "☣️",
            "radioactive": "☢️",
        },
        "ui": {
            "cursor": "◉",
            "move": "🏃",
            "cover": "🛡️",
            "range": "🎯",
            "wait": "⏳",
        },
        "status": {
            "ok": "🟢",
            "hurt": "🟠",
            "down": "🔴",
            "hidden": "🕶️",
            "alert": "🚨",
        },
    },
)

# ----------------------------
# Example Custom tileset with placeholder IDs
# Replace these ints with YOUR uploaded emoji IDs.
# Name conventions become <:ll_{category}_{key}:{id}>
# e.g., <:ll_cover_sandbag:123456789012345678>
# ----------------------------

CUSTOM_DEFAULT = Tileset(
    name="custom_default",
    custom_prefix="ll_",
    categories={
        "players": {
            "p1": 111111111111111111,  # 🔶-style custom
            "p2": 222222222222222222,  # 🔷-style custom
            "p3": 333333333333333333,  # triangle-up (colored) custom
            "p4": 444444444444444444,  # triangle-down (colored) custom
        },
        "enemies": {
            "default": 555555555555555555,
            "boss": 666666666666666666,
            "npc": 777777777777777777,
        },
        "cover": {
            "sandbag": 888888888888888888,
            "barricade": 999999999999999999,
            "dumpster": 101010101010101010,
            "blank": 999999999999999999,        # visible blank tile (e.g., grey)
            "transparent": 999999999999999999,  # your uploaded transparent :blank: ID
        },
        "hazards": {
            "fire": 131313131313131313,
            "explosion": 141414141414141414,
            "electric": 151515151515151515,
            "toxic": 161616161616161616,
            "radioactive": 171717171717171717,
        },
        "ui": {
            "cursor": 181818181818181818,
            "move": 191919191919191919,
            "cover": 202020202020202020,
            "range": 212121212121212121,
            "wait": 222222222222222222,
        },
        "status": {
            "ok": 232323232323232323,
            "hurt": 242424242424242424,
            "down": 252525252525252525,
            "hidden": 262626262626262626,
            "alert": 272727272727272727,
        },
    },
)

# You can define more themed tilesets (greyscale grid, high-contrast, etc.)
# and swap them on the fly.
CUSTOM_GREYGRID = Tileset(
    name="custom_greygrid",
    custom_prefix="ll_",
    categories={
        "players": {
            "p1": 312312312312312310,
            "p2": 312312312312312311,
        },
        "cover": {
            "blank": 312312312312312320,        # grey tile
            "transparent": 312312312312312321,  # transparent tile
        },
    },
)

# ----------------------------
# Registry & Active tileset
# ----------------------------

_TILESETS: Dict[str, Tileset] = {
    UNICODE_TILESET.name: UNICODE_TILESET,
    CUSTOM_DEFAULT.name: CUSTOM_DEFAULT,
    CUSTOM_GREYGRID.name: CUSTOM_GREYGRID,
}

_ACTIVE_TILESET: Tileset = CUSTOM_DEFAULT  # default to custom; you can switch to "unicode"

def available_tilesets() -> list[str]:
    return list(_TILESETS.keys())

def set_active_tileset(name: str) -> None:
    global _ACTIVE_TILESET
    ts = _TILESETS.get(name)
    if not ts:
        raise ValueError(f"Tileset '{name}' not found. Available: {available_tilesets()}")
    _ACTIVE_TILESET = ts

def get_active_tileset() -> str:
    return _ACTIVE_TILESET.name

# ----------------------------
# Core getters
# ----------------------------

def _resolve_spec(category: str, key: str) -> EmojiSpec:
    """
    Get the EmojiSpec for (category, key) from the active tileset,
    falling back to Unicode tileset if missing.
    """
    spec = _ACTIVE_TILESET.get(category, key)
    if spec is not None:
        return spec
    # fallback to unicode
    fallback = UNICODE_TILESET.get(category, key)
    if fallback is not None:
        return fallback
    # final safety
    return "❓"

def emoji_string(category: str, key: str) -> str:
    """
    Return a renderable emoji string for text/embeds.
    - If spec is Unicode -> returns it directly (e.g., '🔷').
    - If spec is int (custom ID) -> returns <:ll_{category}_{key}:{id}> with the tileset's prefix.
    """
    spec = _resolve_spec(category, key)
    if isinstance(spec, str):
        return spec
    # custom ID
    prefix = _ACTIVE_TILESET.custom_prefix
    # ensure consistent naming: ll_{category}_{key}
    name = f"{prefix}{category}_{key}"
    return f"<:{name}:{spec}>"

def emoji_partial(category: str, key: str):
    """
    Return a discord.PartialEmoji for use in Buttons/Menus.
    If discord is unavailable, returns None and you can fall back to emoji_string().
    """
    try:
        import discord  # type: ignore
    except Exception:
        return None

    spec = _resolve_spec(category, key)
    if isinstance(spec, str):
        # Unicode -> PartialEmoji.from_str works
        return discord.PartialEmoji.from_str(spec)
    # Custom ID
    prefix = _ACTIVE_TILESET.custom_prefix
    name = f"{prefix}{category}_{key}"
    return discord.PartialEmoji(name=name, id=spec, animated=False)

# ----------------------------
# Convenience aliases by category
# ----------------------------

def player(slot: str = "p1") -> str:
    return emoji_string("players", slot)

def enemy(kind: str = "default") -> str:
    return emoji_string("enemies", kind)

def cover(kind: str = "sandbag") -> str:
    return emoji_string("cover", kind)

def hazard(kind: str = "fire") -> str:
    return emoji_string("hazards", kind)

def ui(icon: str = "cursor") -> str:
    return emoji_string("ui", icon)

def status(state: str = "ok") -> str:
    return emoji_string("status", state)

# ----------------------------
# Runtime mutation helpers
# ----------------------------

def register_id(category: str, key: str, emoji_id: int, tileset: str | None = None) -> None:
    """
    Register/override a custom emoji ID at runtime.
    Example: register_id("cover", "transparent", 123456789012345678)
    """
    ts = _TILESETS.get(tileset or _ACTIVE_TILESET.name)
    if not ts:
        raise ValueError(f"Tileset '{tileset}' not found.")
    ts.categories.setdefault(category, {})[key] = emoji_id

def register_unicode(category: str, key: str, emoji: str, tileset: str | None = None) -> None:
    """
    Register/override a Unicode emoji at runtime.
    """
    ts = _TILESETS.get(tileset or _ACTIVE_TILESET.name)
    if not ts:
        raise ValueError(f"Tileset '{tileset}' not found.")
    ts.categories.setdefault(category, {})[key] = emoji

# ----------------------------
# Example: quick defaults
# ----------------------------

# If you prefer to start safe (no custom IDs yet), uncomment:
# set_active_tileset("unicode")

# If you want to ensure transparent background tile works even before IDs are set,
# you can temporarily map it to a visible placeholder:
# register_unicode("cover", "transparent", "▫️", tileset="unicode")
