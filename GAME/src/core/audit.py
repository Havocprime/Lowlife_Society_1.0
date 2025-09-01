# GAME/src/admin/audit.py
from __future__ import annotations

import os
from typing import Optional, List, Callable, Any
import functools
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone
from src.core.custodian import ledger


ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID", "0") or "0")


# ---------- helpers ----------
def is_admin():
    async def predicate(inter: discord.Interaction) -> bool:
        # Allow configured admin role OR server administrators
        if isinstance(inter.user, discord.Member):
            if ADMIN_ROLE_ID and any(r.id == ADMIN_ROLE_ID for r in inter.user.roles):
                return True
            if inter.user.guild_permissions.administrator:
                return True
        return False
    return app_commands.check(predicate)


def _chan_mention(guild: Optional[discord.Guild], channel_id: Optional[int]) -> str:
    if not guild or not channel_id:
        return "—"
    ch = guild.get_channel(channel_id) or guild.get_thread(channel_id)
    return ch.mention if ch else f"#deleted({channel_id})"


def _preview(text: Optional[str], limit: int = 180) -> str:
    if not text:
        return ""
    t = text.replace("\n", " ").strip()
    return (t[:limit] + "…") if len(t) > limit else t


def _ts_iso(ts_ms: Optional[int]) -> str:
    try:
        return datetime.fromtimestamp(int(ts_ms) / 1000, tz=timezone.utc).isoformat(timespec="seconds")
    except Exception:
        return str(ts_ms or "")


# ---------- unified decorator ----------
def _resolve_interaction(args, kwargs):
    for a in args:
        if getattr(a, "response", None) and getattr(a, "user", None):
            return a
    itx = kwargs.get("interaction")
    if getattr(itx, "response", None) and getattr(itx, "user", None):
        return itx
    return None

def _maybe_call(fn_or_val, interaction, **kw):
    if callable(fn_or_val):
        try:
            return fn_or_val(interaction, **kw)
        except TypeError:
            return fn_or_val(interaction)
    return fn_or_val

def audit_event(
    name_or_none: Optional[str] = None,
    *,
    action_type: Optional[str] = None,
    target_user: Optional[Callable[..., Any]] = None,
    extra: Optional[Callable[..., Any] | dict] = None,
):
    """
    Flexible decorator for auditing.

    Usages:
      @audit_event("admin.do_thing")
      @audit_event(action_type="admin.do_thing",
                   target_user=lambda itx, user=None: user,
                   extra=lambda itx: {...})
    """
    # Handle bare @audit_event without args
    if callable(name_or_none) and action_type is None:
        fn = name_or_none
        derived = f"{getattr(fn, '__module__', 'unknown')}.{getattr(fn, '__name__', 'callback')}"
        return audit_event(action_type=derived)(fn)

    action = action_type or name_or_none or "unspecified"

    def deco(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            interaction = _resolve_interaction(args, kwargs)
            actor_id = None
            guild_id = None
            channel_id = None
            if interaction is not None:
                try:
                    actor_id = str(getattr(interaction.user, "id", None))
                except Exception:
                    pass
                try:
                    guild_id = str(getattr(interaction.guild, "id", None)) if getattr(interaction, "guild", None) else None
                except Exception:
                    pass
                try:
                    channel_id = str(getattr(interaction.channel, "id", None)) if getattr(interaction, "channel", None) else None
                except Exception:
                    pass

            tu = _maybe_call(target_user, interaction, **kwargs) if target_user else None
            if hasattr(tu, "id"):
                tu = str(tu.id)
            elif tu is not None:
                tu = str(tu)

            extra_ctx = _maybe_call(extra, interaction, **kwargs) if extra else {}
            if not isinstance(extra_ctx, dict):
                extra_ctx = {"extra": extra_ctx}

            ctx = {
                "fn": f"{getattr(fn, '__module__', '?')}.{getattr(fn, '__name__', '?')}",
                "kwargs_keys": list(kwargs.keys())[:20],
            }
            ctx.update(extra_ctx or {})

            try:
                ledger.log(
                    actor_id=str(actor_id or "system"),
                    actor_type="user" if actor_id else "system",
                    action=str(action),
                    context_json=ctx,
                    target_id=tu,
                    guild_id=guild_id,
                    channel_id=channel_id,
                )
            except Exception:
                # Never block the command on audit failure
                pass

            return await fn(*args, **kwargs)
        return wrapper
    return deco


# ---------- pagination view ----------
class AuditPager(discord.ui.View):
    def __init__(
        self,
        rows: List[dict],
        guild: discord.Guild | None,
        page_size: int = 10,
        author_id: int | None = None,
        *,
        timeout: int | None = 180
    ):
        super().__init__(timeout=timeout)
        self.rows = rows
        self.guild = guild
        self.page_size = max(1, min(page_size, 25))
        self.page = 0
        self.author_id = author_id
        self._sync_buttons()

    def _sync_buttons(self):
        total_pages = max(1, (len(self.rows) + self.page_size - 1) // self.page_size)
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.custom_id == "prev":
                    child.disabled = self.page <= 0
                elif child.custom_id == "next":
                    child.disabled = self.page >= (total_pages - 1)

    def _page_slice(self) -> List[dict]:
        start = self.page * self.page_size
        end = start + self.page_size
        return self.rows[start:end]

    def build_embed(self) -> discord.Embed:
        total = len(self.rows)
        total_pages = max(1, (total + self.page_size - 1) // self.page_size)
        lines: List[str] = []
        for r in self._page_slice():
            ts = _ts_iso(r.get("ts"))
            et = r.get("action_type") or "—"
            chid = r.get("channel_id")
            msg = _preview(r.get("content") or "")
            line = f"`{ts}` • **{et}** • {_chan_mention(self.guild, chid)}\n{msg}"
            lines.append(line)
        desc = "\n\n".join(lines) if lines else "_No events._"
        emb = discord.Embed(
            title=f"Audit Recent ({self.page + 1}/{total_pages})",
            description=desc,
            color=discord.Color.blurple()
        )
        emb.set_footer(text=f"{total} events • page size {self.page_size}")
        return emb

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.author_id and interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the invoker can use these controls.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Prev", style=discord.ButtonStyle.secondary, custom_id="prev")
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, custom_id="next")
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        total_pages = max(1, (len(self.rows) + self.page_size - 1) // self.page_size)
        if self.page < total_pages - 1:
            self.page += 1
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)


# ---------- Cog ----------
class AuditCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="audit_recent", description="Show recent audit events (not paged).")
    @is_admin()
    async def audit_recent(
        self,
        inter: discord.Interaction,
        limit: app_commands.Range[int, 1, 25] = 10,
        user: Optional[discord.Member] = None,
        channel: Optional[discord.abc.GuildChannel] = None,
        action_type: Optional[str] = None,
        command_name: Optional[str] = None,
        q: Optional[str] = None,
    ):
        await inter.response.defer(ephemeral=True)
        rows = await query_events(
            guild_id=inter.guild_id,
            user_id=(user.id if user else None),
            channel_id=(getattr(channel, "id", None) if channel else None),
            action_type=action_type,
            command_name=command_name,
            q=q,
            limit=limit,
        )
        lines: List[str] = []
        for r in rows:
            ts = _ts_iso(r.get("ts"))
            et = r.get("action_type") or "—"
            chid = r.get("channel_id")
            msg = _preview(r.get("content") or "")
            lines.append(f"`{ts}` • **{et}** • {_chan_mention(inter.guild, chid)}\n{msg}")
        emb = discord.Embed(
            title="Audit Recent",
            description="\n\n".join(lines) if lines else "_No events._",
            color=discord.Color.blurple(),
        )
        await inter.followup.send(embed=emb, ephemeral=True)

    @app_commands.command(name="audit_recent_paged", description="Browse recent audit events with paging.")
    @is_admin()
    async def audit_recent_paged(
        self,
        inter: discord.Interaction,
        page_size: app_commands.Range[int, 5, 25] = 10,
        user: Optional[discord.Member] = None,
        channel: Optional[discord.abc.GuildChannel] = None,
        action_type: Optional[str] = None,
        command_name: Optional[str] = None,
        q: Optional[str] = None,
        limit: app_commands.Range[int, 20, 500] = 200,
    ):
        await inter.response.defer(ephemeral=True)
        rows = await query_events(
            guild_id=inter.guild_id,
            user_id=(user.id if user else None),
            channel_id=(getattr(channel, "id", None) if channel else None),
            action_type=action_type,
            command_name=command_name,
            q=q,
            limit=limit,
        )
        view = AuditPager(rows=rows, guild=inter.guild, page_size=page_size, author_id=inter.user.id)
        await inter.followup.send(embed=view.build_embed(), view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AuditCog(bot))
