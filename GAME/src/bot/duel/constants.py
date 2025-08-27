"""
All visual constants and simple knobs live here so UX tweaks are centralized.
"""

# --- UI / log sizing ---
LOG_VISIBLE = 6  # how many combat log rows to show in the embed

# --- Fighter glyphs (big + small markers) ---
GLYPH_A = "🔶"
GLYPH_B = "🔷"
GLYPH_A_SMALL = "🔶"  # visually smaller variant; can be same emoji if preferred
GLYPH_B_SMALL = "🔷"
GLYPH_GRAPPLE = "🤼"  # special glyph shown when grappling

# --- Lane background tiles ---
# Bottom-lane background tile (day/night); we kept these neutral for dark Discord themes.
BG_NIGHT = "⠀"  # blank braille space (renders as very subtle dotless gap)
BG_DAY = "⠀"
TOP_BG = " "  # not rendered to Discord as a separate field; string-composed only

# --- Trail tokens (used to mark every tile traversed) ---
# A/B trails can be distinct so you can tell whose path is whose at a glance.
TRAIL_A = "───"  # width-matched nicely against cover/emotes
TRAIL_B = "▪️"

# --- Cover markers (only three types by design) ---
COVER_DOOR = "🚪"
COVER_BARRICADE = "🚧"
COVER_BARREL = "🛢️"
COVER_SET = {COVER_DOOR, COVER_BARRICADE, COVER_BARREL}

# --- Gameplay knobs ---
# % accuracy reduction when defending from a tile that *has* cover
COVER_PCT_DEFAULT = 40
