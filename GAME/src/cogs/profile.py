# GAME/src/cogs/profile.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from src.db import dal


def _fmt_dt(s: Optional[str]) -> str:
    if not s:
        return "â€”"
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00")) if "T" in s else datetime.fromisoformat(s)
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return s

def _pronoun_label(value: Optional[str]) -> str:
    """Normalize any stored value to Male / Female / Other for display."""
    v = (value or "").strip().lower()
    male = {"he", "him", "he/him", "male", "man", "m", "masc", "boy"}
    female = {"she", "her", "she/her", "female", "woman", "f", "femme", "girl"}
    if v in male:
        return "Male"
    if v in female:
        return "Female"
    return "Other"  # default bucket


class Profile(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="profile", description="Show your LOWLIFE character profile.")
    async def profile(self, itx: discord.Interaction):
        await itx.response.defer(ephemeral=False, thinking=False)
        discord_id = str(itx.user.id)

        ch = dal.get_primary_character_by_discord(discord_id)
        if not ch:
            embed = discord.Embed(
                title="No character found",
                description="You donâ€™t have a LOWLIFE character yet. Run **/onboard** to create one.",
                color=0xFD9644,
            )
            await itx.followup.send(embed=embed, ephemeral=True)
            return

        name = getattr(ch, "name", "Unknown")
        char_code = getattr(ch, "char_id", "â€”")
        pronouns_display = _pronoun_label(getattr(ch, "pronouns", None))
        district = getattr(ch, "starting_district", None) or "â€”"
        arche = getattr(ch, "archetypes", None) or "â€”"
        background = getattr(ch, "background", None) or "â€”"

        s_str = getattr(ch, "str", 5)
        s_vit = getattr(ch, "vit", 5)
        s_end = getattr(ch, "end", 5)
        s_agi = getattr(ch, "agi", 5)
        s_dex = getattr(ch, "dex", 5)
        s_wis = getattr(ch, "wis", 5)
        s_int = getattr(ch, "intel", 5)
        s_cha = getattr(ch, "cha", 5)
        s_luck = getattr(ch, "luck", 5)
        hp = getattr(ch, "hp", 60)

        created = _fmt_dt(getattr(ch, "created_at", None))
        updated = _fmt_dt(getattr(ch, "updated_at", None))

        embed = discord.Embed(
            title=f"{name}",
            description=background if background != "â€”" else "",
            color=0x7C4DFF,
        )
        embed.set_author(name=f"{itx.user.display_name}", icon_url=getattr(itx.user.display_avatar, "url", None))
        embed.add_field(name="Pronouns", value=pronouns_display, inline=True)
        embed.add_field(name="Char Code", value=f"`{char_code}`", inline=True)
        embed.add_field(name="District", value=district, inline=True)

        if arche != "â€”":
            embed.add_field(name="Archetypes", value=arche, inline=False)

        stats_lines = [
            f"**STR** {s_str}  **VIT** {s_vit}  **END** {s_end}",
            f"**AGI** {s_agi}  **DEX** {s_dex}  **WIS** {s_wis}",
            f"**INT** {s_int}  **CHA** {s_cha}  **LUK** {s_luck}",
            f"**HP** {hp}",
        ]
        embed.add_field(name="Stats", value="\n".join(stats_lines), inline=False)
        embed.set_footer(text=f"Created {created} â€¢ Updated {updated}")

        await itx.followup.send(embed=embed)

    @app_commands.command(name="profile_of", description="Show another memberâ€™s LOWLIFE character profile.")
    @app_commands.describe(member="The member to view")
    async def profile_of(self, itx: discord.Interaction, member: Optional[discord.Member] = None):
        member = member or itx.user
        await itx.response.defer(ephemeral=False, thinking=False)
        ch = dal.get_primary_character_by_discord(str(member.id))
        if not ch:
            await itx.followup.send(f"{member.mention} has no character yet.", ephemeral=True)
            return

        name = getattr(ch, "name", "Unknown")
        char_code = getattr(ch, "char_id", "â€”")
        pronouns_display = _pronoun_label(getattr(ch, "pronouns", None))
        district = getattr(ch, "starting_district", None) or "â€”"
        arche = getattr(ch, "archetypes", None) or "â€”"
        background = getattr(ch, "background", None) or "â€”"
        s_str = getattr(ch, "str", 5)
        s_vit = getattr(ch, "vit", 5)
        s_end = getattr(ch, "end", 5)
        s_agi = getattr(ch, "agi", 5)
        s_dex = getattr(ch, "dex", 5)
        s_wis = getattr(ch, "wis", 5)
        s_int = getattr(ch, "intel", 5)
        s_cha = getattr(ch, "cha", 5)
        s_luck = getattr(ch, "luck", 5)
        hp = getattr(ch, "hp", 60)
        created = _fmt_dt(getattr(ch, "created_at", None))
        updated = _fmt_dt(getattr(ch, "updated_at", None))

        embed = discord.Embed(
            title=f"{name}",
            description=background if background != "â€”" else "",
            color=0x7C4DFF,
        )
        embed.set_author(name=f"{member.display_name}", icon_url=getattr(member.display_avatar, "url", None))
        embed.add_field(name="Pronouns", value=pronouns_display, inline=True)
        embed.add_field(name="Char Code", value=f"`{char_code}`", inline=True)
        embed.add_field(name="District", value=district, inline=True)
        if arche != "â€”":
            embed.add_field(name="Archetypes", value=arche, inline=False)
        stats_lines = [
            f"**STR** {s_str}  **VIT** {s_vit}  **END** {s_end}",
            f"**AGI** {s_agi}  **DEX** {s_dex}  **WIS** {s_wis}",
            f"**INT** {s_int}  **CHA** {s_cha}  **LUK** {s_luck}",
            f"**HP** {hp}",
        ]
        embed.add_field(name="Stats", value="\n".join(stats_lines), inline=False)
        embed.set_footer(text=f"Created {created} â€¢ Updated {updated}")
        await itx.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Profile(bot))
