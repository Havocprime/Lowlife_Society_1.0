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
)

log = logging.getLogger("inventory.cog")


def _fmt_line(r: dict) -> str:
    """Pretty row for /inventory."""
    name = r["name"]
    qty = int(r.get("qty") or 1)
    stack_max = int(r.get("stack_max") or 1) if r.get("stack_max") is not None else 1
    rarity = (r.get("rarity") or "common").lower()
    equipped = " ✅" if int(r.get("equipped") or 0) else ""
    # No "x1" for non-stackables; show xN for stackables
    qty_txt = f" x{qty}" if stack_max > 1 else ""
    return f"#{r['inv_id']:>2} — {name}{qty_txt} · class={r.get('item_class','?')} · {rarity}{equipped}"


async def _ac_item_name(
    interaction: discord.Interaction, current: str
) -> List[app_commands.Choice[str]]:
    """Autocomplete strictly from the catalog (case-insensitive prefix)."""
    try:
        names = list_item_names(current or "", limit=25)
    except Exception as e:
        log.warning("name autocomplete failed: %s", e)
        names = []
    return [app_commands.Choice(name=n, value=n) for n in names]


class InventoryCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -------------------------------------------------------------------------
    # Admin: grant an existing catalog item
    # -------------------------------------------------------------------------
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
                interaction.user,
                member,
                name,
                qty,
                equipped,
                inv_id,
            )
            await interaction.followup.send(
                f"✅ Gave **{item.name}** x{qty} to {member.mention} (inv_id **{inv_id}**)",
                ephemeral=True,
            )
        except Exception as e:
            log.exception("giveitem failed")
            await interaction.followup.send(
                f"Grant failed: `{type(e).__name__}: {e}`", ephemeral=True
            )

    # Back-compat alias (/inv_grant) — calls /giveitem under the hood
    @app_commands.command(
        name="inv_grant", description="(alias) Admin: grant a catalog item to a member"
    )
    @app_commands.describe(
        member="Target member",
        name="Item name (from catalog)",
        qty="Quantity (default 1)",
        equipped="Equip immediately",
    )
    @app_commands.autocomplete(name=_ac_item_name)
    async def inv_grant_alias(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        name: str,
        qty: int = 1,
        equipped: bool = False,
    ):
        await self.giveitem.callback(  # type: ignore
            self, interaction, member, name, qty, equipped
        )

    # -------------------------------------------------------------------------
    # Admin: create a new catalog item (renamed from /item_add → /createitem)
    # -------------------------------------------------------------------------
    @app_commands.command(
        name="createitem", description="Admin: add a new item to the catalog"
    )
    @app_commands.describe(
        name="Unique item name",
        item_class="Item class enum (e.g., misc, weapon, gear...)",
        durability="Base durability (0-100)",
        bop="Bind on pickup?",
        pitch="Pitch value",
        rune="Rune value",
        scrap="Scrap value",
        hidden="Hidden trait (free text)",
        mint="Mint index / serial number",
    )
    async def createitem(
        self,
        interaction: discord.Interaction,
        name: str,
        item_class: ItemClass,
        durability: int = 0,
        bop: bool = False,
        pitch: int = 0,
        rune: int = 0,
        scrap: int = 0,
        hidden: str = "",
        mint: int = 0,
    ):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Nope.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            item = Item(
                id=0,  # allocated by manager.create_item
                name=name,
                item_class=item_class,
                created_at=datetime.now(timezone.utc),
                bind_on_pickup=bop,
                durability=durability,
                pitch_value=pitch,
                rune_value=rune,
                scrap_value=scrap,
                hidden_trait=hidden,
                mint_index=mint,
            )
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

    # -------------------------------------------------------------------------
    # Admin: edit an existing catalog item
    # -------------------------------------------------------------------------
    @app_commands.command(name="item_edit", description="Admin: edit a catalog item")
    @app_commands.describe(
        name="Existing item name (from catalog)",
        new_name="New name (optional)",
        durability="New durability",
        bop="Bind on pickup?",
        pitch="Pitch value",
        rune="Rune value",
        scrap="Scrap value",
        hidden="Hidden trait",
        mint="Mint index / serial",
    )
    @app_commands.autocomplete(name=_ac_item_name)
    async def item_edit(
        self,
        interaction: discord.Interaction,
        name: str,
        new_name: Optional[str] = None,
        durability: Optional[int] = None,
        bop: Optional[bool] = None,
        pitch: Optional[int] = None,
        rune: Optional[int] = None,
        scrap: Optional[int] = None,
        hidden: Optional[str] = None,
        mint: Optional[int] = None,
    ):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Nope.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            item = get_item_by_name(name)
            if not item:
                await interaction.followup.send(
                    f"❌ Unknown item **{name}**.", ephemeral=True
                )
                return

            # Apply patches
            if new_name:
                item.name = new_name
            if durability is not None:
                item.durability = durability
            if bop is not None:
                item.bind_on_pickup = bool(bop)
            if pitch is not None:
                item.pitch_value = pitch
            if rune is not None:
                item.rune_value = rune
            if scrap is not None:
                item.scrap_value = scrap
            if hidden is not None:
                item.hidden_trait = hidden
            if mint is not None:
                item.mint_index = mint

            update_item(item)
            log.info("/item_edit by %s -> %s", interaction.user, name)
            await interaction.followup.send(
                f"✏️ Item **{name}** updated.", ephemeral=True
            )
        except Exception as e:
            log.exception("item_edit failed")
            await interaction.followup.send(
                f"Edit failed: `{type(e).__name__}: {e}`", ephemeral=True
            )

    # -------------------------------------------------------------------------
    # Player-facing: inventory & equip/unequip
    # -------------------------------------------------------------------------
    @app_commands.command(name="inventory", description="View your inventory (or a member’s).")
    @app_commands.describe(member="Optional member to inspect")
    async def inventory_cmd(
        self, interaction: discord.Interaction, member: Optional[discord.Member] = None
    ):
        target = member or interaction.user  # type: ignore
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            rows = inventory_for_user(target.id)
            if not rows:
                await interaction.followup.send("Empty.", ephemeral=True)
                return
            lines = [_fmt_line(r) for r in rows]
            await interaction.followup.send("\n".join(lines)[:1900], ephemeral=True)
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
