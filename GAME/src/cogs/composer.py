from __future__ import annotations
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
from src.utils.image_composer import compose_layers

class Composer(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="compose", description="Composite transparent PNG layers and return a merged image.")
    @app_commands.describe(
        base="Base/background PNG (transparent OK)",
        overlay1="First overlay PNG (e.g., player icon)",
        overlay2="Second overlay PNG (e.g., HUD/damage)",
        pos="Positions for overlays: 'x1,y1;x2,y2' (optional)",
        size="Sizes for overlays: 'w1,h1;w2,h2' (optional)",
        text="Optional text: 'text|x|y|size' (repeat by separating with ;)"
    )
    async def compose(
        self,
        interaction: discord.Interaction,
        base: discord.Attachment,
        overlay1: Optional[discord.Attachment] = None,
        overlay2: Optional[discord.Attachment] = None,
        pos: Optional[str] = None,
        size: Optional[str] = None,
        text: Optional[str] = None,
    ):
        await interaction.response.defer(thinking=True, ephemeral=True)

        if not base.content_type or "image" not in base.content_type:
            return await interaction.followup.send("Base must be an image attachment (PNG).", ephemeral=True)

        base_bytes = await base.read()
        overlays = []
        if overlay1 and overlay1.content_type and "image" in overlay1.content_type:
            overlays.append(await overlay1.read())
        if overlay2 and overlay2.content_type and "image" in overlay2.content_type:
            overlays.append(await overlay2.read())

        positions = []
        if pos:
            try:
                for p in pos.split(";"):
                    x, y = p.split(",")
                    positions.append((int(x), int(y)))
            except Exception:
                return await interaction.followup.send("Bad pos format. Use: x1,y1;x2,y2", ephemeral=True)

        sizes = []
        if size:
            try:
                for s in size.split(";"):
                    w, h = s.split(",")
                    sizes.append((int(w), int(h)))
            except Exception:
                return await interaction.followup.send("Bad size format. Use: w1,h1;w2,h2", ephemeral=True)

        text_overlays = []
        if text:
            # Example: "32|120|-20|36; -24|160|40|28" → damage numbers at two spots
            # Or "DMG: -32|140|10|28"
            try:
                for t in text.split(";"):
                    t = t.strip()
                    if not t:
                        continue
                    parts = t.split("|")
                    # supports "text|x|y|size"
                    label = parts[0]
                    x = int(parts[1]) if len(parts) > 1 else 0
                    y = int(parts[2]) if len(parts) > 2 else 0
                    sz = int(parts[3]) if len(parts) > 3 else 28
                    text_overlays.append({"text": label, "xy": (x, y), "size": sz})
            except Exception:
                return await interaction.followup.send("Bad text format. Use: 'text|x|y|size; text2|x|y|size'", ephemeral=True)

        merged = compose_layers(
            base_bytes=base_bytes,
            overlay_bytes_list=overlays,
            positions=positions or None,
            sizes=sizes or None,
            text_overlays=text_overlays or None,
        )

        file = discord.File(fp=merged, filename="composite.png")
        embed = discord.Embed(title="Composite", description="Merged layers")
        embed.set_image(url="attachment://composite.png")
        await interaction.followup.send(file=file, embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Composer(bot))
