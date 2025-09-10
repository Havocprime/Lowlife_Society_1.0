# GAME/src/cogs/tags_seed_cmd.py
from __future__ import annotations
import inspect, sqlite3, traceback
import discord
from discord import app_commands
from discord.ext import commands

from src.systems.tags import dal, seed
from src.systems.tags.schema import ensure_tags_schema

class TagSeedCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.default_permissions(manage_guild=True)
    @app_commands.command(
        name="tag_seed",
        description="Seed default tags (Bleeding, Gunshot Wound) into the tag catalog."
    )
    @app_commands.describe(force="Seed even if the catalog is not empty")
    async def tag_seed_cmd(self, itx: discord.Interaction, force: bool = False):
        try:
            ensure_tags_schema()

            # Tolerate either seed_defaults() or seed_defaults(force=...)
            sig = inspect.signature(seed.seed_defaults)
            if "force" in sig.parameters:
                n = seed.seed_defaults(force=force) or 0
            else:
                n = seed.seed_defaults() or 0

            # Verify counts after seeding
            with sqlite3.connect(dal.DB_PATH) as con:
                (n_tags,) = con.execute("SELECT COUNT(*) FROM tags").fetchone()
            await itx.response.send_message(
                f"âœ… Seeded **{n}** tag(s). Catalog now has **{n_tags}** rows. DB=`{dal.DB_PATH}`",
                ephemeral=True,
            )
        except Exception:
            tb = traceback.format_exc()
            await itx.response.send_message(
                f"âš ï¸ Seeding failed. Check logs.\n```\n{tb}\n```",
                ephemeral=True,
            )

class TagDebug(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.default_permissions(manage_guild=True)
    @app_commands.command(
        name="tag_debug",
        description="Show tag DB path and counts (catalog + instances)."
    )
    async def tag_debug_cmd(self, itx: discord.Interaction):
        with sqlite3.connect(dal.DB_PATH) as con:
            (n_tags,) = con.execute("SELECT COUNT(*) FROM tags").fetchone()
            (n_inst,) = con.execute("SELECT COUNT(*) FROM tag_instances").fetchone()
        await itx.response.send_message(
            f"DB: `{dal.DB_PATH}`\nCatalog rows: **{n_tags}**\nInstances: **{n_inst}**",
            ephemeral=True,
        )

async def setup(bot: commands.Bot):
    # IMPORTANT: add BOTH cogs so both commands register
    await bot.add_cog(TagSeedCog(bot))
    await bot.add_cog(TagDebug(bot))
