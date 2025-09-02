# GAME/src/cogs/items_admin.py
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from src.models.item import Item, ItemClass

log = logging.getLogger("items_admin.cog")

DB_PATH = Path("var/db/lowlife.sqlite")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Map nice choice labels -> ItemClass enum
_ITEMCLASS_CHOICES: list[tuple[str, ItemClass]] = [
    ("weapon", ItemClass.WEAPON) if hasattr(ItemClass, "WEAPON") else ("weapon", ItemClass.MISC),
    ("tool", ItemClass.TOOL) if hasattr(ItemClass, "TOOL") else ("tool", ItemClass.MISC),
    ("gear", ItemClass.GEAR) if hasattr(ItemClass, "GEAR") else ("gear", ItemClass.MISC),
    ("clothes", ItemClass.CLOTHES) if hasattr(ItemClass, "CLOTHES") else ("clothes", ItemClass.MISC),
    ("medical", ItemClass.MEDICAL) if hasattr(ItemClass, "MEDICAL") else ("medical", ItemClass.MISC),
    ("misc", ItemClass.MISC),
]


class ItemsAdminCog(commands.Cog):
    """Admin: maintain the item catalog (authoritative list of spawnable items)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------------- /createitem ----------------
    @app_commands.command(name="createitem", description="Admin: add a new item to the catalog.")
    @app_commands.describe(
        name="Display name (must be unique, case-insensitive)",
        item_class="Category/class for the item",
        bind_on_pickup="If true, entry is character-bound on pickup",
        durability="Base durability (0-100, default 100)",
    )
    @app_commands.choices(
        item_class=[
            app_commands.Choice(name=label, value=label) for (label, _enum) in _ITEMCLASS_CHOICES
        ]
    )
    async def createitem(
        self,
        interaction: discord.Interaction,
        name: str,
        item_class: str,
        bind_on_pickup: bool = False,
        durability: int = 100,
    ):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Nope.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            with sqlite3.connect(DB_PATH) as cx:
                cx.row_factory = sqlite3.Row
                cur = cx.cursor()

                # Prevent duplicates (case-insensitive)
                cur.execute("SELECT id FROM items WHERE LOWER(name)=LOWER(?)", (name,))
                row = cur.fetchone()
                if row:
                    await interaction.followup.send(
                        f"❌ Item **{name}** already exists (id `{row['id']}`).", ephemeral=True
                    )
                    return

                # Choose enum (fallback to MISC if the enum is not present)
                enum = next((e for (label, e) in _ITEMCLASS_CHOICES if label == item_class), ItemClass.MISC)

                # Deterministic id by name (matches grant path we used earlier)
                item_id = abs(hash((name, "catalog"))) % (2**31)

                # Insert using existing columns so we don’t require schema changes
                cur.execute(
                    """
                    INSERT INTO items (
                        id, name, item_class, created_at,
                        bind_on_pickup, durability, pitch_value, rune_value, scrap_value,
                        hidden_trait, mint_index
                    )
                    VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0, '', 0)
                    """,
                    (
                        item_id,
                        name,
                        enum.value,
                        _now_iso(),
                        1 if bind_on_pickup else 0,
                        max(0, min(int(durability), 100)),
                    ),
                )
                cx.commit()

            log.info("/createitem: '%s' class=%s id=%s", name, item_class, item_id)
            await interaction.followup.send(
                f"✅ Created item **{name}** (class `{item_class}`, id `{item_id}`) in catalog.",
                ephemeral=True,
            )
        except Exception as e:
            log.exception("createitem failed")
            await interaction.followup.send(f"Create failed: `{type(e).__name__}: {e}`", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ItemsAdminCog(bot))
