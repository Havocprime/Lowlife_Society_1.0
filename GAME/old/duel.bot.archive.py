# src/bot/commands/duel.py
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional

import discord
from discord import app_commands, Interaction, Member  # import types directly

from src.core.debug import get_logger, slash_try

log = get_logger("duel")

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
DB_COMBATS = DATA_DIR / "combats.json"
DB_PLAYERS = DATA_DIR / "players.json"

RANGES = ["Close", "Near", "Mid", "Far", "OutOfRange"]
COLOR_LIVE = 0x2ecc71   # green
COLOR_ENDED = 0xe74c3c  # red
MAX_HP_DEFAULT = 50     # until rules wire-in

# -------------------- tiny DB helpers --------------------
def _load_combats() -> Dict[str, Any]:
    if DB_COMBATS.exists():
        try:
            return json.loads(DB_COMBATS.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}

def _save_combats(db: Dict[str, Any]) -> None:
    DB_COMBATS.write_text(json.dumps(db, indent=2), encoding="utf-8")

def _load_players() -> Dict[str, Any]:
    if DB_PLAYERS.exists():
        try:
            return json.loads(DB_PLAYERS.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}

def _key(guild_id: Optional[int]) -> str:  # one duel per guild (prototype)
    return str(guild_id or 0)

# -------------------- labels & HUD (ephemeral) --------------------
async def _user_label(inter: Interaction, user_id: int) -> str:
    if inter.guild:
        m = inter.guild.get_member(user_id)
        if m:
            return m.display_name or m.name
    u = inter.client.get_user(user_id)
    if u:
        return getattr(u, "display_name", None) or getattr(u, "global_name", None) or u.name
    try:
        u = await inter.client.fetch_user(user_id)
        return getattr(u, "display_name", None) or getattr(u, "global_name", None) or u.name
    except Exception:
        return f"<@{user_id}>"

def _defaults_for_user(uid: str) -> Dict[str, Any]:
    return {
        "alias": f"User {uid}",
        "cash": 0,
        "net_worth": 0,
        "level": 1,
        "equipped": "Fists",
        "weight": 0.0,
        "capacity": 30.0,
        "blood": 0,
    }

def _player_snapshot(uid: int) -> Dict[str, Any]:
    db = _load_players()
    row = db.get(str(uid), {})
    snap = _defaults_for_user(str(uid))
    snap.update({
        "alias": row.get("alias", snap["alias"]),
        "cash": row.get("cash", 0),
        "net_worth": row.get("net_worth", 0),
        "level": row.get("level", 1),
        "equipped": row.get("equipped", "Fists"),
        "weight": row.get("weight", 0.0),
        "capacity": row.get("capacity", 30.0),
        "blood": row.get("blood", 0),
    })
    return snap

def _hp_for_user_in_duel(uid: int, d: Optional[Dict[str, Any]]) -> int:
    if not d or "hp" not in d:
        return MAX_HP_DEFAULT
    return int(d["hp"]["attacker" if uid == d.get("attacker_id") else "defender"])

def _hud_line_for_user(uid: int, d: Optional[Dict[str, Any]]) -> str:
    p = _player_snapshot(uid)
    hp = _hp_for_user_in_duel(uid, d)
    return (
        f"**{p['alias']}**  "
        f"♥ {hp}/{MAX_HP_DEFAULT}  |  "
        f"🩸 {p['blood']}  |  "
        f"💵 ${p['cash']:,}  |  "
        f"📈 ${p['net_worth']:,}  |  "
        f"🧬 L{p['level']}  |  "
        f"🧰 {p['equipped']}  |  "
        f"⚖️ {p['weight']}/{p['capacity']}"
    )

async def _send_hud_ephemeral(inter: Interaction, uid: int, d: Optional[Dict[str, Any]]) -> None:
    await inter.followup.send(
        _hud_line_for_user(uid, d),
        ephemeral=True,
        allowed_mentions=discord.AllowedMentions.none(),
    )

# -------------------- public tracker (no private HUD inside) --------------------
def _build_tracker_embed(
    attacker_label: str,
    defender_label: str,
    rng: str,
    rnd: int,
    *,
    live: bool = True,
    last_action: Optional[str] = None,
) -> discord.Embed:
    color = COLOR_LIVE if live else COLOR_ENDED
    desc = f"**Range:** {rng} • **Round:** {rnd}" + ("" if live else "\n**Status:** Ended")
    emb = discord.Embed(title=f"⚔️ {attacker_label} vs {defender_label}", description=desc, color=color)
    if last_action:
        emb.add_field(name="Last action", value=last_action, inline=False)
    return emb

# -------------------- message helpers --------------------
async def _fetch_message(client: discord.Client, channel_id: int, message_id: int) -> Optional[discord.Message]:
    ch = client.get_channel(channel_id)
    try:
        if ch is None:
            ch = await client.fetch_channel(channel_id)
        return await ch.fetch_message(message_id)
    except Exception:
        return None

async def _delete_msg(msg: Optional[discord.Message]) -> None:
    try:
        if msg:
            await msg.delete()
    except Exception:
        pass

def _mentions_only(uid: int) -> discord.AllowedMentions:
    return discord.AllowedMentions(users=[discord.Object(id=uid)], roles=False, everyone=False)

async def _replace_tracker(
    inter: Interaction,
    combats: Dict[str, Any],
    d: Dict[str, Any],
    tracker_embed: discord.Embed,
    *,
    allowed_mentions: Optional[discord.AllowedMentions] = None,
) -> None:
    old = await _fetch_message(inter.client, d.get("channel_id") or 0, d.get("message_id") or 0)
    await _delete_msg(old)
    new_msg = await inter.channel.send(embed=tracker_embed, allowed_mentions=allowed_mentions)
    d["channel_id"], d["message_id"] = new_msg.channel.id, new_msg.id
    _save_combats(combats)

# -------------------- command registration --------------------
def register(tree: app_commands.CommandTree) -> None:
    @tree.command(name="duel", description="Start a duel at Mid range.")
    @slash_try
    async def duel(inter: Interaction, target: Member):
        if target.id == inter.user.id:
            await inter.response.send_message("You can’t duel yourself.", ephemeral=True)
            return

        combats = _load_combats()
        k = _key(inter.guild_id)
        existing = combats.get(k)
        if existing and existing.get("live", True):
            await inter.response.send_message("A duel is already active here. Use **/end_duel** first.", ephemeral=True)
            return

        await inter.response.defer(ephemeral=True)

        combats[k] = {
            "attacker_id": inter.user.id,
            "defender_id": target.id,
            "range": "Mid",
            "round": 1,
            "started_at": time.time(),
            "channel_id": None,
            "message_id": None,
            "live": True,
            "hp": {"attacker": MAX_HP_DEFAULT, "defender": MAX_HP_DEFAULT},
        }
        log.info("Duel start (guild=%s): attacker=%s defender=%s", inter.guild_id, inter.user.id, target.id)

        a_lbl = await _user_label(inter, combats[k]["attacker_id"])
        d_lbl = await _user_label(inter, combats[k]["defender_id"])
        tracker = _build_tracker_embed(a_lbl, d_lbl, "Mid", 1, live=True, last_action="Duel started.")
        await _replace_tracker(inter, combats, combats[k], tracker)
        await _send_hud_ephemeral(inter, inter.user.id, combats[k])

    @tree.command(name="hud", description="Show your personal HUD line.")
    @slash_try
    async def hud(inter: Interaction):
        combats = _load_combats()
        k = _key(inter.guild_id)
        d = combats.get(k)
        await inter.response.send_message(
            _hud_line_for_user(inter.user.id, d),
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @tree.command(name="range", description="Show the current duel range.")
    @slash_try
    async def show_range(inter: Interaction):
        combats = _load_combats()
        k = _key(inter.guild_id)
        if k not in combats:
            await inter.response.send_message("No active duel. Use **/duel** first.", ephemeral=True)
            return
        d = combats[k]
        await inter.response.send_message(
            f"📏 Range is **{d['range']}** (Round {d['round']}). "
            f"<@{d['attacker_id']}> vs <@{d['defender_id']}>."
        )

    @tree.command(name="advance", description="Move one range closer (e.g., Mid → Near).")
    @slash_try
    async def advance(inter: Interaction):
        combats = _load_combats()
        k = _key(inter.guild_id)
        if k not in combats:
            await inter.response.send_message("No active duel. Use **/duel** first.", ephemeral=True)
            return
        d = combats[k]
        if not d.get("live", True):
            await inter.response.send_message("This duel has ended.", ephemeral=True)
            return

        await inter.response.defer(ephemeral=True)

        cur = d["range"]
        idx = max(0, RANGES.index(cur) - 1)
        new = RANGES[idx]
        if new == cur:
            await inter.followup.send("You’re already at **Close**.", ephemeral=True)
            return

        d["range"] = new
        d["round"] += 1
        _save_combats(combats)
        log.info("Advance (guild=%s user=%s): %s -> %s round=%s", inter.guild_id, inter.user.id, cur, new, d["round"])

        a_lbl = await _user_label(inter, d["attacker_id"])
        b_lbl = await _user_label(inter, d["defender_id"])
        actor_lbl = await _user_label(inter, inter.user.id)
        last = f"**{actor_lbl}** advanced: **{cur} → {new}**"
        tracker = _build_tracker_embed(a_lbl, b_lbl, d["range"], d["round"], live=True, last_action=last)
        await _replace_tracker(inter, combats, d, tracker)
        await _send_hud_ephemeral(inter, inter.user.id, d)

    @tree.command(name="retreat", description="Move one range away. Notifies your opponent.")
    @slash_try
    async def retreat(inter: Interaction):
        combats = _load_combats()
        k = _key(inter.guild_id)
        if k not in combats:
            await inter.response.send_message("No active duel. Use **/duel** first.", ephemeral=True)
            return
        d = combats[k]
        if not d.get("live", True):
            await inter.response.send_message("This duel has ended.", ephemeral=True)
            return

        await inter.response.defer(ephemeral=True)

        cur = d["range"]
        idx = min(len(RANGES) - 1, RANGES.index(cur) + 1)
        new = RANGES[idx]
        if new == cur:
            await inter.followup.send("You’re already at **OutOfRange**.", ephemeral=True)
            return

        d["range"] = new
        d["round"] += 1
        _save_combats(combats)
        log.info("Retreat (guild=%s user=%s): %s -> %s round=%s", inter.guild_id, inter.user.id, cur, new, d["round"])

        a_lbl = await _user_label(inter, d["attacker_id"])
        b_lbl = await _user_label(inter, d["defender_id"])
        actor_lbl = await _user_label(inter, inter.user.id)
        opponent_id = d["defender_id"] if inter.user.id == d["attacker_id"] else d["attacker_id"]
        last = f"**{actor_lbl}** retreated: **{cur} → {new}**  |  <@{opponent_id}> your opponent moved."
        tracker = _build_tracker_embed(a_lbl, b_lbl, d["range"], d["round"], live=True, last_action=last)
        await _replace_tracker(inter, combats, d, tracker, allowed_mentions=_mentions_only(opponent_id))
        await _send_hud_ephemeral(inter, inter.user.id, d)

    @tree.command(name="end_duel", description="End the current duel in this server.")
    @slash_try
    async def end_duel(inter: Interaction):
        combats = _load_combats()
        k = _key(inter.guild_id)
        if k not in combats:
            await inter.response.send_message("No active duel.", ephemeral=True)
            return

        await inter.response.defer(ephemeral=True)
        d = combats[k]
        d["live"] = False
        _save_combats(combats)
        log.info("End duel (guild=%s) by user=%s", inter.guild_id, inter.user.id)

        a_lbl = await _user_label(inter, d["attacker_id"])
        b_lbl = await _user_label(inter, d["defender_id"])
        tracker = _build_tracker_embed(a_lbl, b_lbl, d["range"], d["round"], live=False, last_action="Duel ended.")
        await _replace_tracker(inter, combats, d, tracker)

        combats.pop(k, None)
        _save_combats(combats)
        await inter.followup.send("✅ Duel ended. State cleared.", ephemeral=True)
        await _send_hud_ephemeral(inter, inter.user.id, None)

    @tree.command(name="reset_duel", description="Force clear duel state for this server.")
    @slash_try
    async def reset_duel(inter: Interaction):
        combats = _load_combats()
        k = _key(inter.guild_id)
        if k in combats:
            d = combats[k]
            try:
                msg = await _fetch_message(inter.client, d.get("channel_id") or 0, d.get("message_id") or 0)
                await _delete_msg(msg)
            except Exception:
                pass
            combats.pop(k, None)
            _save_combats(combats)
            await inter.response.send_message("🧹 Cleared duel state.", ephemeral=True)
        else:
            await inter.response.send_message("No duel state found.", ephemeral=True)

    log.info("Registered duel commands")


