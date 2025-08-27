# GAME/src/cogs/audit_log.py
from __future__ import annotations

import json
import os
from typing import Optional

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

# --- DB path: import from core (authoritative), with a safe fallback ---
try:
    from src.core.audit import _AUDIT_DB_PATH as AUDIT_DB_PATH  # same file used by ensure_db()
except Exception:
    # Fallback to GAME/data/audit.sqlite (two levels up from cogs/)
    AUDIT_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "audit.sqlite")
AUDIT_DB_PATH = os.path.normpath(AUDIT_DB_PATH)


class AuditLogCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _fetch_one(self, trace_id: str):
        async with aiosqlite.connect(AUDIT_DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM audit_log WHERE id = ? LIMIT 1", (trace_id,)
            ) as cur:
                return await cur.fetchone()

    async def _fetch_many(self, query: str, params: tuple, limit: int = 20):
        async with aiosqlite.connect(AUDIT_DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            sql = query + " ORDER BY ts DESC LIMIT ?"
            async with db.execute(sql, (*params, limit)) as cur:
                return await cur.fetchall()

    # ---- Commands (prefixed to avoid collisions) ----

    @app_commands.command(name="audit_trace", description="Trace an action by its Trace ID.")
    @app_commands.describe(id="The action/interaction Trace ID (UUID).")
    async def audit_trace(self, interaction: discord.Interaction, id: str):
        row = await self._fetch_one(id)
        if not row:
            await interaction.response.send_message(
                f"❌ No action found for ID `{id}`.", ephemeral=True
            )
            return

        details = {}
        try:
            details = json.loads(row["details"] or "{}")
        except Exception:
            pass

        embed = discord.Embed(title="🔎 Audit Trace", color=discord.Color.blurple())
        embed.add_field(name="Trace ID", value=f"`{row['id']}`", inline=False)
        embed.add_field(name="Action Type", value=row["action_type"] or "—", inline=True)
        embed.add_field(name="Command", value=row["command_name"] or "—", inline=True)
        embed.add_field(name="Timestamp (UTC, ms)", value=str(row["ts"]), inline=False)
        embed.add_field(name="Guild", value=str(row["guild_id"]), inline=True)
        embed.add_field(name="Channel", value=str(row["channel_id"]), inline=True)
        embed.add_field(name="Actor (user_id)", value=str(row["user_id"]), inline=True)
        if row["target_user_id"]:
            embed.add_field(name="Target (user_id)", value=str(row["target_user_id"]), inline=True)
        if details:
            pretty = json.dumps(details, indent=2, ensure_ascii=False)
            embed.add_field(name="Details", value=f"```json\n{pretty[:1000]}\n```", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="audit_trace_user", description="Show recent actions by a user.")
    @app_commands.describe(user="User to inspect", limit="Max rows (default 20, max 100)")
    async def audit_trace_user(
        self, interaction: discord.Interaction, user: discord.User, limit: Optional[int] = 20
    ):
        limit = max(1, min(limit or 20, 100))
        rows = await self._fetch_many(
            "SELECT * FROM audit_log WHERE user_id = ?", (user.id,), limit
        )
        if not rows:
            await interaction.response.send_message(
                f"ℹ️ No recent actions for {user.mention}.", ephemeral=True
            )
            return

        lines = [
            f"- `{r['id']}` • `{r['action_type']}` • ts={r['ts']} • cmd={r['command_name'] or '—'}"
            for r in rows
        ]
        await interaction.response.send_message(
            f"**Recent actions for {user.mention} (limit {limit})**\n" + "\n".join(lines[:50]),
            ephemeral=True,
        )

    @app_commands.command(
        name="audit_recent", description="List recent actions, optionally filter by action_type."
    )
    @app_commands.describe(
        action_type="Filter (e.g., duel.start, inventory.add)",
        limit="Max rows (default 20, max 100)",
    )
    async def audit_recent(
        self,
        interaction: discord.Interaction,
        action_type: Optional[str] = None,
        limit: Optional[int] = 20,
    ):
        limit = max(1, min(limit or 20, 100))
        if action_type:
            rows = await self._fetch_many(
                "SELECT * FROM audit_log WHERE action_type = ?", (action_type,), limit
            )
        else:
            rows = await self._fetch_many("SELECT * FROM audit_log WHERE 1=1", tuple(), limit)

        if not rows:
            await interaction.response.send_message("ℹ️ No recent actions found.", ephemeral=True)
            return

        lines = [
            f"- `{r['id']}` • `{r['action_type']}` • ts={r['ts']} • user={r['user_id']} • cmd={r['command_name'] or '—'}"
            for r in rows
        ]
        await interaction.response.send_message(
            f"**Recent actions (limit {limit})**\n" + "\n".join(lines[:50]), ephemeral=True
        )

    @app_commands.command(
        name="audit_trace_item", description="Find actions that touched a specific item_id."
    )
    @app_commands.describe(
        item_id="Item ID to search for in details", limit="Max rows (default 20, max 100)"
    )
    async def audit_trace_item(
        self, interaction: discord.Interaction, item_id: str, limit: Optional[int] = 20
    ):
        limit = max(1, min(limit or 20, 100))
        rows = await self._fetch_many(
            "SELECT * FROM audit_log WHERE details LIKE ?", (f"%{item_id}%",), limit
        )
        if not rows:
            await interaction.response.send_message(
                f"ℹ️ No actions referencing `item_id={item_id}`.", ephemeral=True
            )
            return

        lines = [
            f"- `{r['id']}` • `{r['action_type']}` • ts={r['ts']} • user={r['user_id']}"
            for r in rows
        ]
        await interaction.response.send_message(
            f"**Actions referencing item `{item_id}` (limit {limit})**\n" + "\n".join(lines[:50]),
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(AuditLogCog(bot))
