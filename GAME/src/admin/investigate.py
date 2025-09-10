# GAME/src/admin/investigate.py
from __future__ import annotations
import os
import io
import csv
from typing import Optional, Literal

import discord
from discord import app_commands
from discord.ext import commands


ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID", "0") or "0")  # optional role gate


def is_admin():
    async def predicate(inter: discord.Interaction) -> bool:
        member = inter.user if isinstance(inter.user, discord.Member) else None
        if not member:
            return False
        if ADMIN_ROLE_ID and any(r.id == ADMIN_ROLE_ID for r in member.roles):
            return True
        return member.guild_permissions.administrator
    return app_commands.check(predicate)


class InvestigateCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # /investigate user @mention [action_type] [limit]
    @app_commands.command(name="investigate", description="Timeline of a user's recent actions.")
    @is_admin()
    async def investigate_user(
        self,
        inter: discord.Interaction,
        user: discord.Member,
        action_type: Optional[str] = None,
        limit: app_commands.Range[int, 1, 200] = 50,
    ):
        """Shows recent audited events for a specific user."""
        await inter.response.defer(ephemeral=True)

        # Lazy-import to avoid partial-init circular imports
        from src.core import audit as audit_core

        rows = await audit_core.query_events(
            guild_id=inter.guild_id,
            user_id=user.id,
            action_type=action_type,
            limit=limit,
        )

        if not rows:
            await inter.followup.send("No events found.", ephemeral=True)
            return

        # Build compact, readable chunks
        chunks: list[str] = []
        for r in rows:
            ts = r.get("ts")
            et = r.get("action_type") or "â€”"
            ch = f"<#{r['channel_id']}>" if r.get("channel_id") else "â€”"
            msg = (r.get("content") or "")[:180]
            chunks.append(f"`{ts}` â€¢ **{et}** â€¢ {ch}\n{msg}")

        # Paginate every ~8 lines
        page_size = 8
        pages = [chunks[i : i + page_size] for i in range(0, len(chunks), page_size)]
        for i, page in enumerate(pages, 1):
            embed = discord.Embed(
                title=f"Investigation: {user} [{i}/{len(pages)}]",
                description="\n\n".join(page),
                color=discord.Color.blurple(),
            )
            await inter.followup.send(embed=embed, ephemeral=True)

    # /audit_search query:"text" [action_type] [channel]
    @app_commands.command(name="audit_search", description="Full-text search across audited content.")
    @is_admin()
    async def audit_search(
        self,
        inter: discord.Interaction,
        query: str,
        action_type: Optional[str] = None,
        channel: Optional[discord.abc.GuildChannel] = None,
        limit: app_commands.Range[int, 1, 200] = 50,
        export: Optional[Literal["csv"]] = None,
    ):
        """Searches audit log by text (FTS) plus optional filters."""
        await inter.response.defer(ephemeral=True)
        from src.core import audit as audit_core

        rows = await audit_core.query_events(
            guild_id=inter.guild_id,
            channel_id=getattr(channel, "id", None) if channel else None,
            action_type=action_type,
            q=query,
            limit=limit,
        )

        if not rows:
            await inter.followup.send("No matches.", ephemeral=True)
            return

        if export == "csv":
            # Include some details pulled from details_obj for convenience.
            buf = io.StringIO()
            fieldnames = [
                "ts",
                "action_type",
                "guild_id",
                "channel_id",
                "user_id",
                "target_user_id",
                "command_name",
                "message_id",
                "content",
            ]
            w = csv.DictWriter(buf, fieldnames=fieldnames)
            w.writeheader()
            for r in rows:
                details = r.get("details_obj") or {}
                w.writerow(
                    {
                        "ts": r.get("ts"),
                        "action_type": r.get("action_type"),
                        "guild_id": r.get("guild_id"),
                        "channel_id": r.get("channel_id"),
                        "user_id": r.get("user_id"),
                        "target_user_id": r.get("target_user_id"),
                        "command_name": r.get("command_name"),
                        "message_id": details.get("message_id"),
                        "content": r.get("content", ""),
                    }
                )
            data = io.BytesIO(buf.getvalue().encode("utf-8"))
            await inter.followup.send(file=discord.File(data, filename="audit_export.csv"), ephemeral=True)
            return

        # Inline results (first 50)
        chunks: list[str] = []
        for r in rows[:50]:
            ts = r.get("ts")
            et = r.get("action_type") or "â€”"
            ch = f"<#{r['channel_id']}>" if r.get("channel_id") else "â€”"
            msg = (r.get("content") or "")[:200]
            chunks.append(f"`{ts}` â€¢ **{et}** â€¢ {ch}\n{msg}")

        embed = discord.Embed(
            title=f"Search: â€œ{query}â€",
            description="\n\n".join(chunks),
            color=discord.Color.blurple(),
        )
        await inter.followup.send(embed=embed, ephemeral=True)

    # /message_trace message_id
    @app_commands.command(name="message_trace", description="Follow a message's lifecycle (edits, reacts, delete).")
    @is_admin()
    async def message_trace(self, inter: discord.Interaction, message_id: str):
        """Collects all audit entries that reference a given message ID (works without FTS)."""
        await inter.response.defer(ephemeral=True)
        from src.core import audit as audit_core

        # Pull a reasonable window and filter by message_id from details_obj
        window = await audit_core.query_events(guild_id=inter.guild_id, limit=500)
        mid = int(message_id)
        rows = []
        for r in window:
            d = r.get("details_obj") or {}
            if d.get("message_id") == mid:
                rows.append(r)
            # include bulk deletes that list many IDs
            ids = d.get("message_ids")
            if isinstance(ids, (list, tuple)) and mid in ids:
                rows.append(r)

        if not rows:
            await inter.followup.send("No audit trail for that message.", ephemeral=True)
            return

        rows.sort(key=lambda r: r.get("ts", 0))  # chronological

        lines: list[str] = []
        for r in rows:
            ts = r.get("ts")
            et = r.get("action_type") or "â€”"
            ch = f"<#{r['channel_id']}>" if r.get("channel_id") else "â€”"
            lines.append(f"`{ts}` â€¢ **{et}** â€¢ {ch}")
            c = r.get("content") or ""
            if c:
                lines.append(f"> {c[:180]}")

        # paginate if long
        page_size = 12
        for i in range(0, len(lines), page_size):
            embed = discord.Embed(
                title=f"Message Trace {message_id}",
                description="\n".join(lines[i : i + page_size]),
                color=discord.Color.blurple(),
            )
            await inter.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(InvestigateCog(bot))
