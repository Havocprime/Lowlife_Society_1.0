# FILE: src/bot/embed_demo.py
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from pathlib import Path

# ---- CONFIG ----
# Put your image at: assets/combat_template.png
# You can change this if you prefer a different path/filename.
IMAGE_PATH = Path("assets/combat_template.png")
ATTACH_NAME = "combat_template.png"   # name used by attachment:// URL

EMBED_COLOR = 0x8A2BE2  # purple-ish for Lowlife vibes

def _build_combat_embed(image_attach_name: str) -> discord.Embed:
    """
    Build a combat-style embed that fills every possible image field:
      - Author icon (via set_author)
      - Thumbnail (via set_thumbnail)
      - Main image (via set_image)
      - Footer icon (via set_footer)
    All use the same file via attachment://<name>.
    """
    attach_url = f"attachment://{image_attach_name}"

    e = discord.Embed(
        title="⚔️ Lowlife Combat — Template",
        description=(
            "**Attacker:** Havocprime\n"
            "**Defender:** AI Defender\n"
            "**Range:** Close\n"
            "**Status:** Grapple Established\n\n"
            "This embed demonstrates **all image-capable spots** filled at once."
        ),
        color=EMBED_COLOR,
    )

    # Author (supports an icon)
    e.set_author(
        name="Lowlife Combat Engine",
        url="https://discord.com",  # optional; can be omitted
        icon_url=attach_url,
    )

    # Thumbnail (small image at the right)
    e.set_thumbnail(url=attach_url)

    # Fields to mimic a combat readout
    e.add_field(name="Attacker Action", value="**Choke** (Stamina −6)", inline=True)
    e.add_field(name="Defender Reaction", value="**Struggle** (Stamina −4)", inline=True)
    e.add_field(name="Outcome", value="**Choke escalates** → Defender **Unconscious**", inline=False)

    e.add_field(name="Attacker HP", value="**82 / 100**", inline=True)
    e.add_field(name="Defender HP", value="**41 / 100**", inline=True)
    e.add_field(name="\u200b", value="\u200b", inline=False)

    # Main image (big image below description/fields)
    e.set_image(url=attach_url)

    # Footer (supports an icon)
    e.set_footer(text="Prototype • All image slots populated", icon_url=attach_url)

    return e


def register_embed_demo(tree: app_commands.CommandTree):
    """
    Call this from your bot's on_ready registration block, e.g.:
        from src.bot.embed_demo import register_embed_demo
        register_embed_demo(tree)
    """

    @tree.command(name="combat_embed_template", description="Show a combat embed with all image fields populated.")
    async def combat_embed_template(interaction: discord.Interaction):
        # Validate image existence and send a friendly error if missing
        if not IMAGE_PATH.exists():
            await interaction.response.send_message(
                content=(
                    f"⚠️ Image not found at `{IMAGE_PATH}`.\n"
                    "Please place your provided image there, or update IMAGE_PATH in `embed_demo.py`."
                ),
                ephemeral=True,
            )
            return

        # Create the embed
        embed = _build_combat_embed(ATTACH_NAME)

        # Attach the image file so attachment:// works for every image slot
        file = discord.File(IMAGE_PATH, filename=ATTACH_NAME)

        # Example action row just for context (not required for image testing)
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Choke", style=discord.ButtonStyle.danger, disabled=True))
        view.add_item(discord.ui.Button(label="Push", style=discord.ButtonStyle.secondary, disabled=True))
        view.add_item(discord.ui.Button(label="Mercy", style=discord.ButtonStyle.success, disabled=True))

        await interaction.response.send_message(embed=embed, file=file, view=view)

# Optional: standalone Cog loader (if you prefer cogs)
class EmbedDemo(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="combat_embed_template_cog", description="(Cog) Combat embed with all image fields populated.")
    async def combat_embed_template_cog(self, interaction: discord.Interaction):
        if not IMAGE_PATH.exists():
            await interaction.response.send_message(
                content=f"⚠️ Image not found at `{IMAGE_PATH}`.", ephemeral=True
            )
            return

        embed = _build_combat_embed(ATTACH_NAME)
        file = discord.File(IMAGE_PATH, filename=ATTACH_NAME)
        await interaction.response.send_message(embed=embed, file=file)

async def setup(bot: commands.Bot):
    await bot.add_cog(EmbedDemo(bot))
