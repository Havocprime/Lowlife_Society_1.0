# FILE: src/bot/duel/views.py
"""
Discord Views & HUD plumbing:
- All the interactive buttons
- Factory to choose the right view per-state
- HUD update helpers (edit the message correctly)
- Finisher helpers and end-of-duel banner updates
"""

from __future__ import annotations
import asyncio
import logging
import random
from typing import Optional

import discord

from src.core.duel_core import (
    DuelState, Combatant, clamp, record_hit, iclamp,
)
from .constants import GLYPH_GRAPPLE
from .battlefield import update_cover_flags, mark_path_between
from .ui import player_hud_embed, update_public_result, finish_summary

# Best-effort inventory hook (optional)
try:
    from src.core.inventory import add_item_to_inventory  # type: ignore
except Exception:  # pragma: no cover
    add_item_to_inventory = None  # type: ignore

log = logging.getLogger("duel.views")

# ---------- safe reply ----------

async def safe_reply(
    inter: discord.Interaction,
    *,
    content: str | None = None,
    embed: discord.Embed | None = None,
    view: discord.ui.View | None = None,
    ephemeral: bool = False,
) -> None:
    """Send or follow-up a reply while surviving ephemeral/interaction state quirks."""
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

# ---------- HUD update helpers ----------

def make_view(state: DuelState, client: discord.Client, viewer_id: int) -> discord.ui.View:
    """Pick the correct button set from the POV of `viewer_id`."""
    if not state.active:
        return DuelLogView(state)

    finisher = getattr(state, "finisher", None)
    if finisher:
        victor_id, target_id = finisher
        if viewer_id == victor_id:
            return FinalizeView(state, client, victor_id=victor_id, target_id=target_id)
        return DuelLogView(state)

    # v0.3 — Choke flow menus:
    if state.choking:
        choker_id, victim_id = state.choking
        if state.current().user_id == choker_id and viewer_id == choker_id:
            # Choker's turn → Choke / Push
            return ChokeView(state, client)
        if state.current().user_id == victim_id and viewer_id == victim_id:
            # Victim's turn → Gouge (only here), Wrestle, Punch
            return ChokedVictimView(state, client)
        return DuelLogView(state)

    if state.grappling:
        if viewer_id == state.current().user_id:
            return GrappleView(state, client)
        return DuelLogView(state)

    return DuelMainView(state, client)

async def hud_update_with_view(
    interaction: discord.Interaction,
    state: DuelState,
    viewer: discord.User,
    view: discord.ui.View,
) -> None:
    """Force a specific view (e.g., when a finisher becomes available)."""
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

async def hud_update_auto(
    interaction: discord.Interaction,
    state: DuelState,
    viewer: discord.User,
) -> None:
    """Rebuilds the correct view to avoid stale buttons after state changes."""
    view = make_view(state, interaction.client, viewer.id) if state.active else DuelLogView(state)
    await hud_update_with_view(interaction, state, viewer, view)

# ---------- Views (buttons) ----------

class DuelLogView(discord.ui.View):
    """Read-only view when the duel is over (or when a non-actor is looking)."""
    def __init__(self, state: DuelState):
        super().__init__(timeout=None)
        self.state = state

class DuelMainView(discord.ui.View):
    """Primary ranged actions view."""
    def __init__(self, state: DuelState, client: discord.Client):
        super().__init__(timeout=900)
        self.state = state
        self.client = client

        # v0.3: ensure optional fields exist without breaking old saves
        if not hasattr(self.state, "cover_level"):
            self.state.cover_level = {}  # type: ignore[attr-defined]

    # === Buttons ===

    @discord.ui.button(label="Advance", style=discord.ButtonStyle.primary)
    async def btn_advance(self, inter: discord.Interaction, btn: discord.ui.Button):
        from .actions import resolve_pending_grenade  # local import avoids cycles
        from .ai import maybe_ai_take_turn
        if not self._is_my_turn(inter): return
        await resolve_pending_grenade(inter, self.state, self.state.current())
        steps = random.randint(1, 2)  # meters
        prev = iclamp(self.state.pos.get(inter.user.id, 0), 0, self.state.vis_segments - 1)
        self.state.micro_move(inter.user.id, steps)
        cur = iclamp(self.state.pos.get(inter.user.id, 0), 0, self.state.vis_segments - 1)
        mark_path_between(self.state, inter.user.id, prev, cur)
        update_cover_flags(self.state)
        self.state.push(f"{self.state.current().name} advances **{steps} meters**.")
        self.state.end_turn()
        await maybe_ai_take_turn(inter, self.state)
        await end_and_update(self.state, inter)

    @discord.ui.button(label="Attack", style=discord.ButtonStyle.danger)
    async def btn_attack(self, inter: discord.Interaction, btn: discord.ui.Button):
        from .actions import resolve_pending_grenade, attack_once
        from .ai import maybe_ai_take_turn
        if not self._is_my_turn(inter): return
        await resolve_pending_grenade(inter, self.state, self.state.current())
        attacker = self.state.current(); defender = self.state.other()
        attack_once(self.state, attacker, defender)
        self.state.end_turn()
        await maybe_ai_take_turn(inter, self.state)
        await end_and_update(self.state, inter)

    @discord.ui.button(label="Throw Grenade", style=discord.ButtonStyle.secondary)
    async def btn_grenade(self, inter: discord.Interaction, btn: discord.ui.Button):
        from .actions import can_throw_grenade, grenade_hit_chance
        from .ai import maybe_ai_take_turn
        if not self._is_my_turn(inter): return
        thrower = self.state.current(); target = self.state.other()
        if not can_throw_grenade(thrower.user_id):
            self.state.push(f"{thrower.name} fumbles for a grenade, but has none.")
        else:
            p = grenade_hit_chance(self.state, thrower.user_id, target.user_id)
            if random.random() <= p:
                dmg = random.randint(30, 40)
                self.state.grenades_pending[target.user_id] = {"from": thrower.user_id, "damage": dmg}
                self.state.push(f"💣 {thrower.name} lobs a grenade! It lands near {target.name} and will detonate at the start of their turn.")
            else:
                self.state.push(f"💣 {thrower.name} throws a grenade but it **misses** the mark.")
        self.state.end_turn()
        from .ai import maybe_ai_take_turn
        await maybe_ai_take_turn(inter, self.state)
        await end_and_update(self.state, inter)

    @discord.ui.button(label="Disengage", style=discord.ButtonStyle.secondary)
    async def btn_disengage(self, inter: discord.Interaction, btn: discord.ui.Button):
        from .actions import resolve_pending_grenade
        from .ai import maybe_ai_take_turn
        if not self._is_my_turn(inter): return
        await resolve_pending_grenade(inter, self.state, self.state.current())
        steps = -random.randint(1, 3)  # meters back
        prev = iclamp(self.state.pos.get(inter.user.id, 0), 0, self.state.vis_segments - 1)
        self.state.micro_move(inter.user.id, steps)
        cur = iclamp(self.state.pos.get(inter.user.id, 0), 0, self.state.vis_segments - 1)
        mark_path_between(self.state, inter.user.id, prev, cur)
        update_cover_flags(self.state)
        self.state.push(f"{self.state.current().name} retreats **{abs(steps)} meters**.")
        self.state.end_turn()
        await maybe_ai_take_turn(inter, self.state)
        await end_and_update(self.state, inter)

    # --- v0.3: Defensive intents & Cover ---

    @discord.ui.button(label="Block", style=discord.ButtonStyle.secondary, row=1)
    async def btn_block(self, inter: discord.Interaction, btn: discord.ui.Button):
        """Consumes turn; sets status_block on the current fighter via actions.act_block."""
        from .actions import act_block
        from .ai import maybe_ai_take_turn
        if not self._is_my_turn(inter): return
        self.state.push(await _apply_and_log(inter, self.state, act_block))
        self.state.end_turn()
        await maybe_ai_take_turn(inter, self.state)
        await end_and_update(self.state, inter)

    @discord.ui.button(label="Dodge", style=discord.ButtonStyle.secondary, row=1)
    async def btn_dodge(self, inter: discord.Interaction, btn: discord.ui.Button):
        """Consumes turn; sets status_dodge on the current fighter via actions.act_dodge."""
        from .actions import act_dodge
        from .ai import maybe_ai_take_turn
        if not self._is_my_turn(inter): return
        self.state.push(await _apply_and_log(inter, self.state, act_dodge))
        self.state.end_turn()
        await maybe_ai_take_turn(inter, self.state)
        await end_and_update(self.state, inter)

    @discord.ui.button(label="Take Cover", style=discord.ButtonStyle.secondary, row=1)
    async def btn_take_cover(self, inter: discord.Interaction, btn: discord.ui.Button):
        """Toggle Partial → Full cover for this user; also updates map flags."""
        from .ai import maybe_ai_take_turn
        if not self._is_my_turn(inter): return
        if not hasattr(self.state, "cover_level"):
            self.state.cover_level = {}  # type: ignore[attr-defined]
        cur = self.state.cover_level.get(inter.user.id, 0)
        nxt = 1 if cur == 0 else 2
        self.state.cover_level[inter.user.id] = nxt
        update_cover_flags(self.state)
        lvl = "FULL" if nxt == 2 else "PARTIAL"
        self.state.push(f"{self.state.current().name} moves into **{lvl} cover**.")
        self.state.end_turn()
        await maybe_ai_take_turn(inter, self.state)
        await end_and_update(self.state, inter)

    @discord.ui.button(label="Leave Cover", style=discord.ButtonStyle.secondary, row=1)
    async def btn_leave_cover(self, inter: discord.Interaction, btn: discord.ui.Button):
        from .ai import maybe_ai_take_turn
        if not self._is_my_turn(inter): return
        if hasattr(self.state, "cover_level"):
            self.state.cover_level[inter.user.id] = 0  # type: ignore[attr-defined]
        update_cover_flags(self.state)
        self.state.push(f"{self.state.current().name} **leaves cover**.")
        self.state.end_turn()
        await maybe_ai_take_turn(inter, self.state)
        await end_and_update(self.state, inter)

    @discord.ui.button(label="Grapple", style=discord.ButtonStyle.secondary, row=2)
    async def btn_grapple(self, inter: discord.Interaction, btn: discord.ui.Button):
        if not self._is_my_turn(inter): return
        if not self.state.can_grapple():
            await safe_reply(inter, content="You can only start a grapple at **Hands On** range and when not already grappling.", ephemeral=True)
            return
        self.state.begin_grapple(inter.user.id)
        await hud_update_auto(inter, self.state, inter.user)

    # === helpers ===
    def _is_my_turn(self, inter: discord.Interaction) -> bool:
        if not self.state.active:
            asyncio.create_task(safe_reply(inter, content="Duel has ended.", ephemeral=True))
            return False
        if inter.user.id != self.state.current().user_id:
            asyncio.create_task(safe_reply(inter, content="Not your turn.", ephemeral=True))
            return False
        return True

    async def on_timeout(self) -> None:
        try:
            if self.state.active:
                self.state.active = False
                self.state.push("⏱️ Duel timed out due to inactivity.")
                for item in self.children: item.disabled = True
                await update_public_result(self.client, self.state, "Timed out due to inactivity.")
        except Exception as e:
            log.warning("on_timeout handling failed: %s", e)

# ----- Grapple-only view -----

class GrappleView(discord.ui.View):
    def __init__(self, state: DuelState, client: discord.Client):
        super().__init__(timeout=900)
        self.state = state
        self.client = client

    @discord.ui.button(label="Choke", style=discord.ButtonStyle.danger)
    async def btn_choke(self, inter: discord.Interaction, btn: discord.ui.Button):
        from .ai import maybe_ai_take_turn
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
        await maybe_ai_take_turn(inter, self.state)
        await end_and_update(self.state, inter)

    @discord.ui.button(label="Wrestle", style=discord.ButtonStyle.primary)
    async def btn_wrestle(self, inter: discord.Interaction, btn: discord.ui.Button):
        from .ai import maybe_ai_take_turn
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
        await maybe_ai_take_turn(inter, self.state)
        await end_and_update(self.state, inter)

    @discord.ui.button(label="Punch", style=discord.ButtonStyle.secondary)
    async def btn_punch(self, inter: discord.Interaction, btn: discord.ui.Button):
        from .ai import maybe_ai_take_turn
        if not self._is_my_turn(inter): return
        me = self.state.current(); foe = self.state.other()
        dmg = random.randint(1, 5)
        foe.hp = max(0, foe.hp - dmg)
        self.state.push(f"{me.name} **punches** {foe.name} for **{dmg}**.")
        record_hit(self.state, me.user_id, foe.user_id, "punch", "Fists")
        self.state.end_turn()
        await maybe_ai_take_turn(inter, self.state)
        await end_and_update(self.state, inter)

    @discord.ui.button(label="Break Free", style=discord.ButtonStyle.success)
    async def btn_breakfree(self, inter: discord.Interaction, btn: discord.ui.Button):
        from .ai import maybe_ai_take_turn
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
        await maybe_ai_take_turn(inter, self.state)
        await end_and_update(self.state, inter)

    def _is_my_turn(self, inter: discord.Interaction) -> bool:
        if not self.state.active:
            asyncio.create_task(safe_reply(inter, content="Duel has ended.", ephemeral=True)); return False
        if inter.user.id != self.state.current().user_id:
            asyncio.create_task(safe_reply(inter, content="Not your turn.", ephemeral=True)); return False
        if not self.state.grappling or self.state.choking:
            asyncio.create_task(safe_reply(inter, content="Grapple actions are unavailable right now.", ephemeral=True)); return False
        return True

# ----- Choke-only view (choker gets buttons) -----

class ChokeView(discord.ui.View):
    """Choker's turn: can Choke (damage) or Push (break & create space)."""
    def __init__(self, state: DuelState, client: discord.Client):
        super().__init__(timeout=900)
        self.state = state
        self.client = client

    @discord.ui.button(label="Choke", style=discord.ButtonStyle.danger)
    async def btn_squeeze(self, inter: discord.Interaction, btn: discord.ui.Button):
        from .ai import maybe_ai_take_turn
        if not self._is_my_turn(inter): return
        choker, target = self.state.choking or (None, None)
        if target is None:
            await hud_update_auto(inter, self.state, inter.user)
            return
        self.state.breath[target] = iclamp(self.state.breath.get(target, 50) - random.randint(8, 12), 0, 100)
        self.state.bloodflow[target] = iclamp(self.state.bloodflow.get(target, 50) - random.randint(4, 8), 0, 100)
        self.state.push(f"🫀 {self.state.current().name} **tightens the choke**.")
        if self.state.breath[target] <= 0 or self.state.bloodflow[target] <= 0:
            self.state.unconscious.add(target)
            record_hit(self.state, choker, target, "strangled", "")
            winner = self.state.winner()
            if winner:
                self.state.finisher = (winner.user_id, target)
                msg = "☠️ Your opponent is **unconscious**. Choose their fate."
                if not self.state.log_lines or self.state.log_lines[-1] != msg:
                    self.state.add_raw(msg)
        self.state.end_turn()
        await maybe_ai_take_turn(inter, self.state)
        await end_and_update(self.state, inter)

    @discord.ui.button(label="Push", style=discord.ButtonStyle.secondary)
    async def btn_push(self, inter: discord.Interaction, btn: discord.ui.Button):
        """v0.3: replaces 'Let go'. Breaks choke and creates space."""
        from .ai import maybe_ai_take_turn
        if not self._is_my_turn(inter): return
        choker, target = self.state.choking or (None, None)
        self.state.choking = None
        # create a bit of space by shifting positioning apart
        if choker is not None and target is not None:
            self.state.positioning[choker] = iclamp(self.state.positioning.get(choker, 50) - 10, 0, 100)
            self.state.positioning[target] = iclamp(self.state.positioning.get(target, 50) + 10, 0, 100)
        self.state.push(f"🫁 {self.state.current().name} **pushes off**, breaking the choke and creating space.")
        self.state.end_turn()
        await maybe_ai_take_turn(inter, self.state)
        await end_and_update(self.state, inter)

    def _is_my_turn(self, inter: discord.Interaction) -> bool:
        if not self.state.active:
            asyncio.create_task(safe_reply(inter, content="Duel has ended.", ephemeral=True)); return False
        if inter.user.id != self.state.current().user_id:
            asyncio.create_task(safe_reply(inter, content="Not your turn.", ephemeral=True)); return False
        if not self.state.choking or self.state.choking[0] != inter.user.id:
            asyncio.create_task(safe_reply(inter, content="Only the choker can act here.", ephemeral=True)); return False
        return True

# ----- v0.3: Victim-under-choke view (Gouge appears only for the victim) -----

class ChokedVictimView(discord.ui.View):
    """Victim's turn while being choked: can Gouge, Wrestle, or Punch."""
    def __init__(self, state: DuelState, client: discord.Client):
        super().__init__(timeout=900)
        self.state = state
        self.client = client

    @discord.ui.button(label="Gouge", style=discord.ButtonStyle.danger)
    async def btn_gouge(self, inter: discord.Interaction, btn: discord.ui.Button):
        """Only available to the victim being choked."""
        from .ai import maybe_ai_take_turn
        if not self._is_my_turn(inter): return
        choker, victim = self.state.choking or (None, None)
        me = self.state.current()
        if victim is None or me.user_id != victim:
            await safe_reply(inter, content="Gouge is only available while **you** are being choked.", ephemeral=True)
            return
        if random.random() <= 0.65:
            # Break choke + small counter damage
            self.state.choking = None
            foe = self.state.other()
            dmg = random.randint(2, 5)
            foe.hp = max(0, foe.hp - dmg)
            self.state.push(f"{me.name} **gouges** to break free, countering for **{dmg}**!")
            record_hit(self.state, me.user_id, foe.user_id, "gouge", "")
        else:
            self.state.push(f"{me.name} tries to **gouge** free but **fails**.")
        self.state.end_turn()
        await maybe_ai_take_turn(inter, self.state)
        await end_and_update(self.state, inter)

    @discord.ui.button(label="Wrestle", style=discord.ButtonStyle.primary)
    async def btn_wrestle(self, inter: discord.Interaction, btn: discord.ui.Button):
        from .ai import maybe_ai_take_turn
        if not self._is_my_turn(inter): return
        me = self.state.current(); foe = self.state.other()
        dmg = random.randint(1, 2)
        foe.hp = max(0, foe.hp - dmg)
        if random.random() < 0.5:
            self.state.positioning[me.user_id] = iclamp(self.state.positioning.get(me.user_id, 50) + 8, 0, 100)
            self.state.positioning[foe.user_id] = iclamp(self.state.positioning.get(foe.user_id, 50) - 8, 0, 100)
            swing = " Position improved."
        else:
            swing = ""
        self.state.push(f"{me.name} **wrestles** {foe.name} for **{dmg}**.{swing}")
        record_hit(self.state, me.user_id, foe.user_id, "wrestle", "")
        self.state.end_turn()
        await maybe_ai_take_turn(inter, self.state)
        await end_and_update(self.state, inter)

    @discord.ui.button(label="Punch", style=discord.ButtonStyle.secondary)
    async def btn_punch(self, inter: discord.Interaction, btn: discord.ui.Button):
        from .ai import maybe_ai_take_turn
        if not self._is_my_turn(inter): return
        me = self.state.current(); foe = self.state.other()
        dmg = random.randint(1, 4)
        foe.hp = max(0, foe.hp - dmg)
        self.state.push(f"{me.name} **punches** {foe.name} for **{dmg}**.")
        record_hit(self.state, me.user_id, foe.user_id, "punch", "Fists")
        self.state.end_turn()
        await maybe_ai_take_turn(inter, self.state)
        await end_and_update(self.state, inter)

    def _is_my_turn(self, inter: discord.Interaction) -> bool:
        if not self.state.active:
            asyncio.create_task(safe_reply(inter, content="Duel has ended.", ephemeral=True)); return False
        if inter.user.id != self.state.current().user_id:
            asyncio.create_task(safe_reply(inter, content="Not your turn.", ephemeral=True)); return False
        if not self.state.choking or self.state.choking[1] != inter.user.id:
            asyncio.create_task(safe_reply(inter, content="These options are only for a fighter **being choked**.", ephemeral=True)); return False
        return True

# ----- Finisher view -----

class FinalizeView(discord.ui.View):
    def __init__(self, state: DuelState, client: discord.Client, victor_id: int, target_id: int):
        super().__init__(timeout=900)
        self.state = state
        self.client = client
        self.victor_id = victor_id
        self.target_id = target_id

    def _is_victor(self, inter: discord.Interaction) -> bool:
        if not self.state.active:
            asyncio.create_task(safe_reply(inter, content="Duel has ended.", ephemeral=True)); return False
        if inter.user.id != self.victor_id:
            asyncio.create_task(safe_reply(inter, content="Only the victor can choose.", ephemeral=True)); return False
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
        await update_public_result(inter, self.state, f"{victor.name} spared {target.name}.")
        await hud_update_auto(inter, self.state, inter.user)

    @discord.ui.button(label="Beat", style=discord.ButtonStyle.danger)
    async def btn_beat(self, inter: discord.Interaction, btn: discord.ui.Button):
        if not self._is_victor(inter): return
        victor = self.state.a if self.state.a.user_id == self.victor_id else self.state.b
        target = self.state.a if self.state.a.user_id == self.target_id else self.state.b
        dmg = random.randint(1, 7)
        target.hp = max(0, target.hp - dmg)
        self.state.push(f"👊 {victor.name} **beats** the unconscious {target.name} for **{dmg}**.")
        record_hit(self.state, self.victor_id, self.target_id, "punch", "Fists")
        if target.hp <= 0:
            self.state.finisher = None
            self.state.active = False
            await update_public_result(inter, self.state, finish_summary(self.state))
        await hud_update_auto(inter, self.state, inter.user)

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
        await update_public_result(inter, self.state, f"{victor.name} kidnapped {target.name}.")
        await hud_update_auto(inter, self.state, inter.user)

    @discord.ui.button(label="Souvenir", style=discord.ButtonStyle.secondary, disabled=True)
    async def btn_souvenir(self, inter: discord.Interaction, btn: discord.ui.Button):
        await safe_reply(inter, content="Souvenir options coming soon.", ephemeral=True)

# ---------- Finisher helpers & end-of-duel ----------

async def maybe_offer_finisher(inter: discord.Interaction, state: DuelState) -> Optional[discord.ui.View]:
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

async def end_if_finished_or_offer(state: DuelState, inter: discord.Interaction):
    fin_view = await maybe_offer_finisher(inter, state)
    if fin_view is not None:
        await hud_update_with_view(inter, state, inter.user, fin_view)
        return

    if state.is_draw():
        state.finisher = None
        state.active = False
        state.push("Both fighters fall! It's a draw.")
        await update_public_result(inter, state, "It ends in a draw.")
    else:
        winner = state.winner()
        if winner is not None:
            state.finisher = None
            state.active = False
            summary = finish_summary(state)
            state.push(f"🏆 {winner.name} wins!")
            await update_public_result(inter, state, summary)
    await hud_update_auto(inter, state, inter.user)

async def end_and_update(state: DuelState, inter: discord.Interaction):
    await end_if_finished_or_offer(state, inter)

    # --- drop in to replace the existing make_view in src/bot/duel/views.py ---

def _compat_current(state: DuelState):
    # Support both legacy state.current() and new ds.turn_of
    if hasattr(state, "current") and callable(getattr(state, "current")):
        try:
            return state.current()  # zero-arg helper we attach in __init__.py
        except Exception:
            pass
    return state.a if getattr(state, "turn_of", 1) == 1 else state.b

def make_view(state: DuelState, client: discord.Client, viewer_id: int) -> discord.ui.View:
    """Pick the correct button set from the POV of `viewer_id` (compat-safe)."""
    if not getattr(state, "active", True):
        return DuelLogView(state)

    finisher = getattr(state, "finisher", None)
    if finisher:
        victor_id, target_id = finisher
        if viewer_id == victor_id:
            return FinalizeView(state, client, victor_id=victor_id, target_id=target_id)
        return DuelLogView(state)

    # Choke flow (optional in some state variants)
    choking = getattr(state, "choking", None)
    if choking:
        choker_id, _ = choking
        cur = _compat_current(state)
        if getattr(cur, "user_id", None) == choker_id and viewer_id == choker_id:
            return ChokeView(state, client)
        return DuelLogView(state)

    # Grapple flow (optional in some state variants)
    if getattr(state, "grappling", False):
        cur = _compat_current(state)
        if viewer_id == getattr(cur, "user_id", None):
            return GrappleView(state, client)
        return DuelLogView(state)

    # Default main view
    return DuelMainView(state, client)


# --- local helper for Block/Dodge logging without duplication ---
async def _apply_and_log(inter: discord.Interaction, state: DuelState, fn):
    """Call a small action resolver that returns a log string."""
    try:
        # resolver signature: (ds, idx) -> str
        idx = 1 if state.current() is state.a else 2
        return fn(state, idx)
    except Exception as e:
        log.warning("apply_and_log failed: %s", e)
        return "Action failed."
    
# FILE: src/bot/duel/views.py
# …(existing code)…

# --- Public exports / legacy alias ---
DuelView = DuelMainView  # keep older imports working

__all__ = [
    "DuelLogView", "DuelMainView", "GrappleView",
    "ChokeView", "ChokedVictimView", "FinalizeView",
    "DuelView",  # legacy name
    "make_view", "hud_update_auto", "safe_reply",
]
