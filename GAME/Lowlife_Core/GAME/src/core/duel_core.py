# FILE: src/core/duel_core.py
from __future__ import annotations

import math
import os
import random
import time
import logging
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Dict, List, Optional, Tuple, Set, Any

log = logging.getLogger("duel_core")

# ---------- external providers (optional) ----------
try:
    from src.core.inventory import get_equipped_mods, get_equipped_ids  # type: ignore
except Exception:
    def get_equipped_mods(_user_id: int) -> dict: return {}
    def get_equipped_ids(_user_id: int) -> dict: return {}

try:
    from src.core.items import get_item  # type: ignore
except Exception:
    def get_item(_iid: str): return None

try:
    from src.core.players import get_player_stats as _GET_STATS  # type: ignore
except Exception:
    _GET_STATS = None

try:
    # loadout-based weapon selection
    from src.core.combat_loadout import get_combatkit, pick_weapon_for_range  # type: ignore
except Exception:
    def get_combatkit(_gid: int, _uid: int) -> dict: return {"mods": {}}
    def pick_weapon_for_range(_range_state: str, _kit: dict): return (None, None)

# ---------- misc helpers ----------
def clamp(v: float, lo: float, hi: float) -> float: return max(lo, min(hi, v))
def iclamp(v: int, lo: int, hi: int) -> int: return max(lo, min(hi, v))

_ANIM_FRAMES_ENV = os.getenv("LOWLIFE_ANIM_FRAMES")
ANIM_FRAMES = [f.strip() for f in (_ANIM_FRAMES_ENV.split(",") if _ANIM_FRAMES_ENV else ["◐", "◓", "◑", "◒"]) if f.strip()]
_SPIN_IDX = -1
def next_fx_frame() -> str:
    global _SPIN_IDX
    if not ANIM_FRAMES: return "•"
    _SPIN_IDX = (_SPIN_IDX + 1) % len(ANIM_FRAMES)
    return ANIM_FRAMES[_SPIN_IDX]

# ---------------- range / grapple ----------------
class RangeGate(IntEnum):
    HANDS   = 0   # 1–3m (≈2m)
    CLOSE   = 1   # 4–10m (≈7m)
    MID     = 2   # 11–30m (≈20m)
    FAR     = 3   # 31–50m (≈40m)
    VERYFAR = 4   # >50m (≈65m)

RANGE_NAMES = {
    RangeGate.HANDS:  "Hands On",
    RangeGate.CLOSE:  "Close",
    RangeGate.MID:    "Mid",
    RangeGate.FAR:    "Far",
    RangeGate.VERYFAR:"Very Far",
}
RANGE_METERS: Dict[RangeGate, Tuple[float, float]] = {
    RangeGate.HANDS:  (1.0, 3.0),
    RangeGate.CLOSE:  (4.0, 10.0),
    RangeGate.MID:    (11.0, 30.0),
    RangeGate.FAR:    (31.0, 50.0),
    RangeGate.VERYFAR:(51.0, 999.0),
}
RANGE_ORDER: List[RangeGate] = [RangeGate.HANDS, RangeGate.CLOSE, RangeGate.MID, RangeGate.FAR, RangeGate.VERYFAR]

def _approx_m(rg: RangeGate) -> int:
    lo, hi = RANGE_METERS[rg]
    return int(round((lo + min(hi, lo+max(2.0,(hi-lo)))) / 2.0))

def range_label(rg: RangeGate) -> str:
    lo, hi = RANGE_METERS[rg]
    hi_txt = "50m+" if rg == RangeGate.VERYFAR else f"{int(hi)}m"
    return f"{RANGE_NAMES[rg]} {int(lo)}–{hi_txt} (≈{_approx_m(rg)}m)"

# ---------------- stats / items ----------------
def load_player_stats(user_id: int) -> Dict[str, float]:
    base = {
        "health":100.0,"blood":0.0,"cash":0.0,"net_worth":0.0,"weight":0.0,"capacity":20.0,
        "melee_dmg":10.0,"ranged_dmg":10.0,"combat":10.0,"fitness":10.0,
        "hit_bonus":0.0,"crit_bonus":0.0,"crit_mult_bonus":0.0,"armor":0.0,
    }
    if _GET_STATS:
        try:
            raw = _GET_STATS(user_id) or {}
            base["health"] = float(raw.get("health", raw.get("hp", base["health"]))); base["blood"] = float(raw.get("blood", base["blood"]))
            base["cash"] = float(raw.get("cash", base["cash"])); base["net_worth"] = float(raw.get("net_worth", raw.get("networth", base["net_worth"])) )
            base["weight"] = float(raw.get("weight", base["weight"])); base["capacity"] = float(raw.get("capacity", raw.get("inventory_capacity", base["capacity"])) )
            base["melee_dmg"] = float(raw.get("melee_dmg", base["melee_dmg"])); base["ranged_dmg"] = float(raw.get("ranged_dmg", base["ranged_dmg"]))
            base["combat"] = float(raw.get("combat", base["combat"])); base["fitness"] = float(raw.get("fitness", base["fitness"]))
        except Exception:
            log.exception("External stats provider failed")
    try:
        mods = get_equipped_mods(user_id) or {}
        for k in ("melee_dmg","ranged_dmg","combat","fitness","capacity","weight","hit_bonus","crit_bonus","crit_mult_bonus","armor"):
            base[k] = float(base.get(k, 0.0)) + float(mods.get(k, 0.0))
    except Exception:
        pass
    return base

def profile_score(user_id: int, hp_now: int) -> float:
    s = load_player_stats(user_id)
    return max(1.0, 0.30*(s["melee_dmg"]+s["ranged_dmg"]) + 0.25*s["combat"] + 0.20*s["fitness"] + 0.25*float(hp_now))

def odds_phrase(p_a: float, name_a: str, name_b: str) -> str:
    diff = abs(p_a - 0.5); fav = name_a if p_a >= 0.5 else name_b
    if diff < 0.02: return "Anyone's guess!"
    if diff < 0.08: return "It looks like it's going to be a close fight."
    if diff < 0.15: return f"Slight edge to {fav}."
    if diff < 0.25: return f"{fav} is favored."
    return "This should be a beatdown..."

# ==================== INVENTORY → COMBAT RESOLVER ====================
_RANGE_ACC_MOD = {"Close": +10, "Near": 0, "Mid": -10, "Far": -20, "Out-of-Range": -999}
def rg_to_loadout_range(rg: RangeGate) -> str:
    if rg in (RangeGate.HANDS, RangeGate.CLOSE): return "Close"
    if rg == RangeGate.MID: return "Mid"
    return "Far"

def compute_attack_numbers(guild_id: int, attacker_user_id: int, range_state: str):
    """
    Returns attack numbers derived from the attacker's equipped gear.
    If no viable weapon is found, fall back to an unarmed 'Fists' profile,
    usable only at our 'Close' loadout range (which covers HANDS/CLOSE gates).
    """
    kit = get_combatkit(guild_id, attacker_user_id)
    slot, wp = pick_weapon_for_range(range_state, kit)
    mods = kit.get("mods", {})

    if not wp:
        if range_state != "Close":
            return {
                "ready": False,
                "reason": "no_weapon_too_far",
                "message": (
                    f"No viable weapon at {range_state} range. You're unarmed — "
                    f"advance to **Close** to use **Fists**."
                ),
                "mods": mods,
            }
        from types import SimpleNamespace
        wp = SimpleNamespace(
            name="Fists",
            wclass="melee",
            base_accuracy=70,
            base_damage=6,
        )
        slot = "unarmed"

    acc = int(wp.base_accuracy) + int(mods.get("accuracy", 0)) + int(_RANGE_ACC_MOD.get(range_state, 0))
    acc = max(5, min(95, acc))

    dmg = int(wp.base_damage) + int(mods.get("damage", 0))
    dmg = max(1, dmg)

    return {"ready": True, "slot": slot, "weapon": wp, "accuracy": acc, "damage": dmg, "mods": mods}

def armor_kind_from_wclass(wcls: str) -> str:
    if wcls == "melee": return "melee"
    if wcls in ("pistol", "smg"): return "small_ranged"
    if wcls in ("shotgun", "rifle"): return "large_ranged"
    return "ranged"

# -------- inventory helpers (shared UI/engine) --------
def equipped_ids(user_id: int) -> Dict[str, str]:
    try: return get_equipped_ids(user_id) or {}
    except Exception: return {}

def item_name(iid: Optional[str]) -> str:
    if not iid: return "—"
    it = get_item(iid) if get_item else None
    return getattr(it, "name", iid) if it else iid

def slot_category(disarmed: Dict[int, Set[str]], user_id: int, slot: str) -> Optional[str]:
    if slot in disarmed.get(user_id, set()): return None
    eq = equipped_ids(user_id); iid = eq.get(slot)
    if not iid: return None
    it = get_item(iid) if get_item else None
    return getattr(it, "category", None) if it else None

def primary_reach(disarmed: Dict[int, Set[str]], user_id: int) -> float:
    if "primary" in disarmed.get(user_id, set()): return 0.0
    eq = equipped_ids(user_id); iid = eq.get("primary")
    if not iid: return 0.0
    it = get_item(iid) if get_item else None
    return float(getattr(it, "reach_m", 0.0)) if it else 0.0

# --------------- state ---------------
@dataclass
class Combatant:
    user_id: int
    name: str
    hp: int = 100
    is_ai: bool = False
    ai_medkit: bool = True

WEATHER_EMOJIS = ["☀️","⛅","🌧️","🌩️","🌫️","❄️","🌪️","🌦️"]

@dataclass
class DuelState:
    guild_id: int
    channel_id: int
    a: Combatant
    b: Combatant

    range_idx: int = RANGE_ORDER.index(RangeGate.MID)
    vis_segments: int = 26
    pos: Dict[int, int] = field(default_factory=dict)
    last_mover: Optional[int] = None

    turn_id: int = 0
    log_lines: List[str] = field(default_factory=list)
    full_log_lines: List[str] = field(default_factory=list)
    active: bool = True
    round_no: int = 1
    public_msg_id: Optional[int] = None
    last_update: float = field(default_factory=lambda: time.time())

    odds_phrase: str = ""
    initiative_note: str = ""
    revealed_secondary: Set[int] = field(default_factory=set)

    grappling: bool = False
    disarmed: Dict[int, Set[str]] = field(default_factory=dict)
    positioning: Dict[int, int] = field(default_factory=dict)

    # Choke/strangle system
    choking: Optional[Tuple[int,int]] = None
    breath: Dict[int,int] = field(default_factory=dict)
    bloodflow: Dict[int,int] = field(default_factory=dict)
    unconscious: Set[int] = field(default_factory=set)   # ← NEW

    clearing_stacks: Dict[int, int] = field(default_factory=dict)
    clearing_attacks_left: Dict[int, int] = field(default_factory=dict)
    clearing_expiries: Dict[int, List[int]] = field(default_factory=dict)
    turn_tick: int = 0

    hidden: Set[int] = field(default_factory=set)
    in_cover: Set[int] = field(default_factory=set)
    cover_pct: Dict[int, int] = field(default_factory=dict)

    grenades_pending: Dict[int, Dict[str, int]] = field(default_factory=dict)
    moved_since_grenade: Set[int] = field(default_factory=set)

    skip_turn_for: Set[int] = field(default_factory=set)
    last_action: Dict[int, str] = field(default_factory=dict)

    weather: str = field(default_factory=lambda: random.choice(WEATHER_EMOJIS))
    last_hit: Dict[int, Dict[str, Any]] = field(default_factory=dict)

    # grapple bookkeeping
    grapple_just_started: bool = False
    grapple_starter_id: Optional[int] = None
    grapple_flip: int = 0

    def __post_init__(self):
        if not self.pos:
            d = self._target_vis_gap()
            left = max(0, (self.vis_segments - d) // 2 - 1)
            self.pos[self.a.user_id] = left
            self.pos[self.b.user_id] = min(self.vis_segments-1, left + d)
        self.positioning[self.a.user_id] = 50
        self.positioning[self.b.user_id] = 50

    # ---- small utilities ----
    def touch(self): self.last_update = time.time()
    def rngate(self) -> RangeGate: return RANGE_ORDER[self.range_idx]
    def players(self) -> Tuple[Combatant, Combatant]: return (self.a, self.b)
    def current(self) -> Combatant: return self.a if self.turn_id == 0 else self.b
    def other(self) -> Combatant: return self.b if self.turn_id == 0 else self.a
    def is_participant(self, uid: int) -> bool: return uid in (self.a.user_id, self.b.user_id)

    def is_draw(self) -> bool:
        a_dead = self.a.hp <= 0 or self.a.user_id in self.unconscious
        b_dead = self.b.hp <= 0 or self.b.user_id in self.unconscious
        return a_dead and b_dead

    def winner(self) -> Optional[Combatant]:
        # HP defeat
        if self.a.hp <= 0 and self.b.hp > 0: return self.b
        if self.b.hp <= 0 and self.a.hp > 0: return self.a
        # Consciousness defeat
        if self.a.user_id in self.unconscious and self.b.user_id not in self.unconscious: return self.b
        if self.b.user_id in self.unconscious and self.a.user_id not in self.unconscious: return self.a
        return None

    def push(self, line: str):
        msg = f"{next_fx_frame()} {line}"
        self.full_log_lines.append(msg)
        self.log_lines.append(msg)
        if len(self.log_lines) > 6: self.log_lines = self.log_lines[-6:]
        self.touch()

    def add_raw(self, line: str):
        self.full_log_lines.append(line)
        self.log_lines.append(line)
        if len(self.log_lines) > 6: self.log_lines = self.log_lines[-6:]
        self.touch()

    def replace_last(self, line: str):
        if self.log_lines: self.log_lines[-1] = line
        else: self.log_lines.append(line)
        if self.full_log_lines:
            self.full_log_lines[-1] = line
        else:
            self.full_log_lines.append(line)
        self.touch()

    # ----- distance helpers -----
    def _target_vis_gap(self) -> int:
        idx_ratio = self.range_idx / (len(RANGE_ORDER) - 1)
        return iclamp(int(round(idx_ratio * (self.vis_segments - 1))), 3, self.vis_segments - 3)

    def _sync_visual_positions(self, mover_id: Optional[int] = None):
        if self.grappling: return
        a_id, b_id = self.a.user_id, self.b.user_id
        target_gap = self._target_vis_gap()
        pos_a, pos_b = self.pos.get(a_id, 1), self.pos.get(b_id, self.vis_segments-2)
        if pos_a >= pos_b: pos_a = max(0, pos_b - 2)
        cur_gap = abs(pos_b - pos_a)
        if cur_gap == target_gap:
            self.pos[a_id], self.pos[b_id] = pos_a, pos_b; return

        if mover_id == a_id:
            pos_a = iclamp(pos_b - target_gap, 0, self.vis_segments-1)
        elif mover_id == b_id:
            pos_b = iclamp(pos_a + target_gap, 0, self.vis_segments-1)
        else:
            left = max(0, (self.vis_segments - target_gap) // 2 - 1)
            pos_a = left; pos_b = iclamp(left + target_gap, 0, self.vis_segments-1)

        if pos_a >= pos_b: pos_a = max(0, pos_b - 1)
        self.pos[a_id], self.pos[b_id] = pos_a, pos_b

    def step_range(self, delta: int, actor_id: Optional[int] = None):
        prev = self.rngate()
        self.range_idx = iclamp(self.range_idx + delta, 0, len(RANGE_ORDER)-1)
        self.last_mover = actor_id
        self._sync_visual_positions(mover_id=actor_id)
        self.touch()
        self._check_grapple_transition(prev, self.rngate(), actor_id)

    # ---- micro movement ----
    def micro_move(self, actor_id: int, toward_steps: int):
        if self.grappling:
            return

        a_id, b_id = self.a.user_id, self.b.user_id
        pos_a = self.pos.get(a_id, 1)
        pos_b = self.pos.get(b_id, self.vis_segments-2)

        if actor_id not in (a_id, b_id):
            return

        me_left = (pos_a < pos_b and actor_id == a_id) or (pos_b < pos_a and actor_id == b_id)
        me_pos = pos_a if actor_id == a_id else pos_b
        them_pos = pos_b if actor_id == a_id else pos_a

        if toward_steps >= 0:
            if me_left:
                me_pos = min(them_pos - 1, me_pos + toward_steps)
            else:
                me_pos = max(them_pos + 1, me_pos - toward_steps)
        else:
            steps = abs(toward_steps)
            if me_left:
                me_pos = max(0, me_pos - steps)
            else:
                me_pos = min(self.vis_segments - 1, me_pos + steps)

        if me_left:
            me_pos = min(me_pos, them_pos - 1)
        else:
            me_pos = max(me_pos, them_pos + 1)

        if actor_id == a_id:
            pos_a = me_pos
        else:
            pos_b = me_pos

        self.pos[a_id], self.pos[b_id] = pos_a, pos_b

        gap = abs(pos_b - pos_a)
        ratio = gap / max(1, (self.vis_segments - 1))
        new_idx = iclamp(int(round(ratio * (len(RANGE_ORDER) - 1))), 0, len(RANGE_ORDER) - 1)
        prev = self.rngate()
        self.range_idx = new_idx
        self.touch()
        self._check_grapple_transition(prev, self.rngate(), actor_id)

    # ---- Grapple helpers ----
    def can_grapple(self) -> bool:
        return (not self.grappling) and (self.rngate() == RangeGate.HANDS)

    def begin_grapple(self, starter_id: int):
        if not self.can_grapple():
            return
        self.grappling = True
        self.grapple_just_started = True
        self.grapple_starter_id = starter_id
        self.grapple_flip = 0
        d = 2
        left = max(0, (self.vis_segments - d) // 2 - 1)
        self.pos[self.a.user_id] = left
        self.pos[self.b.user_id] = min(self.vis_segments-1, left + d)
        self.turn_id = 0 if starter_id == self.a.user_id else 1
        self.add_raw("🤼 Grappling engaged!")

    # ----- end-turn / status ticks -----
    def _expire_clearing(self):
        for uid in (self.a.user_id, self.b.user_id):
            exps = self.clearing_expiries.get(uid, [])
            if not exps: continue
            kept = [t for t in exps if t > self.turn_tick]
            removed = len(exps) - len(kept)
            if removed > 0:
                self.clearing_stacks[uid] = max(0, int(self.clearing_stacks.get(uid, 0)) - removed)
            if kept:
                self.clearing_expiries[uid] = kept
            else:
                self.clearing_expiries.pop(uid, None)
                if self.clearing_stacks.get(uid, 0) == 0:
                    self.clearing_stacks.pop(uid, None)

    def _apply_choke_tick(self):
        """Apply ongoing choke effects between turns without reducing HP."""
        if not self.choking: return
        choker, target = self.choking
        self.breath[target]    = iclamp(self.breath.get(target, 50) - random.randint(6,10), 0, 100)
        self.bloodflow[target] = iclamp(self.bloodflow.get(target, 50) - random.randint(3,7), 0, 100)
        if self.breath[target] <= 0 or self.bloodflow[target] <= 0:
            # Mark target unconscious; do NOT change HP
            self.unconscious.add(target)
            loser = self.a if self.a.user_id == target else self.b
            self.last_hit[target] = {"by": choker, "type": "strangled", "weapon": ""}
            self.add_raw(f"😵‍💫 {loser.name} passes out from the choke!")

    def end_turn(self):
        self.turn_id ^= 1
        if self.turn_id == 0: self.round_no += 1
        self.turn_tick += 1
        if self.grappling:
            self.grapple_flip ^= 1
        cur = self.current()
        if cur.user_id in self.skip_turn_for:
            self.skip_turn_for.discard(cur.user_id)
            self.add_raw(f"😵 {cur.name} is staggered and loses a turn.")
            self.turn_id ^= 1
            if self.turn_id == 0: self.round_no += 1
            self.turn_tick += 1
        self._apply_choke_tick()
        self._expire_clearing()
        self.touch()

    def _check_grapple_transition(self, prev: RangeGate, now: RangeGate, actor_id: Optional[int]):
        # break grapple if distance leaves HANDS
        was = self.grappling
        if was and (now != RangeGate.HANDS):
            self.add_raw("🧷 Grappling broken. Combat resumes.")
            self.grappling = False
            self.grapple_just_started = False
            self.grapple_starter_id = None
        if not self.grappling and self.choking:
            self.add_raw("🫁 Choke is released as distance opens.")
            self.choking = None
            self.breath.clear(); self.bloodflow.clear()

# ---- accuracy / damage helpers ----
_ARMOR_DISPLAY_MAX = 20.0
_ARMOR_FACTORS = {"melee": 0.60, "small_ranged": 0.80, "large_ranged": 0.80, "ranged": 0.80, "grenade": 0.50, "none": 0.0}

def apply_armor_reduction(state: DuelState, defender_id: int, dfn: Dict[str,float], dmg: int, kind: str) -> Tuple[int,int]:
    factor = _ARMOR_FACTORS.get(kind, 0.70)
    raw = int(round(float(dfn.get("armor", 0.0)) * factor))
    mit = iclamp(raw, 0, max(0, dmg-1))
    return dmg - mit, mit

def crit_params(atk: Dict[str,float]) -> Tuple[float,float]:
    chance = clamp(0.10 + 0.005*(atk["combat"]-10.0) + float(atk.get("crit_bonus",0.0)), 0.05, 0.40)
    mult   = clamp(1.50 + 0.005*atk["combat"] + float(atk.get("crit_mult_bonus",0.0)), 1.50, 2.25)
    return chance, mult

def record_hit(state: DuelState, attacker_id: int, target_id: int, kind: str, weapon: str = ""):
    state.last_hit[target_id] = {"by": attacker_id, "type": kind, "weapon": weapon}
