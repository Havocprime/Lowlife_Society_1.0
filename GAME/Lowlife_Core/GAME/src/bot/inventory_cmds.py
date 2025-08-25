# FILE: src/bot/inventory_cmds.py
from __future__ import annotations
import logging
from typing import Dict, Any, List, Tuple

import discord
from discord import app_commands

from src.core.inventory import (
    ensure_player, grant_item, generate_item, equip_item, unequip_slot,
    total_weight, is_overweight, get_equipped_mods, current_capacity,
    use_consumable, transfer_item
)
from src.core.items import list_templates
from src.core.combat_loadout import get_combatkit, set_preferred_slot

log = logging.getLogger("inv_cmds")

TIER_ORDER = {"common":0,"uncommon":1,"rare":2,"epic":3}

# ---------- helpers ----------
def _fmt_item(it: Dict[str, Any]) -> str:
    mods = it.get("mods", {})
    mods_str = ", ".join(f"{k}+{v}" for k, v in mods.items() if v)
    mods_str = f" [{mods_str}]" if mods_str else ""
    return f"`{it['inst_id']}` • **{it['name']}** ({it['type']}) • {it['weight']}kg • {it['tier']}{mods_str}"

def _sort_items(items: List[Dict[str, Any]], sort: str) -> List[Dict[str, Any]]:
    if sort == "name":
        return sorted(items, key=lambda x: x.get("name","").lower())
    if sort == "type":
        return sorted(items, key=lambda x: (x.get("type",""), x.get("name","").lower()))
    if sort == "tier":
        return sorted(items, key=lambda x: (TIER_ORDER.get(x.get("tier","common"), 0), x.get("name","").lower()))
    if sort == "weight":
        return sorted(items, key=lambda x: float(x.get("weight", 0)))
    return items

def _player_embed(user: discord.abc.User, state: Dict[str, Any], *, page: int = 1, sort: str = "type") -> discord.Embed:
    PAGE = 10
    items = _sort_items(list(state["inventory"]), sort)
    start = (page-1) * PAGE
    end = start + PAGE
    slice_ = items[start:end]
    total_pages = max(1, (len(items) + PAGE - 1)//PAGE)

    e = discord.Embed(title=f"{user.display_name} — Inventory", color=0x00A99D)
    if slice_:
        e.add_field(name=f"Items (page {page}/{total_pages}, sort={sort})",
                    value="\n".join(_fmt_item(it) for it in slice_)[:1024], inline=False)
    else:
        e.add_field(name=f"Items (page {page}/{total_pages}, sort={sort})", value="*(empty page)*", inline=False)

    eq = state["equipment"]
    eq_lines = []
    for slot in ["primary","secondary","armor","accessory"]:
        iid = eq.get(slot)
        if not iid:
            eq_lines.append(f"**{slot.title()}**: *(empty)*")
        else:
            it = next((x for x in state["inventory"] if x["inst_id"] == iid), None)
            eq_lines.append(f"**{slot.title()}**: {it['name']} `{iid}`" if it else f"**{slot.title()}**: *(missing ref)*")
    e.add_field(name="Equipped", value="\n".join(eq_lines), inline=False)

    tw = total_weight(state)
    cap = current_capacity(state)
    footer = f"Weight: {tw}/{cap} kg"
    if tw > cap:
        footer += " (OVERWEIGHT)"
    e.set_footer(text=footer)
    return e

# ---------- slash commands ----------
@app_commands.command(name="inventory", description="Show your inventory and equipment.")
@app_commands.describe(page="Page number (10 items per page)", sort="Sort by: name|type|tier|weight")
async def inventory_cmd(interaction: discord.Interaction, page: int = 1, sort: str = "type"):
    sort = (sort or "type").lower()
    if sort not in ("name","type","tier","weight"):
        sort = "type"
    if page < 1:
        page = 1
    state = ensure_player(interaction.guild_id, interaction.user.id)
    await interaction.response.send_message(embed=_player_embed(interaction.user, state, page=page, sort=sort), ephemeral=True)

@app_commands.command(name="giveitem", description="[Admin] Give yourself a base templated item.")
@app_commands.describe(def_id="One of the known template ids", tier="common/uncommon/rare/epic")
async def giveitem_cmd(interaction: discord.Interaction, def_id: str, tier: str = "common"):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("You need **Manage Server** to use this.", ephemeral=True)
        return
    if def_id not in list_templates():
        await interaction.response.send_message(f"Unknown def_id. Try: {', '.join(list_templates())}", ephemeral=True)
        return
    state = ensure_player(interaction.guild_id, interaction.user.id)
    item = generate_item(def_id, tier=tier)
    grant_item(state, item)
    await interaction.response.send_message(
        f"Gave you: **{item['name']}** `{item['inst_id']}` ({item['tier']}, {item['weight']}kg)",
        ephemeral=True
    )

@app_commands.command(name="genitem", description="Proc-generate a new item from a template and tier.")
@app_commands.describe(def_id="Template id", tier="common/uncommon/rare/epic")
async def genitem_cmd(interaction: discord.Interaction, def_id: str, tier: str = "common"):
    if def_id not in list_templates():
        await interaction.response.send_message(f"Unknown def_id. Try: {', '.join(list_templates())}", ephemeral=True)
        return
    state = ensure_player(interaction.guild_id, interaction.user.id)
    item = generate_item(def_id, tier=tier)
    grant_item(state, item)
    await interaction.response.send_message(
        f"Generated: **{item['name']}** `{item['inst_id']}` ({item['tier']}, {item['weight']}kg)",
        ephemeral=True
    )

@app_commands.command(name="equip", description="Equip an item by its instance id (shown in /inventory).")
@app_commands.describe(inst_id="The item's instance id (e.g., a1b2c3d4e5)", slot="Optional slot override")
async def equip_cmd(interaction: discord.Interaction, inst_id: str, slot: str | None = None):
    state = ensure_player(interaction.guild_id, interaction.user.id)
    ok, msg = equip_item(state, inst_id, slot=slot)
    await interaction.response.send_message(msg, ephemeral=True)

@app_commands.command(name="unequip", description="Unequip a slot.")
@app_commands.describe(slot="primary/secondary/armor/accessory")
async def unequip_cmd(interaction: discord.Interaction, slot: str):
    state = ensure_player(interaction.guild_id, interaction.user.id)
    ok, msg = unequip_slot(state, slot)
    await interaction.response.send_message(msg, ephemeral=True)

@app_commands.command(name="mystats", description="Show aggregated modifiers from your equipped items.")
async def mystats_cmd(interaction: discord.Interaction):
    state = ensure_player(interaction.guild_id, interaction.user.id)
    mods = get_equipped_mods(state)
    if not mods:
        await interaction.response.send_message("No equipped modifiers yet.", ephemeral=True)
        return
    lines = [f"- **{k}**: +{v}" for k, v in mods.items() if v]
    await interaction.response.send_message("\n".join(lines), ephemeral=True)

@app_commands.command(name="useitem", description="Use a consumable from your inventory.")
@app_commands.describe(inst_id="The item's instance id")
async def useitem_cmd(interaction: discord.Interaction, inst_id: str):
    state = ensure_player(interaction.guild_id, interaction.user.id)
    ok, msg = use_consumable(state, inst_id)
    await interaction.response.send_message(("✅ " if ok else "❌ ") + msg, ephemeral=True)

@app_commands.command(name="transfer", description="Give an item to another player.")
@app_commands.describe(user="The recipient", inst_id="The item's instance id (must be unequipped)")
async def transfer_cmd(interaction: discord.Interaction, user: discord.Member, inst_id: str):
    if user.bot:
        await interaction.response.send_message("Bots can’t receive items.", ephemeral=True)
        return
    sender = ensure_player(interaction.guild_id, interaction.user.id)
    recipient = ensure_player(interaction.guild_id, user.id)
    ok, msg = transfer_item(sender, recipient, inst_id)
    await interaction.response.send_message(("✅ " if ok else "❌ ") + msg, ephemeral=True)

@app_commands.command(name="loadout", description="Show the weapons combat will use from your inventory.")
async def loadout_cmd(interaction: discord.Interaction):
    kit = get_combatkit(interaction.guild_id, interaction.user.id)
    def line(wp):
        if not wp: return "—"
        return f"**{wp.name}** ({wp.wclass}) • ranges: {', '.join(wp.ranges)} • acc {wp.base_accuracy}% • dmg {wp.base_damage}"
    msg = (
        f"Preferred: **{kit.get('preferred_slot','primary')}**\n"
        f"Primary:  {line(kit['primary'])}\n"
        f"Secondary:{line(kit['secondary'])}\n"
        f"Mods: " + (", ".join(f"{k}+{v}" for k,v in kit['mods'].items()) or "—")
    )
    await interaction.response.send_message(msg, ephemeral=True)

@app_commands.command(name="setweapon", description="Choose your preferred weapon slot for combat (auto-switch if invalid for range).")
@app_commands.describe(slot="primary or secondary")
async def setweapon_cmd(interaction: discord.Interaction, slot: str):
    slot = slot.lower()
    if slot not in ("primary","secondary"):
        await interaction.response.send_message("Use `primary` or `secondary`.", ephemeral=True); return
    set_preferred_slot(interaction.guild_id, interaction.user.id, slot)
    await interaction.response.send_message(f"Preferred weapon slot set to **{slot}**.", ephemeral=True)

# ---------- registrar (version-safe) ----------
def _safe_remove(tree: app_commands.CommandTree, name: str) -> None:
    existing = None
    try:
        existing = tree.get_command(name)  # positional name for older d.py
    except Exception:
        existing = None
    if existing is None:
        try:
            for cmd in list(tree.get_commands()):
                if getattr(cmd, "name", None) == name:
                    existing = cmd; break
        except Exception:
            existing = None
    if existing is not None:
        try:
            tree.remove_command(existing.name, type=existing.type); return
        except Exception:
            pass
        try:
            tree.remove_command(existing.name)
        except Exception:
            pass

def register_inventory_commands(tree: app_commands.CommandTree, bot=None):
    for name in ("inventory","giveitem","genitem","equip","unequip","mystats","useitem","transfer","loadout","setweapon"):
        _safe_remove(tree, name)
    tree.add_command(inventory_cmd)
    tree.add_command(giveitem_cmd)
    tree.add_command(genitem_cmd)
    tree.add_command(equip_cmd)
    tree.add_command(unequip_cmd)
    tree.add_command(mystats_cmd)
    tree.add_command(useitem_cmd)
    tree.add_command(transfer_cmd)
    tree.add_command(loadout_cmd)
    tree.add_command(setweapon_cmd)
    log.info("Inventory slash commands registered: %s", [c.name for c in tree.get_commands()])
