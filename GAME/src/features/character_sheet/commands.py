from __future__ import annotations
import discord
from discord import app_commands
from discord.ext import commands
from src.features.character_sheet import service, ui
from src.db import dal

class CharacterSheetCmds(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="onboard", description="Create or link your LOWLIFE character.")
    async def onboard(self, interaction: discord.Interaction, codename: str, faction: str | None = None):
        await interaction.response.defer(ephemeral=True)
        pid = service.upsert_player_from_discord(interaction.user.id, str(interaction.user))
        cid = service.ensure_character(pid, codename=codename, faction=faction)
        dal.ensure_wallet("character", cid)
        # seed a tiny balance to prove wiring (optional)
        dal.tx_credit("character", cid, 10, reason="onboard/bonus", idem=f"onb-{interaction.user.id}")
        # show sheet
        player = dal.get_player_by_discord(str(interaction.user.id))
        chars = dal.get_characters(player["id"])
        embed = ui.character_embed(player, chars[0] if chars else None)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="character", description="Show your character sheet.")
    async def character(self, interaction: discord.Interaction, member: discord.Member | None = None):
        await interaction.response.defer(ephemeral=True)
        target = member or interaction.user
        player = dal.get_player_by_discord(str(target.id))
        if not player:
            await interaction.followup.send("No player record yet. Use `/onboard`.", ephemeral=True)
            return
        chars = dal.get_characters(player["id"])
        embed = ui.character_embed(player, chars[0] if chars else None)
        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(CharacterSheetCmds(bot))
