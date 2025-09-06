# GAME/src/cogs/inventory.py
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from src.models.item import Item, ItemClass
from src.inventory.manager import (
    list_item_names,
    list_item_name_status,
    get_item_by_name,
    create_item,
    update_item,
    grant_item,
    inventory_for_user,
    set_equipped,
    catalog_items,
    soft_delete_item_by_name,
)

log = logging.getLogger("inventory.cog")

# ---------------------------------------------------------------------
# Choice helpers / registries
# ---------------------------------------------------------------------

def _enum_choices(enum_cls) -> list[app_commands.Choice[str]]:
    try:
        return [app_commands.Choice(name=e.value, value=e.value) for e in enum_cls]
    except Exception:
        return []

# Try to import canonical subcats from the model; provide a safe fallback
try:
    from src.models.item import ALLOWED_SUBCATEGORIES, allowed_subcategories_for  # type: ignore
except Exception:
    ALLOWED_SUBCATEGORIES = {
        ItemClass.currency: ["USD", "$", "Cash", "Bitcoin", "BTC", "Crypto"],
        ItemClass.misc: ["Collectible", "Quest", "Junk"],
        ItemClass.tool: ["Lockpick", "Repair", "Utility", "Improvised"],
        ItemClass.weapon: ["Melee", "Firearm", "Thrown", "Tool"],
        ItemClass.gear: ["Clothing", "Armor", "Utility"],
        ItemClass.consumable: ["Food", "Drink", "Medical", "Other"],
        ItemClass.ammo: ["Pistol", "Rifle", "Shotgun", "Other"],
        ItemClass.drugs: ["Depressant", "Stimulant", "Hallucinogen", "Dissociative", "Narcotic", "Inhalant"],
    }
    def allowed_subcategories_for(item_class):  # fallback
        try:
            ic = ItemClass(item_class)
        except Exception:
            ic = item_class
        return ALLOWED_SUBCATEGORIES.get(ic, [])

# Lenient fallback map used only if the model map can’t be read
SUBCATS: dict[str, list[str]] = {
    "weapon": ["melee", "firearm", "thrown", "tool"],
    "currency": ["usd", "$", "cash", "bitcoin", "btc", "crypto"],
    "tool": ["lockpick", "repair", "utility", "improvised"],
    "gear": ["clothing", "armor", "utility"],
    "misc": ["collectible", "quest", "junk"],
    "consumable": ["food", "drink", "medical", "other"],
    "ammo": ["pistol", "rifle", "shotgun", "other"],
    "drugs": ["depressant", "stimulant", "hallucinogen", "dissociative", "narcotic", "inhalant"],
}

def _normalize_class(cls: ItemClass | str | None) -> str:
    if cls is None:
        return ""
    if isinstance(cls, ItemClass):
        return cls.value
    return str(cls).lower()

# ---------------------------------------------------------------------
# Embeds / utility
# ---------------------------------------------------------------------

def _active_work_channel(guild: discord.Guild) -> Optional[discord.TextChannel]:
    from src.core.settings import SETTINGS
    if getattr(SETTINGS, "active_work_channel_id", None):
        ch = guild.get_channel(SETTINGS.active_work_channel_id)
        if isinstance(ch, discord.TextChannel):
            return ch
    for name in ("active-work", "active_work", "activework", "work-active"):
        ch = discord.utils.get(guild.text_channels, name=name)
        if isinstance(ch, discord.TextChannel):
            return ch
    return None

def _icon_asset_path() -> Optional[Path]:
    env = os.getenv("ASSET_ITEM_ICON")
    if env:
        p = Path(env).expanduser()
        if p.exists():
            return p
    base = Path(__file__).resolve().parents[2] / "assets" / "icons"
    for name in ("item_default.png", "item.png", "crate.png"):
        p = base / name
        if p.exists():
            return p
    return None

def _class_emoji(cls_str: str, sub: str | None = None) -> str:
    s = (cls_str or "").lower()
    sub = (sub or "").lower()
    if s == "weapon":
        if sub in ("firearm", "gun", "pistol", "rifle", "smg", "sniper"): return "🔫"
        if sub in ("thrown", "grenade"): return "🎯"
        if sub in ("tool", "improvised"): return "🧰"
        return "🔪"
    if s in ("gear", "armor", "clothing"): return "🧥"
    if s == "tool": return "🧰"
    if s == "currency":
        if sub in ("bitcoin", "btc", "crypto"): return "🪙"
        return "💵"
    if s in ("food", "consumable"): return "🍖"
    if s in ("drink", "beverage"): return "🥤"
    if s in ("medical", "med"): return "💊"
    return "📦"

def _bool_word(v) -> str:
    return "Yes" if bool(v) else "No"

async def _announce_item_card(
    guild: discord.Guild,
    author: discord.abc.User,
    action: str,
    item_obj: Item | None,
    extra: dict | None = None,
) -> None:
    ch = _active_work_channel(guild)
    if not ch:
        log.warning("Active-Work channel not found in %s", getattr(guild, "name", guild.id))
        return

    name = getattr(item_obj, "name", None) or (extra or {}).get("name", "Unknown")
    iid = getattr(item_obj, "id", None) or (extra or {}).get("id", "—")
    cls_val = getattr(item_obj, "item_class", None)
    cls_str = _normalize_class(cls_val or (extra or {}).get("class"))
    sub = getattr(item_obj, "subcategory", None) or (extra or {}).get("subcategory")
    rarity = (getattr(item_obj, "rarity", None) or (extra or {}).get("rarity") or "common").lower()
    stack_max = getattr(item_obj, "stack_max", None) or (extra or {}).get("stack_max", 1)
    dura = getattr(item_obj, "durability", None) or (extra or {}).get("durability", 0)
    cash = getattr(item_obj, "scrap_value", None) or (extra or {}).get("cash", 0)
    equippable = getattr(item_obj, "equippable", None) or (extra or {}).get("equippable", False)

    title_map = {"create": "NEW Item", "delete": "Item Deleted", "edit": "Item Edited"}
    color_map = {"create": discord.Color.green(), "delete": discord.Color.red(), "edit": discord.Color.blurple()}
    title = title_map.get(action, "Item Event")
    color = color_map.get(action, discord.Color.dark_gray())
    emoji = _class_emoji(cls_str, sub)

    e = discord.Embed(title=f"{emoji} {title}", colour=color)
    line1 = f"**{name}** · `ID {iid}`"
    cls_line = f"{cls_str}" + (f" / {sub}" if sub else "")
    line2 = f"*{cls_line} • {rarity}*"
    if action == "delete":
        line3 = f"Removed by **{getattr(author, 'display_name', author)}**"
    else:
        line3 = (
            f"Durability **{int(dura)}** • "
            f"Stack **{int(stack_max)}** • "
            f"Cash **{int(cash)}** • "
            f"Equippable **{_bool_word(equippable)}**"
        )
    e.description = "\n".join([line1, line2, line3])
    e.set_footer(text=f"By {getattr(author, 'display_name', author)}")

    icon_path = _icon_asset_path()
    if icon_path and icon_path.exists():
        e.set_thumbnail(url="attachment://item_icon.png")
        await ch.send(embed=e, file=discord.File(icon_path, filename="item_icon.png"))
    else:
        await ch.send(embed=e)

# ---------------------------------------------------------------------
# Table renders
# ---------------------------------------------------------------------

def _quality_word(q: float) -> str:
    q = float(q)
    if q >= 95: return "Perfect"
    if q >= 80: return "Good"
    if q >= 60: return "Worn"
    if q >= 30: return "Damaged"
    return "Broken"

def _ellipsis(s: str, max_len: int) -> str:
    s = str(s or "")
    return (s[: max_len - 1] + "…") if len(s) > max_len else s

def _emoji_for(row: dict) -> str:
    cls = str(row.get("item_class", "")).lower()
    sub = str(row.get("subcategory", "") or "").lower()
    return _class_emoji(cls, sub)

def _render_inventory_table(rows: List[dict], page: int = 1, page_size: int = 20) -> str:
    total = len(rows)
    if total == 0:
        return "Empty."

    page = max(1, int(page))
    page_size = max(1, int(page_size))
    pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, pages)
    start = (page - 1) * page_size
    chunk = rows[start : start + page_size]

    w_id = 3; w_eq = 1; w_name = 20; w_qty = 3; w_rar = 7; w_qual = 7

    def qty_text(r: dict) -> str:
        qty = int(r.get("qty") or 1)
        stack_max = int(r.get("stack_max") or 1)
        return "–" if stack_max <= 1 else str(qty)

    header = (
        f"{'ID':>{w_id}}  {'':>{w_eq}}  "
        f"{'NAME':<{w_name}}  "
        f"{'QTY':>{w_qty}}  "
        f"{'RAR':<{w_rar}}  "
        f"{'QUAL':<{w_qual}}"
    )
    hr = "─" * len(header)
    lines = [header, hr]

    for r in chunk:
        inv_id = int(r["inv_id"])
        name = _ellipsis(r["name"], w_name)
        eq = "✓" if int(r.get("equipped") or 0) else " "
        rar = (r.get("rarity") or "common").capitalize()
        qual = _quality_word(r.get("quality_float") or 100.0)
        line = (
            f"{inv_id:>{w_id}}  {eq:>{w_eq}}  "
            f"{name:<{w_name}}  "
            f"{qty_text(r):>{w_qty}}  "
            f"{rar:<{w_rar}}  "
            f"{qual:<{w_qual}}"
        )
        lines.append(line)

    if pages > 1:
        lines.append("")
        lines.append(
            f"page {page}/{pages} · items={total} · equipped on page: "
            f"{sum(1 for r in chunk if int(r.get('equipped') or 0))}"
        )

    return f"```\n{'\n'.join(lines)}\n```"

def _render_catalog_table(rows: List[dict]) -> str:
    if not rows:
        return "No matches."

    w_emo = 2; w_id = 3; w_cash = 4; w_name = 20; w_class = 8; w_sub = 8; w_dura = 4; w_qty = 3

    header = (
        f"{'':<{w_emo}}  "
        f"{'ID':>{w_id}}  "
        f"{'$':>{w_cash}}  "
        f"{'NAME':<{w_name}}  "
        f"{'CLASS':<{w_class}}  "
        f"{'SUB':<{w_sub}}  "
        f"{'DURA':>{w_dura}}  "
        f"{'QTY':>{w_qty}}"
    )
    hr = "─" * len(header)
    lines = [header, hr]

    for r in rows:
        emoji = _emoji_for(r)
        cash = int(r.get("cash_value") or 0)
        dura = int(r.get("durability") or 0)
        qty = int(r.get("qty") or r.get("stack_max") or 1)
        cls = str(r.get("item_class") or "").lower()
        sub = str(r.get("subcategory") or "")
        line = (
            f"{emoji:<{w_emo}}  "
            f"{int(r['id']):>{w_id}}  "
            f"{cash:>{w_cash}}  "
            f"{_ellipsis(r['name'], w_name):<{w_name}}  "
            f"{cls:<{w_class}}  "
            f"{_ellipsis(sub, w_sub):<{w_sub}}  "
            f"{dura:>{w_dura}}  "
            f"{qty:>{w_qty}}"
        )
        lines.append(line)

    return f"```\n{'\n'.join(lines)}\n```"

# ---------------------------------------------------------------------
# Autocomplete helpers
# ---------------------------------------------------------------------

async def _ac_item_name(
    interaction: discord.Interaction, current: str
) -> List[app_commands.Choice[str]]:
    query = (current or "").strip()
    choices: List[app_commands.Choice[str]] = []

    try:
        rows = list_item_name_status(query, limit=25)
        if rows:
            for r in rows:
                label = r["name"] + ("  (deleted)" if r.get("deleted") else "")
                choices.append(app_commands.Choice(name=label, value=r["name"]))
            return choices
    except Exception as e:
        log.warning("name autocomplete (status) failed: %s", e)

    try:
        names = list_item_names(query, limit=25, include_deleted=False) if query \
                else list_item_names("", limit=25, include_deleted=False)
        if names:
            return [app_commands.Choice(name=n, value=n) for n in names[:25]]
    except Exception as e:
        log.warning("name autocomplete (primary) failed: %s", e)

    try:
        rows = catalog_items(query, None, None, None, page=1, page_size=25) if query \
               else catalog_items("", None, None, None, page=1, page_size=25)
        names = sorted({str(r.get("name")) for r in rows if r.get("name")})[:25]
        return [app_commands.Choice(name=n, value=n) for n in names]
    except Exception as e:
        log.warning("name autocomplete (fallback) failed: %s", e)
        return []

def _extract_item_class_from_interaction(interaction: discord.Interaction) -> str:
    """Return the selected item_class as a lowercase string, or '' if not set yet."""
    # Preferred: namespace (most versions)
    try:
        ns = getattr(interaction, "namespace", None)
        if ns is not None:
            v = getattr(ns, "item_class", None)
            if isinstance(v, ItemClass):
                return v.value
            if hasattr(v, "value"):
                return str(v.value).lower()
            if v:
                return str(v).lower()
    except Exception:
        pass

    # Fallback: raw options payload (covers subcommand nesting)
    try:
        data = getattr(interaction, "data", {}) or {}
        def walk(options):
            for opt in options or []:
                if opt.get("name") == "item_class" and "value" in opt:
                    return str(opt["value"]).lower()
                if "options" in opt:
                    found = walk(opt.get("options"))
                    if found:
                        return found
            return ""
        return walk(data.get("options", [])) or ""
    except Exception:
        return ""

async def _ac_subcategory(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    """Autocomplete for subcategory; never raises and degrades gracefully."""
    try:
        cls = _extract_item_class_from_interaction(interaction)
        base: list[str] = []
        if cls:
            try:
                base = allowed_subcategories_for(ItemClass(cls))
            except Exception:
                base = SUBCATS.get(cls, [])
        if not base:
            base = sorted({c for opts in SUBCATS.values() for c in opts})[:12]
        q = (current or "").lower()
        suggestions = [s for s in base if q in s.lower()] if q else base
        suggestions = suggestions[:25] or base[:10]
        return [app_commands.Choice(name=s, value=s) for s in suggestions]
    except Exception as e:
        log.warning("subcategory autocomplete failed: %s", e)
        return []

# ---------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------

class InventoryCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---- Admin utilities (debug/sync)

    @app_commands.command(name="debug_itemclass", description="Show ItemClass values (debug)")
    async def debug_itemclass(self, interaction: discord.Interaction):
        vals = ", ".join(e.value for e in ItemClass)
        await interaction.response.send_message(f"ItemClass = [{vals}]", ephemeral=True)

    @app_commands.command(name="sync_here", description="Force-sync slash commands in this server")
    async def sync_here(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Nope.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        synced = await self.bot.tree.sync(guild=interaction.guild)
        await interaction.followup.send(f"Synced {len(synced)} commands to this guild.", ephemeral=True)

    # ---- Admin: grant existing item

    @app_commands.command(name="giveitem", description="Admin: grant an existing catalog item to a member")
    @app_commands.describe(
        member="Target member",
        name="Item name (from catalog)",
        qty="Quantity (default 1)",
        equipped="Equip immediately",
    )
    @app_commands.autocomplete(name=_ac_item_name)
    async def giveitem(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        name: str,
        qty: int = 1,
        equipped: bool = False,
    ):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Nope.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            item = get_item_by_name(name)
            if not item:
                await interaction.followup.send(
                    f"❌ Unknown item **{name}**. Use `/createitem` first, then try again.",
                    ephemeral=True,
                )
                return

            inv_id = grant_item(member.id, item, qty=max(1, qty), equipped=equipped)
            log.info(
                "/giveitem invoked by %s for %s name=%r qty=%s equipped=%s -> inv_id=%s",
                interaction.user, member, name, qty, equipped, inv_id,
            )
            await interaction.followup.send(
                f"✅ Gave **{item.name}** x{qty} to {member.mention} (inv_id **{inv_id}**)",
                ephemeral=True,
            )
        except Exception as e:
            log.exception("giveitem failed")
            await interaction.followup.send(f"Grant failed: `{type(e).__name__}: {e}`", ephemeral=True)

    # ---- Admin: create item

    @app_commands.command(name="createitem", description="Admin: add a new item to the catalog")
    @app_commands.describe(
        name="Unique item name",
        item_class="Item class enum (e.g., misc, weapon, gear...)",
        subcategory="Optional subcategory (e.g., melee, firearm, usd, bitcoin)",
        durability="Base durability (0-100)",
        bop="Bind on pickup?",
        cash="Cash value at a typical vendor",
        hidden="Hidden trait (free text)",
        mint="Mint index / serial number",
        rarity="Rarity (text, e.g. common)",
        stack_max="Max stack size (default 1)",
        equippable="Can be equipped / worn / held?",
    )
    @app_commands.choices(item_class=_enum_choices(ItemClass))           # dynamic from Enum (includes 'drugs')
    @app_commands.autocomplete(subcategory=_ac_subcategory)
    async def createitem(
        self,
        interaction: discord.Interaction,
        name: str,
        item_class: app_commands.Choice[str],                              # Choice[str] at the API boundary
        subcategory: Optional[str] = None,
        durability: int = 0,
        bop: bool = False,
        cash: int = 0,
        hidden: str = "",
        mint: int = 0,
        rarity: str = "common",
        stack_max: int = 1,
        equippable: bool = True,
    ):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Nope.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)

        # Convert choice -> Enum
        try:
            ic = ItemClass(item_class.value)
        except Exception:
            await interaction.followup.send("Invalid item_class.", ephemeral=True)
            return

        # Duplicate name check
        try:
            existing = get_item_by_name(name)
        except Exception:
            existing = None
        if existing:
            await interaction.followup.send(
                f"❌ The name **{name}** is already in use (id **{getattr(existing, 'id', '—')}**). "
                f"Use `/item_edit name:{name}` to modify it, `/item_delete name:{name}` to remove it, "
                f"or choose a different name.",
                ephemeral=True,
            )
            return

        try:
            item = Item(
                id=0,
                name=name,
                item_class=ic,                          # Enum
                created_at=datetime.now(timezone.utc),
                bind_on_pickup=bop,
                durability=durability,
                scrap_value=cash,                       # mirrored to cash_value by manager (compat)
                hidden_trait=hidden,
                mint_index=mint,
                subcategory=(subcategory or None),      # validated by Item.__post_init__
            )
            setattr(item, "rarity", rarity)
            setattr(item, "stack_max", stack_max)
            setattr(item, "equippable", equippable)

            iid = create_item(item)
            item.id = iid
            log.info("/createitem by %s -> %s (id=%s)", interaction.user, name, iid)

            if interaction.guild:
                extras = {
                    "class": ic.value,
                    "subcategory": subcategory or None,
                    "rarity": rarity,
                    "stack_max": stack_max,
                    "durability": durability,
                    "cash": cash,
                    "equippable": equippable,
                }
                await _announce_item_card(interaction.guild, interaction.user, "create", item, extras)

            ch = _active_work_channel(interaction.guild) if interaction.guild else None
            dest = ch.mention if ch else "#active-work"
            await interaction.followup.send(
                f"🆕 Item **{name}** created with id **{iid}** → logged to {dest}", ephemeral=False
            )

        except Exception as e:
            msg = str(e)
            if "UNIQUE constraint failed: items.name" in msg:
                await interaction.followup.send(
                    f"❌ Create failed: an item named **{name}** already exists. "
                    f"Use `/item_edit name:{name}` or choose a different name.",
                    ephemeral=True,
                )
                return
            log.exception("createitem failed")
            await interaction.followup.send(f"Create failed: `{type(e).__name__}: {e}`", ephemeral=False)

    # ---- Admin: edit item

    @app_commands.command(name="item_edit", description="Admin: edit a catalog item")
    @app_commands.describe(
        name="Existing item name (from catalog)",
        new_name="New name (optional)",
        subcategory="New subcategory (optional)",
        durability="New durability",
        bop="Bind on pickup?",
        cash="New cash value",
        hidden="Hidden trait",
        mint="Mint index / serial",
        rarity="Rarity (text)",
        stack_max="Max stack size",
        equippable="Can be equipped / worn / held?",
    )
    @app_commands.autocomplete(name=_ac_item_name, subcategory=_ac_subcategory)
    async def item_edit(
        self,
        interaction: discord.Interaction,
        name: str,
        new_name: Optional[str] = None,
        subcategory: Optional[str] = None,
        durability: Optional[int] = None,
        bop: Optional[bool] = None,
        cash: Optional[int] = None,
        hidden: Optional[str] = None,
        mint: Optional[int] = None,
        rarity: Optional[str] = None,
        stack_max: Optional[int] = None,
        equippable: Optional[bool] = None,
    ):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Nope.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)
        try:
            item = get_item_by_name(name)
            if not item:
                await interaction.followup.send(f"❌ Unknown item **{name}**.", ephemeral=False)
                return

            changed: dict = {}
            if new_name:
                changed["new_name"] = new_name
                item.name = new_name
            if subcategory is not None:
                changed["subcategory"] = subcategory or None
                item.subcategory = subcategory or None
            if durability is not None:
                changed["durability"] = int(durability)
                item.durability = int(durability)
            if bop is not None:
                changed["bind_on_pickup"] = bool(bop)
                item.bind_on_pickup = bool(bop)
            if cash is not None:
                changed["cash"] = int(cash)
                item.scrap_value = int(cash)
                setattr(item, "cash_value", int(cash))
            if hidden is not None:
                changed["hidden_trait"] = hidden
                item.hidden_trait = hidden
            if mint is not None:
                changed["mint_index"] = int(mint)
                item.mint_index = int(mint)
            if rarity is not None:
                changed["rarity"] = str(rarity)
                setattr(item, "rarity", str(rarity))
            if stack_max is not None:
                changed["stack_max"] = int(stack_max)
                setattr(item, "stack_max", int(stack_max))
            if equippable is not None:
                changed["equippable"] = bool(equippable)
                setattr(item, "equippable", bool(equippable))

            update_item(item)
            log.info("/item_edit by %s -> %s (changed=%s)", interaction.user, name, list(changed.keys()))

            if interaction.guild:
                await _announce_item_card(interaction.guild, interaction.user, "edit", item, changed)

            ch = _active_work_channel(interaction.guild) if interaction.guild else None
            dest = ch.mention if ch else "#active-work"
            await interaction.followup.send(
                f"✏️ Item **{item.name}** updated → logged to {dest}", ephemeral=False
            )

        except Exception as e:
            log.exception("item_edit failed")
            await interaction.followup.send(f"Edit failed: `{type(e).__name__}: {e}`", ephemeral=False)

    # ---- Admin: soft-delete

    @app_commands.command(name="item_delete", description="Admin: soft-delete a catalog item by name")
    @app_commands.describe(name="Name of the item to delete")
    @app_commands.autocomplete(name=_ac_item_name)
    async def item_delete_cmd(self, interaction: discord.Interaction, name: str):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Nope.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)
        try:
            pre = get_item_by_name(name)
            ok = soft_delete_item_by_name(name)
            if not ok:
                await interaction.followup.send("Nothing deleted.", ephemeral=False)
                return

            if interaction.guild:
                extras = {"name": name}
                await _announce_item_card(interaction.guild, interaction.user, "delete", pre, extras)

            ch = _active_work_channel(interaction.guild) if interaction.guild else None
            dest = ch.mention if ch else "#active-work"
            nid = getattr(pre, "id", "—")
            await interaction.followup.send(
                f"🗑️ Soft-deleted **{name}** (id **{nid}**) → logged to {dest}", ephemeral=False
            )

        except Exception as e:
            log.exception("item_delete failed")
            await interaction.followup.send(f"Delete error: `{type(e).__name__}: {e}`", ephemeral=False)

    # ---- Catalog (ephemeral)

    @app_commands.command(name="catalog", description="Browse item catalog")
    @app_commands.describe(
        q="Search text",
        rarity="Filter by rarity (e.g., common, rare)",
        item_class="Filter by item_class (e.g., misc, weapon)",
        subcategory="Filter by subcategory (e.g., melee, firearm, usd)",
        equippable="Filter equippable yes/no",
        page="Page number (1-based)",
    )
    @app_commands.autocomplete(subcategory=_ac_subcategory)
    async def catalog_cmd(
        self,
        interaction: discord.Interaction,
        q: Optional[str] = None,
        rarity: Optional[str] = None,
        item_class: Optional[str] = None,
        subcategory: Optional[str] = None,
        equippable: Optional[bool] = None,
        page: int = 1,
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)

        state = {"page": max(1, int(page))}

        def fetch_filtered(p: int) -> List[dict]:
            rows = catalog_items(q or "", rarity, item_class, equippable, page=p, page_size=20)
            if subcategory:
                sub_l = subcategory.lower()
                rows = [r for r in rows if str(r.get("subcategory") or "").lower() == sub_l]
            return rows

        def render() -> str:
            rows = fetch_filtered(state["page"])
            return _render_catalog_table(rows) if rows else "No matches."

        try:
            table = render()
            view = discord.ui.View()
            prev_btn = discord.ui.Button(label="◀ Prev", style=discord.ButtonStyle.secondary)
            next_btn = discord.ui.Button(label="Next ▶", style=discord.ButtonStyle.secondary)

            async def _flip(i: discord.Interaction, delta: int):
                if i.user.id != interaction.user.id:
                    await i.response.send_message("Only the requester can change pages.", ephemeral=True)
                    return
                state["page"] = max(1, state["page"] + delta)
                await i.response.edit_message(content=render(), view=view)

            prev_btn.callback = lambda i: _flip(i, -1)  # type: ignore
            next_btn.callback = lambda i: _flip(i, +1)  # type: ignore
            view.add_item(prev_btn); view.add_item(next_btn)

            await interaction.followup.send(table, view=view, ephemeral=True)
        except Exception as e:
            log.exception("catalog failed")
            await interaction.followup.send(f"Catalog error: `{type(e).__name__}: {e}`", ephemeral=True)

    # ---- Catalog (public)

    @app_commands.command(name="catalog_publish", description="Publish the item catalog (with filters) to this channel.")
    @app_commands.describe(
        q="Search text",
        rarity="Filter by rarity (e.g., common, rare)",
        item_class="Filter by item_class (e.g., misc, weapon)",
        subcategory="Filter by subcategory (e.g., melee, firearm, usd)",
        equippable="Filter equippable yes/no",
        page="Starting page (1-based)",
    )
    @app_commands.autocomplete(subcategory=_ac_subcategory)
    async def catalog_publish(
        self,
        interaction: discord.Interaction,
        q: Optional[str] = None,
        rarity: Optional[str] = None,
        item_class: Optional[str] = None,
        subcategory: Optional[str] = None,
        equippable: Optional[bool] = None,
        page: int = 1,
    ):
        await interaction.response.defer(thinking=True)

        state = {"page": max(1, int(page))}

        def fetch_filtered(p: int) -> List[dict]:
            rows = catalog_items(q or "", rarity, item_class, equippable, page=p, page_size=20)
            if subcategory:
                sub_l = subcategory.lower()
                rows = [r for r in rows if str(r.get("subcategory") or "").lower() == sub_l]
            return rows

        def render() -> str:
            rows = fetch_filtered(state["page"])
            return _render_catalog_table(rows) if rows else "No matches."

        try:
            table = render()
            view = discord.ui.View()
            prev_btn = discord.ui.Button(label="◀ Prev", style=discord.ButtonStyle.secondary)
            next_btn = discord.ui.Button(label="Next ▶", style=discord.ButtonStyle.secondary)

            async def _flip(i: discord.Interaction, delta: int):
                if i.user.id != interaction.user.id:
                    await i.response.send_message("Only the requester can change pages.", ephemeral=True)
                    return
                state["page"] = max(1, state["page"] + delta)
                await i.response.edit_message(content=render(), view=view)

            prev_btn.callback = lambda i: _flip(i, -1)  # type: ignore
            next_btn.callback = lambda i: _flip(i, +1)  # type: ignore
            view.add_item(prev_btn); view.add_item(next_btn)

            await interaction.followup.send(table, view=view, ephemeral=False)
        except Exception as e:
            log.exception("catalog_publish failed")
            await interaction.followup.send(f"Catalog publish error: `{type(e).__name__}: {e}`", ephemeral=False)

    # ---- Player: inventory & equip / unequip

    @app_commands.command(name="inventory", description="View your inventory (or a member’s).")
    @app_commands.describe(member="Optional member to inspect", page="Optional page number (1-based)")
    async def inventory_cmd(
        self,
        interaction: discord.Interaction,
        member: Optional[discord.Member] = None,
        page: int = 1,
    ):
        target = member or interaction.user  # type: ignore
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            rows = inventory_for_user(target.id)
            if not rows:
                await interaction.followup.send("Empty.", ephemeral=True)
                return
            table = _render_inventory_table(rows, page=page, page_size=20)
            if len(table) > 1990:
                table = table[:1987] + "```"
            await interaction.followup.send(table, ephemeral=True)
        except Exception as e:
            log.exception("inventory failed")
            await interaction.followup.send(f"Inventory error: `{type(e).__name__}: {e}`", ephemeral=True)

    @app_commands.command(name="equip", description="Equip an inventory item by id.")
    async def equip_cmd(self, interaction: discord.Interaction, inv_id: int):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            set_equipped(inv_id, True)
            await interaction.followup.send("✅ Equipped", ephemeral=True)
        except ValueError as e:
            await interaction.followup.send(f"❌ {e}", ephemeral=True)
        except Exception as e:
            log.exception("equip failed")
            await interaction.followup.send(f"Equip error: `{type(e).__name__}: {e}`", ephemeral=True)

    @app_commands.command(name="unequip", description="Unequip an inventory item by id.")
    async def unequip_cmd(self, interaction: discord.Interaction, inv_id: int):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            set_equipped(inv_id, False)
            await interaction.followup.send("✅ Unequipped", ephemeral=True)
        except Exception as e:
            log.exception("unequip failed")
            await interaction.followup.send(f"Unequip error: `{type(e).__name__}: {e}`", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(InventoryCog(bot))
