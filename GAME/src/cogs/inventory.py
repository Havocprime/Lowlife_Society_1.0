# GAME/src/cogs/inventory.py
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from src.models.item import Item, ItemClass
from src.inventory.manager import (
    list_item_names,
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

# -----------------------------
# Small formatting helpers
# -----------------------------

def _quality_word(q: float) -> str:
    q = float(q)
    if q >= 95:
        return "Perfect"
    if q >= 80:
        return "Good"
    if q >= 60:
        return "Worn"
    if q >= 30:
        return "Damaged"
    return "Broken"

def _ellipsis(s: str, max_len: int) -> str:
    s = str(s or "")
    return (s[: max_len - 1] + "…") if len(s) > max_len else s

def _emoji_for(row: dict) -> str:
    """Pick a simple emoji by class/name for catalog prettiness."""
    cls = str(row.get("item_class", "")).lower()
    name = str(row.get("name", "")).lower()
    if any(w in name for w in ("bill", "coin", "quarters", "quarter", "dollar", "cash")):
        return "💵"
    if cls in ("currency", "money", "cash"):
        return "💵"
    if cls in ("weapon", "melee", "ranged"):
        return "⚔️"
    if cls in ("gear", "armor", "clothing"):
        return "🧥"
    if cls in ("tool",):
        return "🧰"
    if cls in ("food", "consumable"):
        return "🍖"
    if cls in ("drink", "beverage"):
        return "🥤"
    if cls in ("medical", "medicine", "med"):
        return "💊"
    return "📦"  # misc / default

def _render_inventory_table(rows: List[dict], page: int = 1, page_size: int = 20) -> str:
    """
    Inventory table (monospace):

      ID  EQ  NAME                 QTY   RARITY   QUAL
    """
    total = len(rows)
    if total == 0:
        return "Empty."

    page = max(1, int(page))
    page_size = max(1, int(page_size))
    pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, pages)
    start = (page - 1) * page_size
    chunk = rows[start : start + page_size]

    w_id = 3
    w_eq = 1
    w_name = 20
    w_qty = 3
    w_rar = 7
    w_qual = 7

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
    """
    Catalog table (monospace):

      EMOJI  ID   $   NAME                 CLASS      DURA  QTY
    """
    if not rows:
        return "No matches."

    w_emo = 2
    w_id = 3
    w_cash = 4
    w_name = 20
    w_class = 8
    w_dura = 4
    w_qty = 3

    header = (
        f"{'':<{w_emo}}  "
        f"{'ID':>{w_id}}  "
        f"{'$':>{w_cash}}  "
        f"{'NAME':<{w_name}}  "
        f"{'CLASS':<{w_class}}  "
        f"{'DURA':>{w_dura}}  "
        f"{'QTY':>{w_qty}}"
    )
    hr = "─" * len(header)
    lines = [header, hr]

    for r in rows:
        emoji = _emoji_for(r)
        cash = int(r.get("cash_value") or 0)          # manager selects scrap_value AS cash_value
        dura = int(r.get("durability") or 0)          # manager selects durability column
        qty = int(r.get("stack_max") or 1)            # show stack_max as QTY in catalog
        line = (
            f"{emoji:<{w_emo}}  "
            f"{int(r['id']):>{w_id}}  "
            f"{cash:>{w_cash}}  "
            f"{_ellipsis(r['name'], w_name):<{w_name}}  "
            f"{str(r['item_class']).lower():<{w_class}}  "
            f"{dura:>{w_dura}}  "
            f"{qty:>{w_qty}}"
        )
        lines.append(line)

    return f"```\n{'\n'.join(lines)}\n```"

async def _ac_item_name(
    interaction: discord.Interaction, current: str
) -> List[app_commands.Choice[str]]:
    """Autocomplete strictly from active catalog (case-insensitive)."""
    try:
        names = list_item_names(current or "", limit=25)
    except Exception as e:
        log.warning("name autocomplete failed: %s", e)
        names = []
    return [app_commands.Choice(name=n, value=n) for n in names]

# -----------------------------
# Cog
# -----------------------------

class InventoryCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -------- Admin: grant existing item --------
    @app_commands.command(
        name="giveitem", description="Admin: grant an existing catalog item to a member"
    )
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
                f"✅ Gave **{item.name}** x{qty} to {member.mention} (inv_id **{inv_id}**) ",
                ephemeral=True,
            )
        except Exception as e:
            log.exception("giveitem failed")
            await interaction.followup.send(
                f"Grant failed: `{type(e).__name__}: {e}`", ephemeral=True
            )

    # -------- Admin: create item --------
    @app_commands.command(name="createitem", description="Admin: add a new item to the catalog")
    @app_commands.describe(
        name="Unique item name",
        item_class="Item class enum (e.g., misc, weapon, gear...)",
        durability="Base durability (0-100)",
        bop="Bind on pickup?",
        cash="Cash value at a typical vendor",
        hidden="Hidden trait (free text)",
        mint="Mint index / serial number",
        rarity="Rarity (text, e.g. common)",
        stack_max="Max stack size (default 1)",
        equippable="Can be equipped / worn / held?",
    )
    async def createitem(
        self,
        interaction: discord.Interaction,
        name: str,
        item_class: ItemClass,
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

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            item = Item(
                id=0,
                name=name,
                item_class=item_class,
                created_at=datetime.now(timezone.utc),
                bind_on_pickup=bop,
                durability=durability,
                # CASH lives in scrap_value (manager exposes as cash_value for catalog)
                scrap_value=cash,
                hidden_trait=hidden,
                mint_index=mint,
            )
            # Extras that may not be explicit in dataclass
            setattr(item, "rarity", rarity)
            setattr(item, "stack_max", stack_max)
            setattr(item, "equippable", equippable)

            iid = create_item(item)
            log.info("/createitem by %s -> %s (id=%s)", interaction.user, name, iid)
            await interaction.followup.send(
                f"🆕 Item **{name}** created with id **{iid}**.", ephemeral=True
            )
        except Exception as e:
            log.exception("createitem failed")
            await interaction.followup.send(
                f"Create failed: `{type(e).__name__}: {e}`", ephemeral=True
            )

    # -------- Admin: edit item --------
    @app_commands.command(name="item_edit", description="Admin: edit a catalog item")
    @app_commands.describe(
        name="Existing item name (from catalog)",
        new_name="New name (optional)",
        durability="New durability",
        bop="Bind on pickup?",
        cash="New cash value",
        hidden="Hidden trait",
        mint="Mint index / serial",
        rarity="Rarity (text)",
        stack_max="Max stack size",
        equippable="Can be equipped / worn / held?",
    )
    @app_commands.autocomplete(name=_ac_item_name)
    async def item_edit(
        self,
        interaction: discord.Interaction,
        name: str,
        new_name: Optional[str] = None,
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

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            item = get_item_by_name(name)
            if not item:
                await interaction.followup.send(f"❌ Unknown item **{name}**.", ephemeral=True)
                return

            if new_name:
                item.name = new_name
            if durability is not None:
                item.durability = int(durability)
            if bop is not None:
                item.bind_on_pickup = bool(bop)
            if cash is not None:
                # In the dataclass we continue to store this in scrap_value
                item.scrap_value = int(cash)
                setattr(item, "cash_value", int(cash))
            if hidden is not None:
                item.hidden_trait = hidden
            if mint is not None:
                item.mint_index = int(mint)
            if rarity is not None:
                setattr(item, "rarity", str(rarity))
            if stack_max is not None:
                setattr(item, "stack_max", int(stack_max))
            if equippable is not None:
                setattr(item, "equippable", bool(equippable))

            update_item(item)
            log.info("/item_edit by %s -> %s", interaction.user, name)
            await interaction.followup.send(f"✏️ Item **{item.name}** updated.", ephemeral=True)
        except Exception as e:
            log.exception("item_edit failed")
            await interaction.followup.send(
                f"Edit failed: `{type(e).__name__}: {e}`", ephemeral=True
            )

    # -------- Admin: soft-delete --------
    @app_commands.command(name="item_delete", description="Admin: soft-delete a catalog item by name")
    @app_commands.describe(name="Name of the item to delete")
    @app_commands.autocomplete(name=_ac_item_name)
    async def item_delete_cmd(self, interaction: discord.Interaction, name: str):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Nope.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            ok = soft_delete_item_by_name(name)
            if not ok:
                await interaction.followup.send("Nothing deleted.", ephemeral=True)
                return
            await interaction.followup.send(f"🗑️ Soft-deleted **{name}**.", ephemeral=True)
        except Exception as e:
            log.exception("item_delete failed")
            await interaction.followup.send(
                f"Delete error: `{type(e).__name__}: {e}`", ephemeral=True
            )

    # -------- Admin/Player: catalog --------
    @app_commands.command(name="catalog", description="Browse item catalog")
    @app_commands.describe(
        q="Search text",
        rarity="Filter by rarity (e.g., common, rare)",
        item_class="Filter by item_class (e.g., misc, weapon)",
        equippable="Filter equippable yes/no",
        page="Page number (1-based)",
    )
    async def catalog_cmd(
        self,
        interaction: discord.Interaction,
        q: Optional[str] = None,
        rarity: Optional[str] = None,
        item_class: Optional[str] = None,
        equippable: Optional[bool] = None,
        page: int = 1,
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            rows = catalog_items(q or "", rarity, item_class, equippable, page=page, page_size=20)
            if not rows:
                await interaction.followup.send("No matches.", ephemeral=True)
                return

            table = _render_catalog_table(rows)

            view = discord.ui.View()
            prev_btn = discord.ui.Button(label="◀ Prev", style=discord.ButtonStyle.secondary)
            next_btn = discord.ui.Button(label="Next ▶", style=discord.ButtonStyle.secondary)

            async def _turn(i: discord.Interaction, delta: int):
                new_page = max(1, page + delta)
                r2 = catalog_items(q or "", rarity, item_class, equippable, page=new_page, page_size=20)
                await i.response.edit_message(content=_render_catalog_table(r2), view=view)

            async def _prev_cb(i: discord.Interaction):
                await _turn(i, -1)

            async def _next_cb(i: discord.Interaction):
                await _turn(i, +1)

            prev_btn.callback = _prev_cb  # type: ignore
            next_btn.callback = _next_cb  # type: ignore
            view.add_item(prev_btn)
            view.add_item(next_btn)

            await interaction.followup.send(table, view=view, ephemeral=True)
        except Exception as e:
            log.exception("catalog failed")
            await interaction.followup.send(
                f"Catalog error: `{type(e).__name__}: {e}`", ephemeral=True
            )

    # -------- Player: inventory & equip/unequip --------
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
            await interaction.followup.send(
                f"Inventory error: `{type(e).__name__}: {e}`", ephemeral=True
            )

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
            await interaction.followup.send(
                f"Equip error: `{type(e).__name__}: {e}`", ephemeral=True
            )

    @app_commands.command(name="unequip", description="Unequip an inventory item by id.")
    async def unequip_cmd(self, interaction: discord.Interaction, inv_id: int):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            set_equipped(inv_id, False)
            await interaction.followup.send("✅ Unequipped", ephemeral=True)
        except Exception as e:
            log.exception("unequip failed")
            await interaction.followup.send(
                f"Unequip error: `{type(e).__name__}: {e}`", ephemeral=True
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(InventoryCog(bot))
