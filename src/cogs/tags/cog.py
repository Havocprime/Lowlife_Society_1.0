# src/cogs/tags/cog.py
from __future__ import annotations
import time, sqlite3, discord
from discord import app_commands
from discord.ext import commands
from .schema import ensure_schema, seed
from .catalog import LIVE_PRESETS
from ..util.db import get_db  # tiny helper weâ€™ll add below
from ..util.owners import owner_tuple  # tiny helper weâ€™ll add below

class TagsCog(commands.Cog):
    """Tag system with seed + apply/list/clear and dev helpers."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        with get_db() as db:
            ensure_schema(db)
            # Keep the startup logs you liked:
            n_keys, n_live = seed(db)
            bot.logger.info(f"tags.schema: ensured tables + indices (migrations applied if needed).")
            bot.logger.info(f"tags.cog: Seeded {n_keys} tag key(s) into tag_keys (idempotent).")
            bot.logger.info("tags.cog: Tags schema ensured and tag_keys seeded.")

    group = app_commands.Group(name="tag", description="Manage gameplay tags")

    @group.command(name="seed", description="Seed/refresh tag catalog")
    async def tag_seed(self, interaction: discord.Interaction):
        with get_db() as db:
            ensure_schema(db)
            n_keys, n_live = seed(db)
        await interaction.response.send_message(
            f"ðŸ“š `tag_keys` present â€” {n_keys} key(s).\nðŸ§ª `tags` table present â€” seeded {n_live} live preset(s).",
            ephemeral=True,
        )

    @group.command(name="catalog", description="Show catalog keys")
    async def tag_catalog(self, interaction: discord.Interaction):
        with get_db() as db:
            rows = db.execute("SELECT name, family, kind, max_stacks FROM tag_keys ORDER BY name").fetchall()
        lines = [f"â€¢ **{r[0]}** *(family: {r[1]}, {r[2]}, max:{r[3]})*" for r in rows]
        msg = "ðŸ“š **tag_keys present** â€” " + f"{len(rows)} key(s).\n" + "\n".join(lines[:25])
        await interaction.response.send_message(msg, ephemeral=True)

    @group.command(name="add", description="Apply a live tag to yourself")
    @app_commands.describe(key="Tag key to apply (e.g., Bleeding)")
    async def tag_add(self, interaction: discord.Interaction, key: str):
        owner = owner_tuple(interaction.user)  # ("discord", user_id)
        with get_db() as db:
            row = db.execute("SELECT name, family, kind, max_stacks, negative, duration_s, fatal_on_expire, tick_s "
                             "FROM tag_keys WHERE name = ?", (key,)).fetchone()
            if not row:
                await interaction.response.send_message(f"âŒ Tag `{key}` not found in catalog.", ephemeral=True)
                return
            now = int(time.time())
            expires = None
            if row[5] is not None:
                expires = now + int(row[5])
            db.execute(
                """
                INSERT INTO tags (owner_type, owner_id, key, family, kind, stacks, negative, expires_at, fatal_on_expire)
                VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)
                ON CONFLICT(owner_type, owner_id, key) DO UPDATE SET
                    stacks = MIN(tags.stacks + 1, ?),
                    expires_at = CASE WHEN excluded.expires_at IS NULL THEN tags.expires_at ELSE excluded.expires_at END
                """,
                (owner[0], owner[1], row[0], row[1], row[2], int(row[4]), expires, int(row[6]), row[3]),
            )
            db.commit()
        await interaction.response.send_message(f"âœ… **{key}** Ã—1 âžœ **{interaction.user.mention}**", ephemeral=True)

    @group.command(name="list", description="List your active tags")
    async def tag_list(self, interaction: discord.Interaction):
        owner = owner_tuple(interaction.user)
        with get_db() as db:
            rows = db.execute(
                "SELECT key, kind, negative, stacks, COALESCE(expires_at, 0) FROM tags "
                "WHERE owner_type=? AND owner_id=? ORDER BY key",
                owner,
            ).fetchall()
        if not rows:
            await interaction.response.send_message("â„¹ï¸ No active tags.", ephemeral=True)
            return
        lines = []
        for k, kind, neg, s, exp in rows:
            pol = "negative" if neg else "positive"
            exp_t = "âˆž" if exp == 0 else f"{max(0, exp - int(time.time()))}s"
            lines.append(f"â€¢ **{k}**  *({kind} â€“ {pol})*  Ã—{s}  â€¢ expires in {exp_t}")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @group.command(name="clear", description="Clear ALL your tags")
    async def tag_clear(self, interaction: discord.Interaction):
        owner = owner_tuple(interaction.user)
        with get_db() as db:
            n = db.execute("DELETE FROM tags WHERE owner_type=? AND owner_id=?", owner).rowcount
            db.commit()
        await interaction.response.send_message(f"ðŸ§¹ Cleared **{n}** tag(s).", ephemeral=True)

    # --- Dev helpers you used in testing ------------------------------------

    @app_commands.command(name="dev_gunshot", description="Apply Gunshot Wound + Bleeding")
    async def dev_gunshot(self, interaction: discord.Interaction):
        owner = owner_tuple(interaction.user)
        with get_db() as db:
            for preset in ("Gunshot Wound", "Bleeding"):
                db.execute("INSERT OR IGNORE INTO tag_keys(name, family, kind, max_stacks, negative, duration_s, fatal_on_expire, tick_s) "
                           "VALUES (?, 'event', 'event', 1, 1, NULL, 0, 60)", (preset,))
            db.commit()
        await self.tag_add(interaction, key="Gunshot Wound")
        await self.tag_add(interaction, key="Bleeding")

async def setup(bot: commands.Bot):
    await bot.add_cog(TagsCog(bot))
