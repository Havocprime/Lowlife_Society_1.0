# src/utils/discord_safe.py
from __future__ import annotations

# Map “smart” punctuation & box-drawing to plain ASCII
_PUNCT_MAP = str.maketrans({
    "’": "'", "‘": "'", "“": '"', "”": '"',
    "—": "-", "–": "-", "…": "...", "•": "*",
})
_BOX_MAP = str.maketrans({
    "┌":"+", "┬":"+", "┐":"+",
    "├":"+", "┼":"+", "┤":"+",
    "└":"+", "┴":"+", "┘":"+",
    "─":"-", "│":"|",
    "╔":"+", "╦":"+", "╗":"+",
    "╠":"+", "╬":"+", "╣":"+",
    "╚":"+", "╩":"+", "╝":"+",
    "═":"-", "║":"|",
})

def to_ascii_safe(s: str) -> str:
    """
    Best-effort fix for mojibake (e.g., 'Iâ€™ll') and for box-drawing glyphs.
    1) Try to reverse common UTF-8→cp1252 mis-decoding.
    2) Normalize fancy punctuation & box chars to ASCII.
    3) Strip non-printables.
    """
    if not isinstance(s, str):
        s = str(s)

    # Try to undo mojibake like 'Iâ€™m' -> 'I’m'
    try:
        s_fixed = s.encode("latin1").decode("utf-8")
        # If that didn't actually change anything, keep the original
        if s_fixed != s:
            s = s_fixed
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass

    # Normalize punctuation/box characters to ASCII
    s = s.translate(_PUNCT_MAP).translate(_BOX_MAP)

    # Final safety: keep ASCII + whitespace; replace others with '?'
    s = "".join(ch if (ch in "\t\r\n" or 0x20 <= ord(ch) <= 0x7E) else "?" for ch in s)
    return s
