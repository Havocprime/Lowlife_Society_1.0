from __future__ import annotations
import uuid, discord
from discord import app_commands
from discord.ext import commands
from src.features.character_sheet import service, ui
from src.db import dal
from src.core.perm import require_role, Role

class CharacterSheetCmds(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ... existing /onboard and /character ...

    @app_commands.command(name="character_give_test_item", description="ADMIN: grant a test item to a member.")
    @app_commands.describe(member="Target member", item_name="Name of the test item", qty="Quantity", bonus_coins="Optional coin bonus")
    @require_role(Role.ADMIN)
    async def character_give_test_item(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        item_name: str = "Test Crate",
        qty: int = 1,
        bonus_coins: int = 0,
    ):
        await interaction.response.defer(ephemeral=True)

        # Resolve/create player/character
        pid = service.upsert_player_from_discord(member.id, str(member))
        chars = dal.get_characters(pid)
        if not chars:
            cid = service.ensure_character(pid, codename=member.display_name, faction=None)
        else:
            cid = chars[0]["id"]

        # Ensure wallet + optional coin bonus
        dal.ensure_wallet("character", cid)
        if bonus_coins:
            dal.tx_credit("character", cid, bonus_coins, reason="admin/test_grant", idem=f"adm-coin-{uuid.uuid4()}")

        # Ensure the item def and grant
        idef_id = dal.ensure_itemdef(item_name, rarity="Common", klass="AdminTest", tags="test")
        dal.grant_item(cid, idef_id, qty=qty, meta={"source": "admin_test"})

        # Log event
        dal.append_event(
            "admin/grant_item",
            str(interaction.user.id),
            f"character:{cid}",
            {"item": item_name, "qty": qty, "bonus_coins": bonus_coins},
        )

        # Show updated sheet
        player = dal.get_player_by_discord(str(member.id))
        char = dal.get_characters(player["id"])[0]
        embed = ui.character_embed(player, char)
        await interaction.followup.send(f"✅ Granted **{qty}× {item_name}** to {member.mention}.", ephemeral=True)
        await interaction.followup.send(embed=embed, ephemeral=True)
