# FILE: src/bot/inventory.py
from __future__ import annotations

import discord
from discord import app_commands

from src.core.inventory import (
    add_item,
    equip_item,
    get_inventory,
    get_owned_item_ids,
    remove_item,
    unequip_slot,
)
from src.core.items import SLOTS, get_item, list_items


async def _safe_reply(inter: discord.Interaction, *, content=None, embed=None, ephemeral=True):
    try:
        if not inter.response.is_done():
            await inter.response.send_message(content=content, embed=embed, ephemeral=ephemeral)
        else:
            await inter.followup.send(content=content, embed=embed, ephemeral=ephemeral)
    except Exception:
        pass  # best-effort


def _inv_embed(user: discord.User, inv: dict, eq: dict) -> discord.Embed:
    e = discord.Embed(title=f"ðŸŽ’ Inventory â€” {user.display_name}", color=discord.Color.dark_gold())
    if inv:
        lines = [f"- **{get_item(i).name if get_item(i) else i}** Ã— {c}" for i, c in inv.items()]
        e.add_field(name="Items", value="\n".join(lines)[:1024], inline=False)
    else:
        e.add_field(name="Items", value="(empty)", inline=False)

    if eq:
        lines = [
            f"- **{slot}**: {get_item(i).name if get_item(i) else i}" for slot, i in eq.items()
        ]
        e.add_field(name="Equipped", value="\n".join(lines)[:1024], inline=False)
    else:
        e.add_field(name="Equipped", value="(nothing equipped)", inline=False)
    e.set_footer(text=f"Use /inv equip, /inv unequip (slots: {', '.join(SLOTS)})")
    return e


def register_inventory(tree: app_commands.CommandTree) -> None:
    inv = app_commands.Group(name="inv", description="Inventory and equipment")

    @inv.command(name="show", description="Show your inventory and equipped gear.")
    async def show(inter: discord.Interaction):
        items, eq = await get_inventory(inter.user.id)
        await _safe_reply(inter, embed=_inv_embed(inter.user, items, eq), ephemeral=True)

    @inv.command(name="equip", description="Equip an item you own.")
    @app_commands.describe(item_id="ID of the item to equip (see /inv listitems or /inv show).")
    async def equip(inter: discord.Interaction, item_id: str):
        ok, msg = await equip_item(inter.user.id, item_id)
        await _safe_reply(inter, content=("âœ… " if ok else "âš ï¸ ") + msg, ephemeral=True)
        if ok:
            items, eq = await get_inventory(inter.user.id)
            await inter.followup.send(embed=_inv_embed(inter.user, items, eq), ephemeral=True)

    @inv.command(name="unequip", description="Unequip a slot.")
    @app_commands.describe(slot=f"One of: {', '.join(SLOTS)}")
    async def unequip(inter: discord.Interaction, slot: str):
        ok, msg = await unequip_slot(inter.user.id, slot)
        await _safe_reply(inter, content=("âœ… " if ok else "âš ï¸ ") + msg, ephemeral=True)
        if ok:
            items, eq = await get_inventory(inter.user.id)
            await inter.followup.send(embed=_inv_embed(inter.user, items, eq), ephemeral=True)

    @inv.command(name="listitems", description="List the item catalog.")
    async def listitems(inter: discord.Interaction):
        catalog = list_items()
        lines = [
            f"`{iid}` â€” **{it.name}** (slot: {it.slot or 'â€”'}, wt {it.weight})"
            for iid, it in catalog.items()
        ]
        e = discord.Embed(
            title="ðŸ“¦ Item Catalog",
            description="\n".join(lines)[:4000],
            color=discord.Color.dark_gold(),
        )
        await _safe_reply(inter, embed=e, ephemeral=True)

    # (Optional) Admin helper for testing
    @inv.command(name="give", description="[Admin] Give an item to a user.")
    @app_commands.describe(user="Target player", item_id="Item ID", qty="Quantity")
    async def give(inter: discord.Interaction, user: discord.User, item_id: str, qty: int = 1):
        if not inter.user.guild_permissions.manage_guild:
            await _safe_reply(inter, content="You need Manage Server permission.", ephemeral=True)
            return
        if not get_item(item_id):
            await _safe_reply(inter, content="Unknown item_id. Use /inv listitems.", ephemeral=True)
            return
        await add_item(user.id, item_id, qty)
        await _safe_reply(
            inter,
            content=f"âœ… Gave **{qty}Ã— {get_item(item_id).name}** to **{user.display_name}**.",
            ephemeral=True,
        )

    tree.add_command(inv)
