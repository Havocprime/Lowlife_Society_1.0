# GAME/src/cogs/tags_admin.py
from __future__ import annotations

import logging, inspect, traceback, uuid
from typing import Optional, Callable, Tuple

import discord
from discord import app_commands, Interaction
from discord.ext import commands

from src.tags.service_runtime import TagRuntime
from src.systems.tags import dal as tag_dal
from src.systems.tags.api import apply_tag  # unified API used by the new engine
from src.db import dal as core_dal

log = logging.getLogger("tags.admin")

# ------------- helpers -------------

def _conn():
    for name in ("write_conn", "conn", "_conn", "get_conn"):
        fn = getattr(core_dal, name, None)
        if callable(fn):
            return fn()
    raise RuntimeError("No DAL connection factory found")

def _resolve_owner(user: discord.abc.User) -> Tuple[str, int]:
    """Prefer a canonical player id; fall back to ('discord', discord_id)."""
    candidates: list[tuple[str, Callable]] = []
    for name in ("get_or_create_player", "get_or_create_account", "player_get_or_create", "ensure_player"):
        fn = getattr(core_dal, name, None)
        if callable(fn):
            candidates.append((name, fn))

    discord_id = int(user.id)

    for name, fn in candidates:
        try:
            try:
                pid = fn(discord_id=discord_id)
            except TypeError:
                pid = fn(discord_id)
            return ("player", int(pid))
        except Exception as e:
            log.debug("DAL helper %s failed: %r", name, e)

    return ("discord", discord_id)

async def _maybe_async(callable_obj, *args, **kwargs):
    if inspect.iscoroutinefunction(callable_obj):
        return await callable_obj(*args, **kwargs)
    return callable_obj(*args, **kwargs)

# ------------- cog -------------

class TagsAdmin(commands.Cog):
    """Admin utilities for tag management (power tools)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.runtime = TagRuntime()

    async def cog_load(self):
        start = getattr(self.runtime, "start", None)
        if callable(start):
            try:
                await _maybe_async(start)
            except Exception:
                log.exception("TagRuntime.start failed")

    async def cog_unload(self):
        stop = getattr(self.runtime, "stop", None)
        if callable(stop):
            try:
                await _maybe_async(stop)
            except Exception:
                pass

    # ---------- admin: apply ----------

    @app_commands.command(name="tag_apply", description="(Admin) Apply a tag to a user/anchor")
    @app_commands.describe(
        tag_name="Catalog name (e.g., Bleeding)",
        anchor_path="Where to attach (e.g., body:Left Bicep or entity)",
        stacks="Stacks to add",
        duration_ms="Optional duration override in ms",
        user="Target user (defaults to you)",
    )
    async def tag_apply_cmd(
        self,
        itx: Interaction,
        tag_name: str,
        anchor_path: str = "entity",
        stacks: int = 1,
        duration_ms: Optional[int] = None,
        user: Optional[discord.Member] = None,
    ):
        await itx.response.defer(ephemeral=True)
        trace = uuid.uuid4().hex[:8]

        try:
            target = user or itx.user
            owner_kind, owner_id = _resolve_owner(target)

            iid = apply_tag(
                owner_kind=owner_kind,
                owner_id=owner_id,
                anchor_path=anchor_path,
                tag_name=tag_name,
                stacks=max(1, int(stacks)),
                duration_ms=duration_ms,
                source_kind="cmd",
                source_ref="admin_apply",
            )

            await itx.followup.send(
                f"✅ `{tag_name}` x{stacks} → `{anchor_path}` on {target.mention} "
                f"(owner=`{owner_kind}:{owner_id}`, instance #{iid})",
                ephemeral=True,
            )

        except Exception:
            log.error("[tag_apply] trace=%s\n%s", trace, traceback.format_exc())
            await itx.followup.send(f"⚠️ Apply failed. Trace `{trace}`.", ephemeral=True)

    # ---------- admin: remove ----------

    @app_commands.command(name="tag_remove", description="(Admin) Remove tag(s) from a user")
    @app_commands.describe(
        tag_name="If provided, remove only this tag; otherwise clear all",
        user="Target user (defaults to you)",
    )
    async def tag_remove_cmd(
        self,
        itx: Interaction,
        tag_name: Optional[str] = None,
        user: Optional[discord.Member] = None,
    ):
        await itx.response.defer(ephemeral=True)
        trace = uuid.uuid4().hex[:8]

        try:
            target = user or itx.user
            owner_kind, owner_id = _resolve_owner(target)

            removed = 0
            if not tag_name:
                removed = tag_dal.clear_owner(owner_kind, owner_id)
            else:
                # Prefer a direct DAL helper if present
                fn = getattr(tag_dal, "remove_by_name", None)
                if callable(fn):
                    removed = int(fn(owner_kind, owner_id, tag_name) or 0)
                else:
                    # Fallback: list → remove_instance per match (if supported)
                    rows = tag_dal.list_instances(owner_kind, owner_id) or []
                    rid_fn = getattr(tag_dal, "remove_instance", None)
                    if callable(rid_fn):
                        for r in rows:
                            if str(r["name"]).lower() == tag_name.lower():
                                rid_fn(int(r["id"]))
                                removed += 1
                    else:
                        # Last resort: clear everything
                        removed = tag_dal.clear_owner(owner_kind, owner_id)

            await itx.followup.send(
                f"🧹 Removed {removed} tag(s) from {target.mention} "
                f"(owner=`{owner_kind}:{owner_id}`){' matching `'+tag_name+'`' if tag_name else ''}.",
                ephemeral=True,
            )

        except Exception:
            log.error("[tag_remove] trace=%s\n%s", trace, traceback.format_exc())
            await itx.followup.send(f"⚠️ Remove failed. Trace `{trace}`.", ephemeral=True)

    # ---------- admin: list (RENAMED to avoid collision) ----------

    @app_commands.command(
        name="tag_list_all",
        description="(Admin) List active tags for a user (renamed to avoid collision with user /tag_list)",
    )
    async def tag_list_all_cmd(self, itx: Interaction, user: Optional[discord.Member] = None):
        await itx.response.defer(ephemeral=True)
        trace = uuid.uuid4().hex[:8]

        try:
            target = user or itx.user
            owner_kind, owner_id = _resolve_owner(target)
            rows = tag_dal.list_instances(owner_kind, owner_id)

            if not rows:
                return await itx.followup.send("No active tags.", ephemeral=True)

            lines = []
            for r in rows:
                timer = f"⏱ {int(r['tick_ms'])}ms" if r.get("tick_ms") else ""
                state = f" · state:`{r['state']}`" if r.get("state") else ""
                anchor = r.get("anchor_path", "entity")
                lines.append(f"- **{r['name']}** x{r['stacks']} @ `{anchor}` {timer}{state}")

            await itx.followup.send("\n".join(lines), ephemeral=True)

        except Exception:
            log.error("[tag_list_all] trace=%s\n%s", trace, traceback.format_exc())
            await itx.followup.send(f"⚠️ List failed. Trace `{trace}`.", ephemeral=True)

    # ---------- admin: reload specs ----------

    @app_commands.command(name="tag_specs_reload", description="(Admin) Reload tag spec files from disk")
    async def tag_specs_reload_cmd(self, itx: Interaction):
        await itx.response.defer(ephemeral=True)
        try:
            self.runtime.reload()
            await itx.followup.send("🔁 Tag specs reloaded.", ephemeral=True)
        except Exception:
            log.exception("tag_specs_reload failed")
            await itx.followup.send("⚠️ Reload failed; see logs.", ephemeral=True)

# ------------- setup -------------

async def setup(bot: commands.Bot):
    await bot.add_cog(TagsAdmin(bot))
