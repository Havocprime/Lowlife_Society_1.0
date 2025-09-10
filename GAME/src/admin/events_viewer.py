# GAME/src/admin/events_viewer.py
from __future__ import annotations

import io
import csv
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List

import discord
from discord import app_commands
from discord.ext import commands

# --------- admin gate (role OR admin perms) ----------
ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID", "0") or "0")


def _is_admin_member(m: discord.Member) -> bool:
    if ADMIN_ROLE_ID and any(r.id == ADMIN_ROLE_ID for r in m.roles):
        return True
    return bool(m.guild_permissions.administrator)


def admin_check():
    async def predicate(inter: discord.Interaction) -> bool:
        if isinstance(inter.user, discord.Member) and _is_admin_member(inter.user):
            return True
        await inter.response.send_message("Nope.", ephemeral=True)
        return False

    return app_commands.check(predicate)


# --------- DB helpers ----------
def _db_path() -> Path:
    """Prefer the custodian ledger DB if present; fallback to GAME/data/audit.sqlite."""
    try:
        from src.core.custodian import ledger  # type: ignore
        p = getattr(ledger, "DB_PATH", None)
        if p:
            return Path(p)
    except Exception:
        pass
    return Path(__file__).parents[2] / "data" / "audit.sqlite"


def _chan_mention(guild: Optional[discord.Guild], channel_id: Optional[int]) -> str:
    if not guild or not channel_id:
        return "â€”"
    ch = guild.get_channel(channel_id) or guild.get_thread(channel_id)
    return ch.mention if ch else f"<#{channel_id}>"


def _safe_sub(s: Optional[str], n: int = 120) -> str:
    if not s:
        return ""
    s = s.replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "â€¦"


# ======================================================================================
# Top-level GROUP: /events ...
# (Groups sometimes don't show if only defined as Cog attributes; registering here and
# adding it in setup() avoids that. We also add flat aliases in a Cog below.)
# ======================================================================================

events_group = app_commands.Group(
    name="events",
    description="Inspect bot events (read-only)",
)


@events_group.command(name="recent", description="Show recent events with optional filters.")
@app_commands.describe(
    limit="How many rows (1â€“50, default 15)",
    kind="Filter by event kind (e.g. message, presence, msg/create, member/join)",
    user="Only events by this user",
    channel="Only events in this channel",
    hours="Only events from the last N hours (default 24)",
)
@admin_check()
async def events_recent(
    inter: discord.Interaction,
    limit: app_commands.Range[int, 1, 50] = 15,
    kind: Optional[str] = None,
    user: Optional[discord.Member] = None,
    channel: Optional[discord.abc.GuildChannel] = None,
    hours: app_commands.Range[int, 1, 168] = 24,
):
    await inter.response.defer(ephemeral=True)

    dbp = _db_path()
    where: List[str] = []
    args: List[object] = []

    since_iso = (
        datetime.now(timezone.utc) - timedelta(hours=hours)
    ).isoformat(timespec="seconds").replace("+00:00", "Z")
    where.append("ts_utc >= ?")
    args.append(since_iso)

    if kind:
        where.append("LOWER(kind) = LOWER(?)")
        args.append(kind)
    if user:
        where.append("author_id = ?")
        args.append(int(user.id))
    if channel:
        where.append("channel_id = ?")
        args.append(int(getattr(channel, "id", 0)))

    where_sql = " WHERE " + " AND ".join(where) if where else ""
    sql = f"""
        SELECT id, ts_utc, kind, guild_id, channel_id, author_id, content
          FROM events
        {where_sql}
        ORDER BY id DESC
        LIMIT ?
    """
    args.append(int(limit))

    try:
        with sqlite3.connect(dbp) as con:
            rows = list(con.execute(sql, tuple(args)))
    except Exception as e:
        await inter.followup.send(
            f"DB read failed: `{type(e).__name__}: {e}` (DB: `{dbp}`)", ephemeral=True
        )
        return

    lines: List[str] = []
    for (rid, ts, k, gid, cid, uid, content) in rows:
        ch = _chan_mention(inter.guild, cid if isinstance(cid, int) else None)
        who = f"<@{uid}>" if uid else "â€”"
        lines.append(f"`#{rid}` `{ts}` â€¢ **{k}** â€¢ {who} @ {ch}\n{_safe_sub(content, 140)}")

    desc = "\n\n".join(lines) if lines else "_No events matched._"
    emb = discord.Embed(
        title=f"Events â€” recent (â‰¤{limit})",
        description=desc,
        colour=discord.Color.blurple(),
    )
    emb.set_footer(text=f"DB: {dbp} â€¢ since {since_iso}")
    await inter.followup.send(embed=emb, ephemeral=True)


@events_group.command(name="stats", description="Counts by kind over the last N hours.")
@app_commands.describe(hours="Time window in hours (default 24)")
@admin_check()
async def events_stats(
    inter: discord.Interaction,
    hours: app_commands.Range[int, 1, 168] = 24,
):
    await inter.response.defer(ephemeral=True)

    since_iso = (
        datetime.now(timezone.utc) - timedelta(hours=hours)
    ).isoformat(timespec="seconds").replace("+00:00", "Z")
    dbp = _db_path()
    try:
        with sqlite3.connect(dbp) as con:
            stats = list(
                con.execute(
                    """
                    SELECT kind, COUNT(*) AS n
                      FROM events
                     WHERE ts_utc >= ?
                     GROUP BY kind
                     ORDER BY n DESC
                    """,
                    (since_iso,),
                )
            )
    except Exception as e:
        await inter.followup.send(
            f"DB read failed: `{type(e).__name__}: {e}` (DB: `{dbp}`)", ephemeral=True
        )
        return

    if not stats:
        await inter.followup.send("No rows in that window.", ephemeral=True)
        return

    lines = [f"**{k or 'â€”'}** â€” `{n}`" for (k, n) in stats]
    emb = discord.Embed(
        title=f"Events â€” stats (last {hours}h)",
        description="\n".join(lines),
        colour=discord.Color.blurple(),
    )
    emb.set_footer(text=f"DB: {dbp} â€¢ since {since_iso}")
    await inter.followup.send(embed=emb, ephemeral=True)


# -------- NEW: /events export (CSV) --------
@events_group.command(name="export", description="Export filtered events to CSV.")
@app_commands.describe(
    limit="How many rows to export (1â€“500, default 200)",
    kind="Filter by event kind",
    user="Only events by this user",
    channel="Only events in this channel",
    hours="Only events from the last N hours (default 24)",
    filename="Optional filename for the CSV (default: events_export.csv)",
)
@admin_check()
async def events_export(
    inter: discord.Interaction,
    limit: app_commands.Range[int, 1, 500] = 200,
    kind: Optional[str] = None,
    user: Optional[discord.Member] = None,
    channel: Optional[discord.abc.GuildChannel] = None,
    hours: app_commands.Range[int, 1, 168] = 24,
    filename: Optional[str] = None,
):
    await inter.response.defer(ephemeral=True)

    dbp = _db_path()
    where: List[str] = []
    args: List[object] = []

    since_iso = (
        datetime.now(timezone.utc) - timedelta(hours=hours)
    ).isoformat(timespec="seconds").replace("+00:00", "Z")
    where.append("ts_utc >= ?")
    args.append(since_iso)

    if kind:
        where.append("LOWER(kind) = LOWER(?)")
        args.append(kind)
    if user:
        where.append("author_id = ?")
        args.append(int(user.id))
    if channel:
        where.append("channel_id = ?")
        args.append(int(getattr(channel, "id", 0)))

    where_sql = " WHERE " + " AND ".join(where) if where else ""
    sql = f"""
        SELECT id, ts_utc, kind, guild_id, channel_id, author_id, content, payload
          FROM events
        {where_sql}
        ORDER BY id DESC
        LIMIT ?
    """
    args.append(int(limit))

    try:
        with sqlite3.connect(dbp) as con:
            rows = list(con.execute(sql, tuple(args)))
    except Exception as e:
        await inter.followup.send(
            f"DB read failed: `{type(e).__name__}: {e}` (DB: `{dbp}`)", ephemeral=True
        )
        return

    # Build CSV
    s = io.StringIO()
    w = csv.writer(s)
    w.writerow(["id", "ts_utc", "kind", "guild_id", "channel_id", "author_id", "content", "payload"])
    for r in rows:
        w.writerow(r)

    blob = s.getvalue().encode("utf-8")
    name = (filename or "events_export.csv").strip()
    if not name.lower().endswith(".csv"):
        name += ".csv"

    await inter.followup.send(
        content=f"Exported `{len(rows)}` rows from `{dbp}` (since `{since_iso}`)",
        file=discord.File(fp=io.BytesIO(blob), filename=name),
        ephemeral=True,
    )


# ======================================================================================
# Flat aliases so they always show up in the picker:
#   /events_recent, /events_stats, /events_export
# ======================================================================================

class EventsViewer(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="events_recent", description="[Alias] Show recent events")
    @app_commands.describe(
        limit="How many rows (1â€“50, default 15)",
        kind="Filter by event kind",
        user="Only events by this user",
        channel="Only events in this channel",
        hours="Only events from the last N hours (default 24)",
    )
    @admin_check()
    async def events_recent_alias(
        self,
        inter: discord.Interaction,
        limit: app_commands.Range[int, 1, 50] = 15,
        kind: Optional[str] = None,
        user: Optional[discord.Member] = None,
        channel: Optional[discord.abc.GuildChannel] = None,
        hours: app_commands.Range[int, 1, 168] = 24,
    ):
        await events_recent.callback(  # reuse group handler
            inter, limit=limit, kind=kind, user=user, channel=channel, hours=hours
        )

    @app_commands.command(name="events_stats", description="[Alias] Show event counts by kind")
    @app_commands.describe(hours="Time window in hours (default 24)")
    @admin_check()
    async def events_stats_alias(
        self,
        inter: discord.Interaction,
        hours: app_commands.Range[int, 1, 168] = 24,
    ):
        await events_stats.callback(inter, hours=hours)

    @app_commands.command(name="events_export", description="[Alias] Export filtered events to CSV")
    @app_commands.describe(
        limit="How many rows to export (1â€“500, default 200)",
        kind="Filter by event kind",
        user="Only events by this user",
        channel="Only events in this channel",
        hours="Only events from the last N hours (default 24)",
        filename="Optional filename for the CSV (default: events_export.csv)",
    )
    @admin_check()
    async def events_export_alias(
        self,
        inter: discord.Interaction,
        limit: app_commands.Range[int, 1, 500] = 200,
        kind: Optional[str] = None,
        user: Optional[discord.Member] = None,
        channel: Optional[discord.abc.GuildChannel] = None,
        hours: app_commands.Range[int, 1, 168] = 24,
        filename: Optional[str] = None,
    ):
        await events_export.callback(
            inter,
            limit=limit,
            kind=kind,
            user=user,
            channel=channel,
            hours=hours,
            filename=filename,
        )


# ---------- extension setup ----------
async def setup(bot: commands.Bot):
    # Register the group explicitly (reliable) and add the alias Cog.
    bot.tree.add_command(events_group)
    await bot.add_cog(EventsViewer(bot))
