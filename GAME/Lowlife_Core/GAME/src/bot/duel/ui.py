# FILE: src/bot/duel/ui.py
from __future__ import annotations

import math
from typing import List, Optional

import discord

# State & helpers
from .state import DuelState, RangeGate
from .battlefield import compose_distance_rows  # back-compat shim is fine

# ----------------------------- constants / glyphs ------------------------------

SUN = "🌞"
CLOUD = "⛅"
RAIN = "🌧️"
NIGHT = "🌙"

GLYPH_P1 = "🔷"   # trail for player 1
GLYPH_P2 = "🔶"   # trail for player 2
GLYPH_COVER = "🧱"  # cover cell indicator
GLYPH_SEG = "·"     # empty cell dot
GLYPH_MEET = "✖"    # both in same cell

HEART = "❤️"
ARMOR = "🛡️"
BLOOD = "🩸"
GRENADE = "💣"

# Approximate range meters (min, max) for header text
RANGE_METERS = {
    RangeGate.CLOSE: (4, 10),
    RangeGate.NEAR: (10, 25),
    RangeGate.MID: (25, 40),
    RangeGate.FAR: (40, 70),
    RangeGate.OUT: (70, 120),
}

RANGE_NAME = {
    RangeGate.CLOSE: "Close",
    RangeGate.NEAR:  "Near",
    RangeGate.MID:   "Mid",
    RangeGate.FAR:   "Far",
    RangeGate.OUT:   "Out",
}

# ----------------------------- small format helpers ---------------------------

def _weather_icon(state: DuelState) -> str:
    tod = (getattr(state, "time_of_day", "day") or "day").lower()
    cond = (getattr(state, "weather", "clear") or "clear").lower()
    if "night" in tod:
        return NIGHT
    if "rain" in cond:
        return RAIN
    if "cloud" in cond:
        return CLOUD
    return SUN

def _hp_bar(cur: int, maxhp: int = 100, width: int = 22) -> str:
    cur = max(0, min(maxhp, int(cur)))
    fill = math.floor((cur / maxhp) * width)
    return "█" * fill + "░" * (width - fill)

def _blood_bar(liters: float, max_l: float = 5.0, width: int = 24) -> str:
    liters = max(0.0, min(max_l, float(liters)))
    fill = math.floor((liters / max_l) * width)
    return "█" * fill + "░" * (width - fill)

def _kit_name(kit: dict | None, primary: bool = True) -> str:
    if not isinstance(kit, dict):
        return "—"
    if primary:
        return str(kit.get("primary_name") or kit.get("primary") or kit.get("primary_weapon") or "—")
    return str(kit.get("secondary_name") or kit.get("secondary") or kit.get("secondary_weapon") or "—")

def _cover_name(n: int) -> str:
    if n <= 0:
        return "—"
    if n == 1:
        return "Partial"
    return "Full"

# ----------------------------- distance / map block ---------------------------

def _render_map_rows(state: DuelState) -> List[str]:
    """
    Compose up to 3 rows for the "visual map":
    - Lane with A/B (or ✖ if same cell)
    - Trails row (recent path marks)
    - Cover row (cells with cover)
    Uses only attributes we know to exist or are provided by back-compat shims.
    """
    base_rows = compose_distance_rows(state) or []
    segs = int(getattr(state, "vis_segments", 20) or 20)

    # Derive player indices if available
    pos = getattr(state, "pos", {}) or {}
    a = getattr(state, "a", getattr(state, "p1", None))
    b = getattr(state, "b", getattr(state, "p2", None))
    a_id = getattr(a, "user_id", None)
    b_id = getattr(b, "user_id", None)

    a_idx = 0
    b_idx = segs - 1
    if isinstance(a_id, int):
        a_idx = max(0, min(segs - 1, int(pos.get(a_id, a_idx))))
    if isinstance(b_id, int):
        b_idx = max(0, min(segs - 1, int(pos.get(b_id, b_idx))))

    # Build/patch the lane row
    if not base_rows:
        lane = [GLYPH_SEG] * segs
        if a_idx == b_idx:
            lane[a_idx] = GLYPH_MEET
        else:
            lane[a_idx] = "A"
            lane[b_idx] = "B"
        base_rows = ["".join(lane)]
    else:
        lane = list(base_rows[0])
        if a_idx == b_idx and 0 <= a_idx < len(lane):
            lane[a_idx] = GLYPH_MEET
        base_rows[0] = "".join(lane)

    # Trails
    trails = [GLYPH_SEG] * segs
    marks = getattr(state, "path_marks", set()) or set()
    for item in list(marks):
        try:
            uid, idx = item
        except Exception:
            continue
        if 0 <= idx < segs:
            trails[idx] = GLYPH_P1 if uid == a_id else GLYPH_P2
    trail_row = "".join(trails)

    # Cover
    cover = [GLYPH_SEG] * segs
    cover_cells = getattr(state, "cover_cells", set()) or set()
    for idx in list(cover_cells):
        if isinstance(idx, int) and 0 <= idx < segs:
            cover[idx] = GLYPH_COVER
    cover_row = "".join(cover)

    rows = [base_rows[0]]
    if trail_row.count(GLYPH_SEG) < segs:
        rows.append(trail_row)
    if cover_row.count(GLYPH_SEG) < segs:
        rows.append(cover_row)
    return rows

# ----------------------------- public HUD builder -----------------------------

def player_hud_embed(state: DuelState, viewer: discord.abc.User | discord.Member) -> discord.Embed:
    """
    Rebuilds the full HUD embed. Safe against missing attributes.
    """
    icon = _weather_icon(state)
    gate = getattr(state, "current_range", RangeGate.MID)
    r_lo, r_hi = RANGE_METERS.get(gate, (10, 25))
    r_name = RANGE_NAME.get(gate, "Mid")
    approx = (r_lo + r_hi) // 2

    # Fighters: tolerate either a/b or p1/p2
    a = getattr(state, "a", getattr(state, "p1", None))
    b = getattr(state, "b", getattr(state, "p2", None))
    if a is None or b is None:
        try:
            a = state.fighter(1)  # type: ignore[attr-defined]
            b = state.fighter(2)  # type: ignore[attr-defined]
        except Exception:
            pass

    # Header
    title = f"⚔️ Combat {icon}"
    turn_name = getattr(a, "display", "A") if getattr(state, "turn_of", 1) == 1 else getattr(b, "display", "B")
    desc_header = (
        f"**Range:** {r_name} **{r_lo}–{r_hi}m** (≈{approx}m)  •  "
        f"**Round:** {getattr(state, 'round_no', 1)}  •  "
        f"**Turn:** {turn_name}  •  "
        f"**Map:** {'Day' if icon in (SUN, CLOUD, RAIN) else 'Night'}"
    )
    em = discord.Embed(title=title, description=desc_header, color=discord.Color.blurple())

    # Combat kits cached earlier by the command (if provided)
    p1kit = getattr(state, "_p1kit", None)
    p2kit = getattr(state, "_p2kit", None)

    # --- Fighter blocks ---------------------------------------------------------
    a_hp = int(getattr(a, "hp", 100)); b_hp = int(getattr(b, "hp", 100))
    a_arm = getattr(a, "armor", (0, 0)); b_arm = getattr(b, "armor", (0, 0))
    if not isinstance(a_arm, tuple): a_arm = (int(getattr(a, "armor_cur", 0)), int(getattr(a, "armor_max", 0)))
    if not isinstance(b_arm, tuple): b_arm = (int(getattr(b, "armor_cur", 0)), int(getattr(b, "armor_max", 0)))

    a_wp1 = _kit_name(p1kit, True); a_wp2 = _kit_name(p1kit, False)
    b_wp1 = _kit_name(p2kit, True); b_wp2 = _kit_name(p2kit, False)

    left = (
        f"**{getattr(a, 'display', 'A')}**\n"
        f"{a_wp1} / {a_wp2}\n"
        f"{HEART} HP {a_hp}/100\n`{_hp_bar(a_hp)}`\n"
        f"{ARMOR} Armor: {a_arm[0]}/{a_arm[1]}"
    )
    right = (
        f"**{getattr(b, 'display', 'B')}**\n"
        f"{b_wp1} / {b_wp2}\n"
        f"{HEART} HP {b_hp}/100\n`{_hp_bar(b_hp)}`\n"
        f"{ARMOR} Armor: {b_arm[0]}/{b_arm[1]}"
    )
    em.add_field(name="\u200b", value=left, inline=True)
    em.add_field(name="\u200b", value=right, inline=True)
    em.add_field(name="\u200b", value="\u200b", inline=False)

    # --- Distance block ---------------------------------------------------------
    rows = _render_map_rows(state)
    if rows:
        em.add_field(
            name=f"Distance: **{r_name}** ({r_lo}–{r_hi}m, ≈{approx}m)",
            value="\n".join(f"`{r}`" for r in rows),
            inline=False,
        )

    # --- Combat Log (recent 6) --------------------------------------------------
    lines: List[str] = []
    if hasattr(state, "log") and isinstance(state.log, list):
        lines = [str(x) for x in state.log[-6:]]
    elif hasattr(state, "log_lines") and isinstance(state.log_lines, list):
        lines = [str(x) for x in state.log_lines[-6:]]
    if lines:
        em.add_field(name="Combat Log", value="• " + "\n• ".join(lines), inline=False)

    # --- Initiative -------------------------------------------------------------
    init_text = getattr(state, "initiative_text", None)
    if not init_text:
        a_i = getattr(state, "initiative_a", 50)
        b_i = getattr(state, "initiative_b", 50)
        init_text = f"a{a_i}_[b{b_i}]"
    em.add_field(name="Initiative", value=f"`{init_text}`", inline=False)

    # --- Blood / Bleed ----------------------------------------------------------
    liters = float(getattr(state, "blood_liters", 5.0))
    bleed_note = str(getattr(state, "bleed_note", "No active bleed"))
    em.add_field(
        name=f"{BLOOD} Blood — {liters:.1f} L • {bleed_note}",
        value=f"`{_blood_bar(liters)}`",
        inline=False,
    )

    # --- Grenade info (acting player for convenience) ---------------------------
    acting_is_a = (getattr(state, "turn_of", 1) == 1)
    kit = p1kit if acting_is_a else p2kit
    try:
        grenades = int(kit.get("grenades", 0)) if isinstance(kit, dict) else 0
    except Exception:
        grenades = 0
    em.add_field(name="Grenade", value=f"{GRENADE} {grenades}", inline=True)

    # Footer for viewer context (ephemeral edits etc.)
    em.set_footer(text=f"Use the buttons to act. Viewer: {getattr(viewer,'display_name',getattr(viewer,'name','?'))}")
    return em

# ----------------------------- finish helpers ----------------------------------

def finish_summary(state: DuelState) -> str:
    """Text summary for end-of-duel banner."""
    try:
        winner = state.winner()
    except Exception:
        winner = None
    if winner:
        loser = state.a if winner is state.b else state.b
        return f"{winner.name} defeats {loser.name}."
    if getattr(state, "is_draw", None) and callable(state.is_draw) and state.is_draw():
        return "It ends in a draw."
    return "Duel concluded."

async def post_public_banner(client_or_interaction, state: DuelState, content: Optional[str] = None):
    """Legacy helper: post the initial public banner."""
    try:
        channel_id = getattr(state, "channel_id", None)
        channel = None
        if hasattr(client_or_interaction, "fetch_channel") and channel_id:
            channel = await client_or_interaction.fetch_channel(channel_id)
        elif hasattr(client_or_interaction, "channel"):
            channel = client_or_interaction.channel
        if channel:
            await channel.send(content or "Duel started.")
    except Exception:
        pass

async def update_public_result(client_or_interaction, state: DuelState, text: str):
    """Post a public result note (timeout, mercy, victory, etc.)."""
    try:
        channel_id = getattr(state, "channel_id", None)
        channel = None
        if hasattr(client_or_interaction, "fetch_channel") and channel_id:
            channel = await client_or_interaction.fetch_channel(channel_id)
        elif hasattr(client_or_interaction, "channel"):
            channel = client_or_interaction.channel
        if channel:
            await channel.send(f"**Result:** {text}")
    except Exception:
        pass
