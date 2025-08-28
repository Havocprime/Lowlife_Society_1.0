# GAME/src/admin/audit_paged.py
from __future__ import annotations
import json
import sqlite3
from typing import Optional, List, Tuple

import discord
from discord import app_commands
from discord.ext import commands

from src.core.settings import SETTINGS


PAGE_SIZE = 12


# ---------- small helpers ----------

def _to_int(x):
    try:
        return int(x)
    except Exception:
        return None


def _extract_text(d: dict) -> str:
    """Get a short text body from a payload dict."""
    for k in ("content", "message", "msg", "text", "body"):
        v = d.get(k)
        if isinstance(v, str) and v:
            return v
        if isinstance(v, dict):
            c = v.get("content")
            if isinstance(c, str) and c:
                return c
    return ""


def _ch_label(guild: Optional[discord.Guild], d: dict) -> str:
    """Return '#name' if channel is known, otherwise <#id> or '—'."""
    cid = d.get("channel_id") or d.get("channel") or d.get("cid")
    if isinstance(cid, dict):
        cid = cid.get("id")
    cid = _to_int(cid)
    if not cid:
        return "—"
    ch = guild.get_channel(cid) if guild else None
    return f"#{ch.name}" if ch else f"<#{cid}>"


def _trim(s: str, n: int = 110) -> str:
    s = s.replace("\n", " ").strip()
    return (s[: n - 1] + "…") if len(s) > n else s


# ---------- data access ----------

def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(SETTINGS.db_path)
    c.row_factory = sqlite3.Row
    return c


def fetch_count(kind: Optional[str], actor_id: Optional[int]) -> int:
    sql = "SELECT COUNT(*) AS n FROM events WHERE 1=1"
    args: List[object] = []
    if kind:
        sql += " AND type LIKE ?"
        args.append(kind + "%")
    if actor_id:
        sql += " AND actor_discord_id = ?"
        args.append(str(actor_id))
    with _conn() as c:
        r = c.execute(sql, args).fetchone()
        return int(r["n"] if r else 0)


def fetch_page(kind: Optional[str], actor_id: Optional[int], page: int, page_size: int
               ) -> List[Tuple[str, str, str]]:
    """
    Returns a list of (created_at, type, payload_json) newest-first.
    """
    sql_base = "FROM events WHERE 1=1"
    args: List[object] = []
    if kind:
        sql_base += " AND type LIKE ?"
        args.append(kind + "%")
    if actor_id:
        sql_base += " AND actor_discord_id = ?"
        args.append(str(actor_id))

    sql = f"SELECT created_at, type, payload_json {sql_base} ORDER BY created_at DESC LIMIT ? OFFSET ?"
    args_page = args + [page_size, page * page_size]

    with _conn() as c:
        rows = c.execute(sql, args_page).fetchall()
        return [(r["created_at"], r["type"], r["payload_json"]) for r in rows]


# ---------- UI (View) ----------

class AuditPagedView(discord.ui.View):
    def __init__(self, *, kind: Optional[str], actor_id: Optional[int], page: int, total: int):
        super().__init__(timeout=180)
        self.kind = kind
        self.actor_id = actor_id
        self.page = page
        self.total = total  # total rows
        self.page_count = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        # Disable buttons appropriately
        self.prev_button.disabled = (self.page <= 0)
        self.next_button.disabled = (self.page >= self.page_count - 1)

    async def _render_embed(self, interaction: discord.Interaction) -> discord.Embed:
        rows = fetch_page(self.kind, self.actor_id, self.page, PAGE_SIZE)

        pretty: List[str] = []
        for created_at, kind, payload in rows:
            try:
                data = (
                    json.loads(payload or "{}")
                    if isinstance(payload, (str, bytes))
                    else (payload or {})
                )
            except Exception:
                data = {}

            label = _ch_label(interaction.guild, data)
            txt = _extract_text(data)

            # extra niceties
            if kind == "message_edit" and not txt:
                txt = (data.get("after") or {}).get("content") or ""
            if kind == "message_delete" and not txt:
                txt = (data.get("before") or {}).get("content") or ""

            line = f"{created_at}  {kind}  @{label}  {_trim(txt) if txt else ''}".rstrip()
            if len(line) > 140:
                line = line[:137] + "…"
            pretty.append(line)

        desc = "\n".join(pretty) if pretty else "No recent actions found."
        while len(desc) > 1024 and len(pretty) > 1:
            pretty.pop()
            desc = "\n".join(pretty)

        title = f"Events — page {self.page + 1}/{self.page_count}"
        if self.kind:
            title += f" (kind: {self.kind})"
        if self.actor_id:
            title += f" (actor: {self.actor_id})"

        e = discord.Embed(title=title, description=desc, colour=discord.Color.blurple())
        return e

    @discord.ui.button(label="Prev", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
        self.prev_button.disabled = (self.page <= 0)
        self.next_button.disabled = (self.page >= self.page_count - 1)
        embed = await self._render_embed(interaction)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        if self.page < self.page_count - 1:
            self.page += 1
        self.prev_button.disabled = (self.page <= 0)
        self.next_button.disabled = (self.page >= self.page_count - 1)
        embed = await self._render_embed(interaction)
        await interaction.response.edit_message(embed=embed, view=self)


# ---------- Cog & command ----------

class AuditPagedCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="audit_recent_paged",
        description="View recent events with Prev/Next pagination.",
    )
    @app_commands.describe(
        kind="Optional kind prefix (e.g. 'message', 'econ')",
        actor="Optional actor to filter by",
    )
    async def audit_recent_paged(
        self,
        interaction: discord.Interaction,
        kind: Optional[str] = None,
        actor: Optional[discord.Member] = None,
    ):
        total = fetch_count(kind, actor.id if actor else None)
        view = AuditPagedView(kind=kind, actor_id=(actor.id if actor else None), page=0, total=total)
        embed = await view._render_embed(interaction)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AuditPagedCog(bot))
