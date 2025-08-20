# FILE: src/bot/duel.py
from __future__ import annotations

import asyncio
import logging
import random
from typing import Optional, Tuple, Dict, List

import discord
from discord import app_commands

from src.core.duel_core import (
    DuelState, Combatant,
    range_label, rg_to_loadout_range,
    compute_attack_numbers, load_player_stats,
    profile_score, odds_phrase,
    equipped_ids, item_name,
    armor_kind_from_wclass, apply_armor_reduction,
    record_hit, iclamp, clamp,
)

# Best-effort inventory hooks (optional)
try:
    from src.core.inventory import add_item_to_inventory  # type: ignore
except Exception:  # pragma: no cover
    add_item_to_inventory = None  # type: ignore

log = logging.getLogger("duel")

# --------- UI constants ---------
LOG_VISIBLE = 6
# visual lane settings
GLYPH_A = "🔶"
GLYPH_B = "🔷"
GLYPH_A_SMALL = "🔶"
GLYPH_B_SMALL = "🔷"
GLYPH_GRAPPLE = "🤼"

BG_NIGHT = "⠀"  # bottom lane background, night
BG_DAY = "⠀"      # bottom lane background, day
TOP_BG = " "      # purely visual spacer for the top row (we compose strings anyway)

TRAIL_A = "───"   # trail token width-matched to "..."
TRAIL_B = "▪️"

COVER_DOOR = "🚪"
COVER_BARRICADE = "🚧"
COVER_BARREL = "🛢️"
COVER_SET = {COVER_DOOR, COVER_BARRICADE, COVER_BARREL}

# cover mechanics
COVER_PCT_DEFAULT = 40  # percent to reduce incoming accuracy if a target is "in cover"

# ---------- safe reply ----------
async def _safe_reply(
    inter: discord.Interaction,
    *,
    content: Optional[str] = None,
    embed: Optional[discord.Embed] = None,
    view: Optional[discord.ui.View] = None,
    ephemeral: bool = False,
) -> None:
    try:
        base_kwargs = {"content": content, "embed": embed, "ephemeral": ephemeral}
        if view is not None:
            base_kwargs["view"] = view
        if not inter.response.is_done():
            try:
                await inter.response.send_message(**base_kwargs)
                return
            except discord.HTTPException as e:
                if e.code != 40060:  # "Unknown interaction"
                    raise
        await inter.followup.send(**base_kwargs)
    except Exception:
        log.exception("safe_reply failed")

# ---------- battlefield / map helpers ----------

def _init_battlefield(state: DuelState) -> None:
    """Create a simple day/night map and a line of cover tokens aligned to visible segments."""
    # Day or Night
    state.map_time = random.choice(["Day", "Night"])
    segs = state.vis_segments

    # Cover layout: sparse, but enough to matter
    cover = [None] * segs  # type: List[Optional[str]]

    # Randomly sprinkle 5–8 cover items with spacing
    num = random.randint(5, 8)
    placed: set[int] = set()
    for _ in range(num):
        pos = random.randint(0, segs - 1)
        # keep some spacing so it doesn't clump too tightly
        if any(abs(pos - p) <= 1 for p in placed):
            continue
        token = random.choice([COVER_BARRICADE, COVER_BARRICADE, COVER_BARREL, COVER_DOOR])
        cover[pos] = token
        placed.add(pos)

    state.cover_line = cover  # list[Optional[str]]

    # trails: sets of tile indices visited
    state.trails = {
        state.a.user_id: set(),
        state.b.user_id: set(),
    }

    # Ensure cover flags start correct
    _update_cover_flags(state)

def _bg_token(state: DuelState) -> str:
    return BG_DAY if getattr(state, "map_time", "Night") == "Day" else BG_NIGHT

def _trail_for(uid: int) -> str:
    return TRAIL_A if uid % 2 else TRAIL_B

def _mark_trail(state: DuelState, uid: int) -> None:
    segs = state.vis_segments
    idx = iclamp(state.pos.get(uid, 0), 0, segs - 1)
    state.trails.setdefault(uid, set()).add(idx)

def _update_cover_flags(state: DuelState) -> None:
    """Refresh who is counted as in cover based on current positions."""
    for c in (state.a, state.b):
        segs = state.vis_segments
        idx = iclamp(state.pos.get(c.user_id, 0), 0, segs - 1)
        tok = (getattr(state, "cover_line", None) or [None]*segs)[idx]
        if tok in COVER_SET:
            state.in_cover.add(c.user_id)
            state.cover_pct[c.user_id] = COVER_PCT_DEFAULT
        else:
            state.in_cover.discard(c.user_id)
            state.cover_pct.pop(c.user_id, None)

def _compose_distance_rows(state: DuelState) -> Tuple[str, str]:
    """
    Build the two visual rows:
    - top row: backgrounds only; if a fighter is 'in cover', show SMALL icon here above the cover
    - bottom row: backgrounds/cover/trails and (if not hidden by cover) the main icons
    """
    segs = state.vis_segments
    bg = _bg_token(state)
    cover = (getattr(state, "cover_line", None) or [None]*segs)

    # start rows
    top_row: List[str] = [bg if bg != "..." else "..." for _ in range(segs)]
    bot_row: List[str] = [bg for _ in range(segs)]

    # lay down cover on bottom row
    for i, tok in enumerate(cover):
        if tok:
            bot_row[i] = tok

    # lay down trails where background (don't overwrite cover)
    for uid, visited in getattr(state, "trails", {}).items():
        trail_token = _trail_for(uid)
        for i in visited:
            if 0 <= i < segs and bot_row[i] not in COVER_SET:
                bot_row[i] = trail_token

    # figure fighter positions
    a_id, b_id = state.a.user_id, state.b.user_id
    ia = iclamp(state.pos.get(a_id, 1), 0, segs-1)
    ib = iclamp(state.pos.get(b_id, segs-2), 0, segs-1)
    if ia == ib:  # keep from stacking glyphs
        ib = iclamp(ib + 1, 0, segs-1)

    # if grappling, show the special icon in the center-ish and skip per-tile icons
    if state.grappling:
        center_left = max(0, (segs // 2) - 1)
        bot_row[center_left] = GLYPH_GRAPPLE
        return ("".join(top_row), "".join(bot_row))

    # place fighter icons; if tile is cover, hide on bottom and place small on top
    def _place(uid: int, idx: int, big: str, small: str):
        if bot_row[idx] in COVER_SET:
            top_row[idx] = small  # small marker above cover
        else:
            bot_row[idx] = big

    _place(a_id, ia, GLYPH_A, GLYPH_A_SMALL)
    _place(b_id, ib, GLYPH_B, GLYPH_B_SMALL)

    return ("".join(top_row), "".join(bot_row))

# ---------- view helpers ----------
def _make_view(state: DuelState, client: discord.Client, viewer_id: int) -> discord.ui.View:
    """Choose the correct button set for the current state from the POV of viewer_id."""
    if not state.active:
        return DuelLogView(state)

    # Finisher lock (keeps buttons visible until resolved)
    finisher = getattr(state, "finisher", None)
    if finisher:
        victor_id, target_id = finisher
        if viewer_id == victor_id:
            return FinalizeView(state, client, victor_id=victor_id, target_id=target_id)
        return DuelLogView(state)

    # If choking: only the choker (and only on their turn) gets choke buttons
    if state.choking:
        choker_id, _ = state.choking
        if state.current().user_id == choker_id and viewer_id == choker_id:
            return ChokeView(state, client)
        return DuelLogView(state)

    # If grappling (and not choking): current actor gets grapple actions
    if state.grappling:
        if viewer_id == state.current().user_id:
            return GrappleView(state, client)
        return DuelLogView(state)

    # Default ranged set
    return DuelMainView(state, client)

async def _hud_update_auto(
    interaction: discord.Interaction,
    state: DuelState,
    viewer: discord.User,
) -> None:
    """Always rebuild the correct view to avoid stale buttons after state changes."""
    view = _make_view(state, interaction.client, viewer.id) if state.active else DuelLogView(state)
    await _hud_update_with_view(interaction, state, viewer, view)

async def _hud_update_with_view(
    interaction: discord.Interaction,
    state: DuelState,
    viewer: discord.User,
    view: discord.ui.View,
) -> None:
    """Update HUD with a specific view (e.g., force finisher)."""
    try:
        if not interaction.response.is_done():
            await interaction.response.edit_message(embed=player_hud_embed(state, viewer), view=view)
            return
    except Exception:
        pass
    try:
        await interaction.edit_original_response(embed=player_hud_embed(state, viewer), view=view)
        return
    except Exception:
        pass
    try:
        await interaction.followup.send(embed=player_hud_embed(state, viewer), view=view, ephemeral=True)
    except Exception:
        log.exception("HUD update failed")

# ========= Bars / glyphs =========
def hp_bar(hp: int, segments: int = 13, filled_char: str = "🟩") -> str:
    filled = iclamp(round((hp / 100) * segments), 0, segments)
    return filled_char * filled + "⬛" * (segments - filled)

def armor_bar(armor: float, segments: int = 13) -> str:
    _ARMOR_DISPLAY_MAX = 20.0
    pct = clamp(armor / _ARMOR_DISPLAY_MAX, 0.0, 1.0)
    filled = iclamp(round(pct * segments), 0, segments)
    return "🟦" * filled + "⬛" * (segments - filled)

def meter_bar(val: int, segments: int = 13, full: str = "🟦") -> str:
    v = iclamp(val, 0, 100)
    filled = iclamp(round((v / 100) * segments), 0, segments)
    return full * filled + "⬛" * (segments - filled)

def _blood_bar_and_label(blood_lost_l: float):
    total = 5.0
    remain = clamp(total - blood_lost_l, 0.0, total)
    ticks = 20
    filled = int(round((remain / total) * ticks))
    bar = "🟥" * filled + "⬛" * (ticks - filled)
    lost = total - remain
    if lost < 0.2: wound = "No active bleed"
    elif lost < 0.5: wound = "Light bleed"
    elif lost < 1.0: wound = "Minor puncture"
    elif lost < 2.0: wound = "Major bleed"
    else: wound = "Severed artery"
    return bar, f"{remain:.1f} L • {wound}"

def _pos_word(v: int) -> str:
    if v <= 25: return "Awful"
    if v <= 40: return "Poor"
    if v <= 60: return "Even"
    if v <= 80: return "Good"
    return "Dominant"

# ---------- seed log & initiative ----------
def _seed_combat_log(state: DuelState, rows: int = LOG_VISIBLE - 1, fill_char: str = "◐") -> None:
    if not state.log_lines:
        state.log_lines.extend([fill_char] * rows)
        state.full_log_lines.extend([fill_char] * rows)

def _decide_initiative(state: DuelState) -> None:
    a, b = state.players()
    sa, sb = load_player_stats(a.user_id), load_player_stats(b.user_id)
    p_a = clamp(0.5 + 0.02 * (sa["combat"] - sb["combat"]) + 0.01 * (sa["fitness"] - sb["fitness"]), 0.10, 0.90)
    roll = random.random()
    first = a if roll <= p_a else b
    state.turn_id = 0 if first is a else 1
    pa = round(p_a * 100); pb = 100 - pa
    state.initiative_note = f"a{pa}_[b{pb}]"
    state.log_lines.append(f"Initiative: {a.name} {pa}% vs {b.name} {pb}% → **{first.name}** starts.")
    state.full_log_lines.append(state.log_lines[-1])

# ---------- HUD / embeds ----------
def _distance_block(state: DuelState) -> Tuple[str, str]:
    """Returns (title_line, composed_visual_lines) where visual_lines already include two rows."""
    title = f"Distance: **{range_label(state.rngate())}**"
    top, bot = _compose_distance_rows(state)
    return title, f"{top}\n{bot}"

def player_hud_embed(state: DuelState, viewer: discord.User) -> discord.Embed:
    a, b = state.players()
    header = f"Range: **{range_label(state.rngate())}** • Round: **{state.round_no}**"
    header += f" • Turn: **{state.current().name if state.active else '—'}** • Map: **{getattr(state, 'map_time', 'Night')}**"

    e = discord.Embed(
        title=f"⚔️ Combat {'🌞' if getattr(state,'map_time','Night')=='Day' else '🌙'}",
        description=header,
        color=(discord.Color.orange() if (state.grappling or state.choking) else (discord.Color.blurple() if state.active else discord.Color.dark_grey())),
    )

    def _disp_primary(uid: int) -> str:
        eq = equipped_ids(uid); iid = eq.get("primary")
        dis = "primary" in state.disarmed.get(uid, set())
        name = item_name(iid) or "—"
        if name == "—": name = "Fists"
        return f"{name} (disarmed)" if dis else name

    def _disp_secondary(uid: int) -> str:
        eq = equipped_ids(uid); iid = eq.get("secondary")
        dis = "secondary" in state.disarmed.get(uid, set())
        name = item_name(iid)
        if (uid == viewer.id) or (uid in state.revealed_secondary):
            return f"{name} (disarmed)" if dis else name
        return "???" if iid else "—"

    def _armor_val(uid: int) -> float:
        return float(load_player_stats(uid).get("armor", 0.0))

    a_primary = _disp_primary(a.user_id); a_secondary = _disp_secondary(a.user_id)
    b_primary = _disp_primary(b.user_id); b_secondary = _disp_secondary(b.user_id)

    # White HP if unconscious
    a_color = "⬜" if (a.user_id in state.unconscious) else "🟩"
    b_color = "⬜" if (b.user_id in state.unconscious) else "🟩"

    e.add_field(
        name=f"**{a.name}**",
        value=f"{a_primary} / {a_secondary}\nHP {a.hp}/100\n{hp_bar(a.hp, filled_char=a_color)}\nArmor:\n{armor_bar(_armor_val(a.user_id))}" +
              (f"\nPositioning: {_pos_word(state.positioning.get(a.user_id, 50))}" if state.grappling else ""),
        inline=True,
    )
    e.add_field(
        name=f"**{b.name}**",
        value=f"{b_primary} / {b_secondary}\nHP {b.hp}/100\n{hp_bar(b.hp, filled_char=b_color)}\nArmor:\n{armor_bar(_armor_val(b.user_id))}" +
              (f"\nPositioning: {_pos_word(state.positioning.get(b.user_id, 50))}" if state.grappling else ""),
        inline=True,
    )

    dist_title, dist_rows = _distance_block(state)
    e.add_field(name=dist_title, value=dist_rows, inline=False)

    if state.log_lines:
        e.add_field(
            name="Combat Log",
            value="\n".join(f"• {ln}" for ln in state.log_lines[-LOG_VISIBLE:]),
            inline=False
        )

    if state.initiative_note:
        e.add_field(name="Initiative", value=state.initiative_note, inline=False)

    s = load_player_stats(viewer.id)
    bar, lbl = _blood_bar_and_label(float(s.get("blood", 0.0)))
    e.add_field(name=f"Blood — {lbl}", value=f"{bar}", inline=False)

    # Only the choke target sees their Breath/Bloodflow
    if state.choking:
        choker, target = state.choking
        if viewer.id == target:
            breath = state.breath.get(target, 50)
            flow = state.bloodflow.get(target, 50)
            e.add_field(name="Breath", value=meter_bar(breath, full="🟦"), inline=True)
            e.add_field(name="Bloodflow", value=meter_bar(flow, full="🟧"), inline=True)

    my_eq = equipped_ids(viewer.id)
    e.add_field(name="Grenade", value=item_name(my_eq.get("grenade")), inline=False)

    e.set_footer(text=("Use the buttons to act." if state.active else "Duel ended."))
    return e

# ---------- public banner ----------
def _compose_public_desc(a_name: str, b_name: str, odds: str, result: Optional[str]) -> str:
    lines = [f"{a_name} has picked a fight with {b_name}!", f"Odds: {odds}"]
    if result: lines.append(f"Result: {result}")
    return "\n".join(lines)

def _make_public_banner(desc: str) -> discord.Embed:
    return discord.Embed(description=desc, color=discord.Color.dark_teal())

async def _post_public_banner(inter: discord.Interaction, state: DuelState) -> None:
    a, b = state.players()
    p_a = profile_score(a.user_id, a.hp) / (profile_score(a.user_id, a.hp) + profile_score(b.user_id, b.hp))
    state.odds_phrase = odds_phrase(p_a, a.name, b.name)
    msg = await inter.channel.send(embed=_make_public_banner(_compose_public_desc(a.name, b.name, state.odds_phrase, None)))
    state.public_msg_id = msg.id

def _finish_summary(state: DuelState) -> str:
    winner = state.winner()
    if not winner: return "It ends in a draw."
    loser = state.a if winner is state.b else state.b
    info = state.last_hit.get(loser.user_id, {})
    t = info.get("type")
    w = info.get("weapon") or ""
    if t == "shot":      return f"{winner.name} shot {loser.name}{f' with {w}' if w else ''}."
    if t == "grenade":   return f"{winner.name} blew up {loser.name} with a grenade."
    if t == "punch":     return f"{winner.name} Beat {loser.name} to Death."
    if t == "wrestle":   return f"{winner.name} beat {loser.name} (wrestle)."
    if t == "strangled": return f"{winner.name} choked out {loser.name}."
    if t == "kidnap":    return f"{winner.name} kidnapped {loser.name}."
    if t == "mercy":     return f"{winner.name} spared {loser.name}."
    return f"{winner.name} defeated {loser.name}."

async def _update_public_result(inter: discord.Interaction, state: DuelState, result_text: str) -> None:
    """Try to edit existing banner; if missing/failed, post a fresh result banner."""
    a, b = state.players()
    desc = _compose_public_desc(a.name, b.name, state.odds_phrase or "—", result_text)
    embed = _make_public_banner(desc)

    # First try editing the original banner if we have it.
    if getattr(state, "public_msg_id", None):
        try:
            msg = await inter.channel.fetch_message(state.public_msg_id)
            await msg.edit(embed=embed)
            return
        except Exception as e:
            log.warning("Public banner edit failed; will send a new one: %s", e)

    # Fallback: send a new banner message.
    try:
        msg = await inter.channel.send(embed=embed)
        state.public_msg_id = msg.id
    except Exception:
        log.exception("Failed to post public result banner")

# ---------- Actions used by buttons / AI ----------
def _can_throw_grenade(user_id: int) -> bool:
    return bool(equipped_ids(user_id).get("grenade"))

def _grenade_hit_chance(state: DuelState, thrower_id: int, target_id: int) -> float:
    p = 0.80 - (state.range_idx * 0.12)
    s_throw = load_player_stats(thrower_id)["fitness"]; s_tgt = load_player_stats(target_id)["fitness"]
    p += 0.01 * (s_throw - s_tgt)
    return clamp(p, 0.10, 0.95)

async def _resolve_pending_grenade(inter: discord.Interaction, state: DuelState, acted: Combatant) -> None:
    pend = state.grenades_pending.get(acted.user_id)
    if not pend:
        return
    dfn = load_player_stats(acted.user_id)
    raw = int(pend.get("damage", 0))
    final, mit = apply_armor_reduction(state, acted.user_id, dfn, raw, "grenade")
    acted.hp = max(0, acted.hp - final)
    thrower_id = int(pend.get("from", 0))
    record_hit(state, thrower_id, acted.user_id, "grenade", "grenade")
    state.push(f"💥 Grenade detonates on {acted.name}: **{final}** damage{f' (−{mit} armor)' if mit>0 else ''}.")
    state.grenades_pending.pop(acted.user_id, None)
    await _hud_update_auto(inter, state, inter.user)

def _fists_too_far(state: DuelState) -> bool:
    """True if fists shouldn't be allowed (anything but Hands On / Grappling)."""
    return not (state.grappling or state.can_grapple())

def _attack_once(state: DuelState, attacker: Combatant, defender: Combatant) -> None:
    rng_name = rg_to_loadout_range(state.rngate())
    calc = compute_attack_numbers(state.guild_id, attacker.user_id, rng_name)
    if not calc.get("ready"):
        state.push(calc.get("message", f"{attacker.name} has no viable weapon at this range."))
        return

    # Enforce fists = melee-only
    weapon_name = calc["weapon"].name
    if weapon_name == "Fists" and _fists_too_far(state):
        state.push(f"{attacker.name} is too far away to **swing** their fists.")
        return

    p = float(calc["accuracy"]) / 100.0
    if defender.user_id in state.in_cover:
        p *= (1.0 - float(state.cover_pct.get(defender.user_id, 0)) / 100.0)
    if defender.user_id in state.hidden:
        p = 0.0
    atk = load_player_stats(attacker.user_id); dfn = load_player_stats(defender.user_id)
    p += 0.015 * (atk["combat"] - dfn["combat"]) + 0.010 * (atk["fitness"] - dfn["fitness"])
    p = clamp(p, 0.00, 0.98)

    if random.random() <= p:
        base = int(calc["damage"])
        kind = armor_kind_from_wclass(calc["weapon"].wclass)
        final, mit = apply_armor_reduction(state, defender.user_id, dfn, base, kind)
        defender.hp = max(0, defender.hp - final)
        if weapon_name == "Fists":
            state.push(f"{attacker.name} **swings** and hits {defender.name} for **{final}**{f' (−{mit} armor)' if mit>0 else ''}.")
        else:
            state.push(f"{attacker.name} hits {defender.name} with **{calc['weapon'].name}** for **{final}**{f' (−{mit} armor)' if mit>0 else ''}.")
        record_hit(state, attacker.user_id, defender.user_id, "shot", calc["weapon"].name)
    else:
        if weapon_name == "Fists":
            state.push(f"{attacker.name} **swings** and **misses**.")
        else:
            state.push(f"{attacker.name} fires and **misses**.")

# ---------- Views (with buttons) ----------
class DuelLogView(discord.ui.View):
    def __init__(self, state: DuelState):
        super().__init__(timeout=None)
        self.state = state

class DuelMainView(discord.ui.View):
    def __init__(self, state: DuelState, client: discord.Client):
        super().__init__(timeout=900)
        self.state = state
        self.client = client

    # ==== Buttons ====
    @discord.ui.button(label="Advance", style=discord.ButtonStyle.primary)
    async def btn_advance(self, inter: discord.Interaction, btn: discord.ui.Button):
        if not self._is_my_turn(inter): return
        await _resolve_pending_grenade(inter, self.state, self.state.current())
        steps = random.randint(1, 2)  # meters
        self.state.micro_move(inter.user.id, steps)
        _mark_trail(self.state, inter.user.id)
        _update_cover_flags(self.state)
        self.state.push(f"{self.state.current().name} advances **{steps} meters**.")
        self.state.end_turn()
        await _maybe_ai_take_turn(inter, self.state)
        await _end_and_update(self.state, inter)

    @discord.ui.button(label="Attack", style=discord.ButtonStyle.danger)
    async def btn_attack(self, inter: discord.Interaction, btn: discord.ui.Button):
        if not self._is_my_turn(inter): return
        await _resolve_pending_grenade(inter, self.state, self.state.current())
        attacker = self.state.current(); defender = self.state.other()
        _attack_once(self.state, attacker, defender)
        self.state.end_turn()
        await _maybe_ai_take_turn(inter, self.state)
        await _end_and_update(self.state, inter)

    @discord.ui.button(label="Throw Grenade", style=discord.ButtonStyle.secondary)
    async def btn_grenade(self, inter: discord.Interaction, btn: discord.ui.Button):
        if not self._is_my_turn(inter): return
        thrower = self.state.current(); target = self.state.other()
        if not _can_throw_grenade(thrower.user_id):
            self.state.push(f"{thrower.name} fumbles for a grenade, but has none.")
        else:
            p = _grenade_hit_chance(self.state, thrower.user_id, target.user_id)
            if random.random() <= p:
                dmg = random.randint(30, 40)
                self.state.grenades_pending[target.user_id] = {"from": thrower.user_id, "damage": dmg}
                self.state.push(f"💣 {thrower.name} lobs a grenade! It lands near {target.name} and will detonate at the start of their turn.")
            else:
                self.state.push(f"💣 {thrower.name} throws a grenade but it **misses** the mark.")
        self.state.end_turn()
        await _maybe_ai_take_turn(inter, self.state)
        await _end_and_update(self.state, inter)

    @discord.ui.button(label="Disengage", style=discord.ButtonStyle.secondary)
    async def btn_disengage(self, inter: discord.Interaction, btn: discord.ui.Button):
        if not self._is_my_turn(inter): return
        await _resolve_pending_grenade(inter, self.state, self.state.current())
        steps = -random.randint(1, 3)  # meters back
        self.state.micro_move(inter.user.id, steps)
        _mark_trail(self.state, inter.user.id)
        _update_cover_flags(self.state)
        self.state.push(f"{self.state.current().name} retreats **{abs(steps)} meters**.")
        self.state.end_turn()
        await _maybe_ai_take_turn(inter, self.state)
        await _end_and_update(self.state, inter)

    @discord.ui.button(label="Grapple", style=discord.ButtonStyle.secondary, row=1)
    async def btn_grapple(self, inter: discord.Interaction, btn: discord.ui.Button):
        if not self._is_my_turn(inter): return
        if not self.state.can_grapple():
            await _safe_reply(inter, content="You can only start a grapple at **Hands On** range and when not already grappling.", ephemeral=True)
            return
        self.state.begin_grapple(inter.user.id)
        await _hud_update_auto(inter, self.state, inter.user)

    # ==== helpers ====
    def _is_my_turn(self, inter: discord.Interaction) -> bool:
        if not self.state.active:
            asyncio.create_task(_safe_reply(inter, content="Duel has ended.", ephemeral=True))
            return False
        if inter.user.id != self.state.current().user_id:
            asyncio.create_task(_safe_reply(inter, content="Not your turn.", ephemeral=True))
            return False
        return True

    async def on_timeout(self) -> None:
        try:
            if self.state.active:
                self.state.active = False
                self.state.push("⏱️ Duel timed out due to inactivity.")
                for item in self.children: item.disabled = True
                await _update_public_result(self.client, self.state, "Timed out due to inactivity.")
        except Exception as e:
            log.warning("on_timeout handling failed: %s", e)

# ===== Grapple view =====
class GrappleView(discord.ui.View):
    def __init__(self, state: DuelState, client: discord.Client):
        super().__init__(timeout=900)
        self.state = state
        self.client = client

    @discord.ui.button(label="Choke", style=discord.ButtonStyle.danger)
    async def btn_choke(self, inter: discord.Interaction, btn: discord.ui.Button):
        if not self._is_my_turn(inter): return
        me = self.state.current(); foe = self.state.other()
        my_pos = self.state.positioning.get(me.user_id, 50)
        their_pos = self.state.positioning.get(foe.user_id, 50)
        p = clamp(0.50 + (my_pos - their_pos) / 200.0, 0.20, 0.85)
        if random.random() <= p:
            self.state.choking = (me.user_id, foe.user_id)
            self.state.breath[foe.user_id] = self.state.breath.get(foe.user_id, 50)
            self.state.bloodflow[foe.user_id] = self.state.bloodflow.get(foe.user_id, 50)
            self.state.push(f"🫵 {me.name} secures a **choke** on {foe.name}!")
        else:
            self.state.push(f"{me.name} reaches for a choke but **fails**.")
        self.state.end_turn()
        await _maybe_ai_take_turn(inter, self.state)
        await _end_and_update(self.state, inter)

    @discord.ui.button(label="Wrestle", style=discord.ButtonStyle.primary)
    async def btn_wrestle(self, inter: discord.Interaction, btn: discord.ui.Button):
        if not self._is_my_turn(inter): return
        me = self.state.current(); foe = self.state.other()
        dmg = random.randint(1, 2)
        foe.hp = max(0, foe.hp - dmg)
        if random.random() < 0.5:
            self.state.positioning[me.user_id] = iclamp(self.state.positioning.get(me.user_id, 50) + 10, 0, 100)
            self.state.positioning[foe.user_id] = iclamp(self.state.positioning.get(foe.user_id, 50) - 10, 0, 100)
            swing = " Position improved."
        else:
            swing = ""
        self.state.push(f"{me.name} **wrestles** {foe.name} for **{dmg}**.{swing}")
        record_hit(self.state, me.user_id, foe.user_id, "wrestle", "")
        self.state.end_turn()
        await _maybe_ai_take_turn(inter, self.state)
        await _end_and_update(self.state, inter)

    @discord.ui.button(label="Punch", style=discord.ButtonStyle.secondary)
    async def btn_punch(self, inter: discord.Interaction, btn: discord.ui.Button):
        if not self._is_my_turn(inter): return
        me = self.state.current(); foe = self.state.other()
        dmg = random.randint(1, 5)
        foe.hp = max(0, foe.hp - dmg)
        self.state.push(f"{me.name} **punches** {foe.name} for **{dmg}**.")
        record_hit(self.state, me.user_id, foe.user_id, "punch", "Fists")
        self.state.end_turn()
        await _maybe_ai_take_turn(inter, self.state)
        await _end_and_update(self.state, inter)

    @discord.ui.button(label="Break Free", style=discord.ButtonStyle.success)
    async def btn_breakfree(self, inter: discord.Interaction, btn: discord.ui.Button):
        if not self._is_my_turn(inter): return
        me = self.state.current(); foe = self.state.other()
        my_pos = self.state.positioning.get(me.user_id, 50)
        their_pos = self.state.positioning.get(foe.user_id, 50)
        p = clamp(0.40 + (my_pos - their_pos) / 200.0, 0.10, 0.90)
        if random.random() <= p:
            self.state.grappling = False
            self.state.choking = None
            self.state.push(f"🧷 {me.name} **breaks free** from the grapple!")
        else:
            self.state.positioning[me.user_id] = iclamp(my_pos - 5, 0, 100)
            self.state.positioning[foe.user_id] = iclamp(their_pos + 5, 0, 100)
            self.state.push(f"{me.name} tries to break free but **fails**.")
        self.state.end_turn()
        await _maybe_ai_take_turn(inter, self.state)
        await _end_and_update(self.state, inter)

    def _is_my_turn(self, inter: discord.Interaction) -> bool:
        if not self.state.active:
            asyncio.create_task(_safe_reply(inter, content="Duel has ended.", ephemeral=True)); return False
        if inter.user.id != self.state.current().user_id:
            asyncio.create_task(_safe_reply(inter, content="Not your turn.", ephemeral=True)); return False
        if not self.state.grappling or self.state.choking:
            asyncio.create_task(_safe_reply(inter, content="Grapple actions are unavailable right now.", ephemeral=True)); return False
        return True

# ===== Choke view (only choker gets buttons) =====
class ChokeView(discord.ui.View):
    def __init__(self, state: DuelState, client: discord.Client):
        super().__init__(timeout=900)
        self.state = state
        self.client = client

    @discord.ui.button(label="Choke", style=discord.ButtonStyle.danger)
    async def btn_squeeze(self, inter: discord.Interaction, btn: discord.ui.Button):
        if not self._is_my_turn(inter): return
        choker, target = self.state.choking or (None, None)
        if target is None:
            await _hud_update_auto(inter, self.state, inter.user)
            return
        # Reduce breath & bloodflow (KO by consciousness, not HP)
        self.state.breath[target] = iclamp(self.state.breath.get(target, 50) - random.randint(8, 12), 0, 100)
        self.state.bloodflow[target] = iclamp(self.state.bloodflow.get(target, 50) - random.randint(4, 8), 0, 100)
        self.state.push(f"🫀 {self.state.current().name} **tightens the choke**.")
        if self.state.breath[target] <= 0 or self.state.bloodflow[target] <= 0:
            self.state.unconscious.add(target)  # White HP bar, not dead
            # Record and arm finisher
            record_hit(self.state, choker, target, "strangled", "")
            winner = self.state.winner()
            if winner:
                self.state.finisher = (winner.user_id, target)  # <-- finisher lock
                # Log once
                msg = "☠️ Your opponent is **unconscious**. Choose their fate."
                if not self.state.log_lines or self.state.log_lines[-1] != msg:
                    self.state.add_raw(msg)
        self.state.end_turn()
        await _maybe_ai_take_turn(inter, self.state)
        await _end_and_update(self.state, inter)

    @discord.ui.button(label="Let go", style=discord.ButtonStyle.secondary)
    async def btn_letgo(self, inter: discord.Interaction, btn: discord.ui.Button):
        if not self._is_my_turn(inter): return
        self.state.choking = None
        self.state.push(f"🫁 {self.state.current().name} **releases the choke**.")
        self.state.end_turn()
        await _maybe_ai_take_turn(inter, self.state)
        await _end_and_update(self.state, inter)

    def _is_my_turn(self, inter: discord.Interaction) -> bool:
        if not self.state.active:
            asyncio.create_task(_safe_reply(inter, content="Duel has ended.", ephemeral=True)); return False
        if inter.user.id != self.state.current().user_id:
            asyncio.create_task(_safe_reply(inter, content="Not your turn.", ephemeral=True)); return False
        if not self.state.choking or self.state.choking[0] != inter.user.id:
            asyncio.create_task(_safe_reply(inter, content="Only the choker can act here.", ephemeral=True)); return False
        return True

# ---------- finisher (winner chooses) ----------
class FinalizeView(discord.ui.View):
    def __init__(self, state: DuelState, client: discord.Client, victor_id: int, target_id: int):
        super().__init__(timeout=900)
        self.state = state
        self.client = client
        self.victor_id = victor_id
        self.target_id = target_id

    def _is_victor(self, inter: discord.Interaction) -> bool:
        if not self.state.active:
            asyncio.create_task(_safe_reply(inter, content="Duel has ended.", ephemeral=True)); return False
        if inter.user.id != self.victor_id:
            asyncio.create_task(_safe_reply(inter, content="Only the victor can choose.", ephemeral=True)); return False
        return True

    @discord.ui.button(label="Mercy", style=discord.ButtonStyle.success)
    async def btn_mercy(self, inter: discord.Interaction, btn: discord.ui.Button):
        if not self._is_victor(inter): return
        victor = self.state.a if self.state.a.user_id == self.victor_id else self.state.b
        target = self.state.a if self.state.a.user_id == self.target_id else self.state.b
        self.state.add_raw(f"🕊️ {victor.name} shows **mercy** to {target.name}.")
        self.state.last_hit[self.target_id] = {"by": self.victor_id, "type": "mercy", "weapon": ""}
        self.state.finisher = None
        self.state.active = False
        await _update_public_result(inter, self.state, f"{victor.name} spared {target.name}.")
        await _hud_update_auto(inter, self.state, inter.user)

    @discord.ui.button(label="Beat", style=discord.ButtonStyle.danger)
    async def btn_beat(self, inter: discord.Interaction, btn: discord.ui.Button):
        if not self._is_victor(inter): return
        victor = self.state.a if self.state.a.user_id == self.victor_id else self.state.b
        target = self.state.a if self.state.a.user_id == self.target_id else self.state.b
        dmg = random.randint(1, 7)  # 1–7 damage
        target.hp = max(0, target.hp - dmg)
        self.state.push(f"👊 {victor.name} **beats** the unconscious {target.name} for **{dmg}**.")
        record_hit(self.state, self.victor_id, self.target_id, "punch", "Fists")
        if target.hp <= 0:
            self.state.finisher = None
            self.state.active = False
            await _update_public_result(inter, self.state, _finish_summary(self.state))
        await _hud_update_auto(inter, self.state, inter.user)

    @discord.ui.button(label="Kidnap", style=discord.ButtonStyle.primary)
    async def btn_kidnap(self, inter: discord.Interaction, btn: discord.ui.Button):
        if not self._is_victor(inter): return
        victor = self.state.a if self.state.a.user_id == self.victor_id else self.state.b
        target = self.state.a if self.state.a.user_id == self.target_id else self.state.b
        ok_msg = ""
        try:
            if add_item_to_inventory:
                item = {"category": "hostage", "name": f"Hostage: {target.name}", "meta": {"target_id": self.target_id}}
                add_item_to_inventory(self.victor_id, item)  # type: ignore
                ok_msg = " (added to inventory)"
        except Exception as e:
            log.warning("Kidnap inventory add failed: %s", e)
        self.state.add_raw(f"🧿 {victor.name} **kidnaps** {target.name}.{ok_msg}")
        self.state.last_hit[self.target_id] = {"by": self.victor_id, "type": "kidnap", "weapon": ""}
        self.state.finisher = None
        self.state.active = False
        await _update_public_result(inter, self.state, f"{victor.name} kidnapped {target.name}.")
        await _hud_update_auto(inter, self.state, inter.user)

    @discord.ui.button(label="Souvenir", style=discord.ButtonStyle.secondary, disabled=True)
    async def btn_souvenir(self, inter: discord.Interaction, btn: discord.ui.Button):
        await _safe_reply(inter, content="Souvenir options coming soon.", ephemeral=True)

# ---------- helpers to end / offer finisher ----------
async def _maybe_offer_finisher(inter: discord.Interaction, state: DuelState) -> Optional[discord.ui.View]:
    w = state.winner()
    if not w:
        return None
    loser = state.a if w is state.b else state.b
    if loser.user_id in state.unconscious and state.active:
        if not getattr(state, "finisher", None):
            state.finisher = (w.user_id, loser.user_id)
        msg = "☠️ Your opponent is **unconscious**. Choose their fate."
        if not state.log_lines or state.log_lines[-1] != msg:
            state.add_raw(msg)
        return FinalizeView(state, inter.client, victor_id=w.user_id, target_id=loser.user_id)
    return None

async def _end_if_finished_or_offer(state: DuelState, inter: discord.Interaction):
    fin_view = await _maybe_offer_finisher(inter, state)
    if fin_view is not None:
        await _hud_update_with_view(inter, state, inter.user, fin_view)
        return

    # Otherwise normal end
    if state.is_draw():
        state.finisher = None
        state.active = False
        state.push("Both fighters fall! It's a draw.")
        await _update_public_result(inter, state, "It ends in a draw.")
    else:
        winner = state.winner()
        if winner is not None:
            state.finisher = None
            state.active = False
            summary = _finish_summary(state)
            state.push(f"🏆 {winner.name} wins!")
            await _update_public_result(inter, state, summary)
    await _hud_update_auto(inter, state, inter.user)

async def _end_and_update(state: DuelState, inter: discord.Interaction):
    await _end_if_finished_or_offer(state, inter)

# ---------- simple per-channel registry & AI ----------
_DUEL_BY_CHANNEL: Dict[Tuple[int, int], DuelState] = {}

def _chan_key(inter: discord.Interaction) -> Tuple[int, int]:
    return (inter.guild_id or 0, inter.channel_id)

def _end_duel_in_channel(state: DuelState | None):
    if not state: return
    _DUEL_BY_CHANNEL.pop((state.guild_id, state.channel_id), None)

async def _maybe_ai_take_turn(inter: discord.Interaction, state: DuelState):
    """Very simple AI; respects choke/grapple phases, and logs meters when advancing."""
    if not state.active or not state.current().is_ai:
        return

    # Finisher available? present it; AI won't act further here.
    fin_view = await _maybe_offer_finisher(inter, state)
    if fin_view is not None:
        await _hud_update_with_view(inter, state, inter.user, fin_view)
        return

    await _resolve_pending_grenade(inter, state, state.current())

    ai = state.current()
    foe = state.other()

    # Choke phase
    if state.choking:
        choker, target = state.choking
        if ai.user_id == choker:
            state.breath[target] = iclamp(state.breath.get(target, 50) - random.randint(8, 12), 0, 100)
            state.bloodflow[target] = iclamp(state.bloodflow.get(target, 50) - random.randint(4, 8), 0, 100)
            state.push(f"🤖 {ai.name} tightens the choke.")
            if state.breath[target] <= 0 or state.bloodflow[target] <= 0:
                state.unconscious.add(target)
                record_hit(state, choker, target, "strangled", "")
                winner = state.winner()
                if winner:
                    state.finisher = (winner.user_id, target)
                    msg = "☠️ Your opponent is **unconscious**. Choose their fate."
                    if not state.log_lines or state.log_lines[-1] != msg:
                        state.add_raw(msg)
            state.end_turn()
            await _hud_update_auto(inter, state, inter.user)
            return
        else:
            state.push(f"🤖 {ai.name} struggles for air…")
            state.end_turn()
            await _hud_update_auto(inter, state, inter.user)
            return

    # Grapple phase
    if state.grappling:
        choice = random.choice(["wrestle", "punch", "break"])
        if choice == "wrestle":
            dmg = random.randint(1, 2)
            foe.hp = max(0, foe.hp - dmg)
            if random.random() < 0.5:
                state.positioning[ai.user_id] = iclamp(state.positioning.get(ai.user_id, 50) + 10, 0, 100)
                state.positioning[foe.user_id] = iclamp(state.positioning.get(foe.user_id, 50) - 10, 0, 100)
                swing = " Position improved."
            else:
                swing = ""
            state.push(f"🤖 {ai.name} wrestles {foe.name} for **{dmg}**.{swing}")
            record_hit(state, ai.user_id, foe.user_id, "wrestle", "")
        elif choice == "punch":
            dmg = random.randint(1, 5)
            foe.hp = max(0, foe.hp - dmg)
            state.push(f"🤖 {ai.name} punches {foe.name} for **{dmg}**.")
            record_hit(state, ai.user_id, foe.user_id, "punch", "Fists")
        else:
            my_pos = state.positioning.get(ai.user_id, 50)
            their_pos = state.positioning.get(foe.user_id, 50)
            p = clamp(0.40 + (my_pos - their_pos) / 200.0, 0.10, 0.90)
            if random.random() <= p:
                state.grappling = False
                state.choking = None
                state.push(f"🤖 {ai.name} breaks free!")
            else:
                state.positioning[ai.user_id] = iclamp(my_pos - 5, 0, 100)
                state.positioning[foe.user_id] = iclamp(their_pos + 5, 0, 100)
                state.push(f"🤖 {ai.name} tries to break free but fails.")
        state.end_turn()
        await _hud_update_auto(inter, state, inter.user)
        return

    # Ranged/default phase
    rng_name = rg_to_loadout_range(state.rngate())
    calc = compute_attack_numbers(state.guild_id, ai.user_id, rng_name)
    took_action = False
    if calc.get("ready"):
        weapon_name = calc["weapon"].name
        # Enforce fists = melee-only for AI too
        if weapon_name == "Fists" and _fists_too_far(state):
            # close distance instead
            step = random.randint(1, 2)
            state.micro_move(ai.user_id, step)
            _mark_trail(state, ai.user_id)
            _update_cover_flags(state)
            state.push(f"🤖 {ai.name} advances **{step} meters**.")
            took_action = True
        else:
            p = float(calc["accuracy"]) / 100.0
            if foe.user_id in state.in_cover:
                p *= (1.0 - float(state.cover_pct.get(foe.user_id, 0)) / 100.0)
            if foe.user_id in state.hidden:
                p = 0.0
            atk = load_player_stats(ai.user_id); dfn = load_player_stats(foe.user_id)
            p += 0.015 * (atk["combat"] - dfn["combat"]) + 0.010 * (atk["fitness"] - dfn["fitness"])
            p = clamp(p, 0.00, 0.98)
            if random.random() <= p:
                base = int(calc["damage"])
                kind = armor_kind_from_wclass(calc["weapon"].wclass)
                final, mit = apply_armor_reduction(state, foe.user_id, dfn, base, kind)
                foe.hp = max(0, foe.hp - final)
                if weapon_name == "Fists":
                    state.push(f"🤖 {ai.name} **swings** and hits {foe.name} for **{final}**{f' (−{mit} armor)' if mit>0 else ''}.")
                else:
                    state.push(f"🤖 {ai.name} fires **{calc['weapon'].name}** and hits {foe.name} for **{final}**{f' (−{mit} armor)' if mit>0 else ''}.")
                record_hit(state, ai.user_id, foe.user_id, "shot", calc["weapon"].name)
                took_action = True
            else:
                if weapon_name == "Fists":
                    state.push(f"🤖 {ai.name} **swings** and **misses**.")
                else:
                    state.push(f"🤖 {ai.name} fires and **misses**.")
                took_action = True

    if not took_action:
        step = random.randint(1, 2)
        state.micro_move(ai.user_id, step)
        _mark_trail(state, ai.user_id)
        _update_cover_flags(state)
        state.push(f"🤖 {ai.name} advances **{step} meters**.")

    state.end_turn()
    await _hud_update_auto(inter, state, inter.user)

# ---------- Command Group: /duel ----------
duel_group = app_commands.Group(name="duel", description="Duel commands")

@duel_group.command(name="start", description="Start a duel with another player")
async def duel_start(inter: discord.Interaction, opponent: discord.Member):
    me = inter.user
    if opponent.id == me.id:
        await _safe_reply(inter, content="You can’t duel yourself. Try `/duel ai` to test against a bot.", ephemeral=True)
        return

    key = _chan_key(inter)
    if key in _DUEL_BY_CHANNEL and _DUEL_BY_CHANNEL[key].active:
        await _safe_reply(inter, content="There’s already an active duel in this channel. Use `/duel reset` first.", ephemeral=True)
        return

    a = Combatant(user_id=me.id, name=me.display_name)
    b = Combatant(user_id=opponent.id, name=opponent.display_name)
    state = DuelState(guild_id=key[0], channel_id=key[1], a=a, b=b)
    _seed_combat_log(state); _decide_initiative(state)
    _init_battlefield(state)
    _DUEL_BY_CHANNEL[key] = state

    await _post_public_banner(inter, state)
    await _safe_reply(inter, embed=player_hud_embed(state, me), view=_make_view(state, inter.client, me.id), ephemeral=False)

@duel_group.command(name="ai", description="Start a duel against an AI Defender")
async def duel_ai(inter: discord.Interaction):
    me = inter.user
    key = _chan_key(inter)
    if key in _DUEL_BY_CHANNEL and _DUEL_BY_CHANNEL[key].active:
        await _safe_reply(inter, content="There’s already an active duel in this channel. Use `/duel reset` first.", ephemeral=True)
        return

    a = Combatant(user_id=me.id, name=me.display_name)
    b = Combatant(user_id=10_000_000_000 + (me.id % 1_000_000_000), name="AI Defender", is_ai=True)
    state = DuelState(guild_id=key[0], channel_id=key[1], a=a, b=b)
    _seed_combat_log(state); _decide_initiative(state)
    _init_battlefield(state)
    _DUEL_BY_CHANNEL[key] = state

    await _post_public_banner(inter, state)
    await _safe_reply(inter, embed=player_hud_embed(state, me), view=_make_view(state, inter.client, me.id), ephemeral=False)

    if state.active and state.current().is_ai:
        await asyncio.sleep(0.3)
        await _maybe_ai_take_turn(inter, state)

@duel_group.command(name="reset", description="Force end the duel in this channel")
async def duel_reset(inter: discord.Interaction):
    state = _DUEL_BY_CHANNEL.get(_chan_key(inter))
    if not state:
        await _safe_reply(inter, content="No duel to reset here.", ephemeral=True)
        return
    state.finisher = None
    state.active = False
    state.push("⛔ Duel reset.")
    _end_duel_in_channel(state)
    try:
        await _update_public_result(inter, state, "Aborted.")
    except Exception:
        pass
    await _safe_reply(inter, embed=player_hud_embed(state, inter.user), ephemeral=True)

def register_duel(tree: app_commands.CommandTree):
    try:
        existing = tree.get_command("duel", type=discord.AppCommandType.chat_input, guild=None)
        if existing and not isinstance(existing, app_commands.Group):
            tree.remove_command(existing.name, type=discord.AppCommandType.chat_input, guild=None)
    except Exception as e:
        logging.getLogger("duel").warning("Couldn't remove old /duel: %s", e)
    tree.add_command(duel_group)

# ---------- registry / helpers ----------
def _chan_key(inter: discord.Interaction) -> Tuple[int, int]:
    return (inter.guild_id or 0, inter.channel_id)
