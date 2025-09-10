from __future__ import annotations
import discord
from discord import app_commands
from discord.ext import commands
from src.core.perm import require_role, Role, dangerous_op_cooldown
from src.economy import actions
from src.features.character_sheet import service

def ensure_cid(member: discord.Member) -> int:
    # Create/lookup player + at least one character (reusing your service)
    pid = service.upsert_player_from_discord(member.id, str(member))
    chars = service.dal.get_characters(pid) if hasattr(service, "dal") else None
    from src.db import dal as DAL
    if not chars:
        return service.ensure_character(pid, codename=member.display_name, faction=None)
    return int(chars[0]["id"])

class EconAdmin(commands.Cog):
    def __init__(self, bot: commands.Bot): self.bot = bot

    @app_commands.command(name="econ_transfer", description="ADMIN: transfer coins between two members.")
    @app_commands.describe(src="From member", dst="To member", amount="Coins", memo="Reason")
    @require_role(Role.ADMIN)
    @dangerous_op_cooldown("econ_transfer", 10)
    async def econ_transfer(self, interaction: discord.Interaction, src: discord.Member, dst: discord.Member,
                            amount: int, memo: str = "admin/transfer"):
        await interaction.response.defer(ephemeral=True)
        s = ensure_cid(src); d = ensure_cid(dst)
        b1, b2 = actions.transfer(s, d, amount, reason=memo)
        await interaction.followup.send(
            f"âœ… {src.mention} â†’ {dst.mention} **{amount}**. Balances: {b1}/{b2}",
            ephemeral=True
        )

    @app_commands.command(name="econ_purchase", description="ADMIN: simulate a purchase (debit).")
    @require_role(Role.ADMIN)
    async def econ_purchase(self, interaction: discord.Interaction, buyer: discord.Member, amount: int,
                            memo: str = "admin/purchase"):
        await interaction.response.defer(ephemeral=True)
        cid = ensure_cid(buyer)
        bal = actions.purchase(cid, amount, reason=memo)
        await interaction.followup.send(f"ðŸ›’ Debited **{amount}** from {buyer.mention}. Balance: {bal}", ephemeral=True)

    @app_commands.command(name="econ_refund", description="ADMIN: simulate a refund (credit).")
    @require_role(Role.ADMIN)
    async def econ_refund(self, interaction: discord.Interaction, buyer: discord.Member, amount: int,
                          memo: str = "admin/refund"):
        await interaction.response.defer(ephemeral=True)
        cid = ensure_cid(buyer)
        bal = actions.refund(cid, amount, reason=memo)
        await interaction.followup.send(f"â†©ï¸ Refunded **{amount}** to {buyer.mention}. Balance: {bal}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(EconAdmin(bot))
