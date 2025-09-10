# src/admin/sync.py
from __future__ import annotations
import asyncio
import inspect
import logging
import os
import random
from typing import Any, Awaitable, Callable, List, Literal, Optional

import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger("admin.sync")

DEV_GUILD_ID   = int(os.getenv("DEV_GUILD_ID", "0"))
SYNC_ON_READY  = os.getenv("SYNC_ON_READY", "0") == "1"        # default OFF (no auto-sync)
SYNC_TIMEOUT_S = float(os.getenv("SYNC_TIMEOUT_S", "6.0"))     # used ONLY for auto-sync, not manual

# Capture the ORIGINAL (unwrapped) sync function once, at import time.
# We'll bind this to each bot's tree to bypass our own guard when /sync runs.
_RAW_SYNC_FN = inspect.unwrap(app_commands.CommandTree.sync)


class SyncCog(commands.Cog):
    """
    Centralized, guarded sync utilities.

    - Blocks arbitrary calls to CommandTree.sync() from other cogs (forces using /sync).
    - Fast dev flow: guild-only sync (default).
    - Global sync & both-scopes sync to prune stale GLOBAL commands (e.g., ghost /createitem).
    - "sync_one" helper upserts a single command to a guild via HTTP.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._synced_once = False

        # Bind the ORIGINAL sync as a method on THIS tree so we can always call it.
        self._raw_sync_bound: Callable[..., Awaitable[List[app_commands.AppCommand]]] = _RAW_SYNC_FN.__get__(
            bot.tree, app_commands.CommandTree
        )

        # ---- Guard: block external CommandTree.sync calls (other cogs) ----
        # We only monkeypatch THIS bot's tree (not the class), so other bots are unaffected.
        self._guard_installed = False
        if getattr(bot.tree.sync, "__name__", "") != "_guarded_sync":
            orig_bound = bot.tree.sync  # keep around for clarity (not used directly)

            async def _guarded_sync(*args: Any, **kwargs: Any) -> List[app_commands.AppCommand]:
                guild = kwargs.get("guild", None)
                gid = getattr(guild, "id", None) if guild else None
                log.info(
                    "sync: blocked an external sync call%s; use /sync to run manually.",
                    f" for guild {gid}" if gid else " (GLOBAL)",
                )
                return []  # pretend success but do nothing

            bot.tree.sync = _guarded_sync  # type: ignore[assignment]
            self._guard_installed = True

        log.info(
            "sync: guard installed=%s; SYNC_ON_READY=%s, DEV_GUILD_ID=%s",
            self._guard_installed, int(SYNC_ON_READY), DEV_GUILD_ID
        )

    # ---------------- Auto-sync (optional; still disabled by default) ----------------
    @commands.Cog.listener()
    async def on_ready(self):
        if not SYNC_ON_READY:
            log.info("sync: skipping auto sync on ready (SYNC_ON_READY=0). Use /sync when ready.")
            return
        if self._synced_once or getattr(self.bot, "_synced_once", False):
            return
        await asyncio.sleep(random.uniform(1.0, 3.0))  # soften thundering herd
        # Auto-sync uses a SHORT TIMEOUT so we never block startup forever
        await self._do_sync(auto=True, guild_id=None, long_wait=False, global_scope=False)

    # --- Core sync runner ----------------------------------------------------------
    async def _do_sync(
        self,
        auto: bool,
        *,
        guild_id: int | None,
        long_wait: bool,
        global_scope: bool,
    ) -> int:
        """
        Run a real sync once, BYPASSING the guard by calling the original sync.

        long_wait=True  -> no timeout; let discord.py honor Retry-After (manual /sync)
        long_wait=False -> short timeout; abort quickly if rate-limited (auto paths)

        global_scope=True  -> force a GLOBAL sync (ignore DEV_GUILD_ID)
        """
        try:
            async def _go():
                if global_scope:
                    # Force GLOBAL sync (this is what prunes stale global commands)
                    return await self._raw_sync_bound()
                if guild_id is not None:
                    return await self._raw_sync_bound(guild=discord.Object(id=guild_id))
                elif DEV_GUILD_ID:
                    # Dev convenience: if no guild_id passed, default to DEV_GUILD_ID
                    return await self._raw_sync_bound(guild=discord.Object(id=DEV_GUILD_ID))
                else:
                    # Fallback GLOBAL (only when no DEV_GUILD_ID is set)
                    return await self._raw_sync_bound()

            if long_wait:
                cmds = await _go()  # NO timeout: library will wait & retry properly
            else:
                cmds = await asyncio.wait_for(_go(), timeout=SYNC_TIMEOUT_S)

            if global_scope:
                where = "GLOBAL"
            else:
                where = f"guild {guild_id or DEV_GUILD_ID}" if (guild_id or DEV_GUILD_ID) else "GLOBAL"

            log.info("sync: %s-synced %d commands to %s", "auto" if auto else "manually", len(cmds), where)
            return len(cmds)

        except asyncio.TimeoutError:
            log.warning("sync: aborted due to timeout (likely rate-limited).")
            return -1
        except discord.HTTPException as e:
            log.warning("sync: sync failed: %s", e)
            return 0
        finally:
            self._synced_once = True
            self.bot._synced_once = True  # type: ignore[attr-defined]

    # ----------- Helpers for single-command upsert (bypasses bulk PUT) -------------
    async def _get_guild_cmds_http(self, app_id: int, guild_id: int):
        return await self.bot.http.get_guild_commands(app_id, guild_id)

    async def _create_guild_cmd_http(self, app_id: int, guild_id: int, payload: dict):
        return await self.bot.http.create_guild_command(app_id, guild_id, payload)

    async def _edit_guild_cmd_http(self, app_id: int, guild_id: int, command_id: int, payload: dict):
        return await self.bot.http.edit_guild_command(app_id, guild_id, command_id, payload)

    def _payload_for(self, cmd: app_commands.Command) -> dict:
        data = cmd.to_dict()
        for k in ("contexts", "integration_types"):
            data.pop(k, None)
        return data

    def _cmd_by_name(self, name: str) -> Optional[app_commands.Command]:
        n = name.strip().lower()
        for c in self.bot.tree.get_commands():
            if isinstance(c, app_commands.Command) and c.name.lower() == n:
                return c
        return None

    # ---------------- Manual commands ----------------
    @app_commands.command(
        name="sync",
        description="Bulk-sync commands (guild/global/both)."  # <= 100 chars
    )
    @app_commands.describe(
        scope="Where to sync: guild (fast), global (prune ghosts), or both",
        guild_id="Optional explicit guild id for guild scope"
    )
    async def sync_cmd(
        self,
        interaction: discord.Interaction,
        scope: Literal["guild", "global", "both"] = "guild",
        guild_id: Optional[str] = None,
    ):
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message("Nope.", ephemeral=True)

        await interaction.response.send_message(
            "â³ Bulk sync queued in background. Iâ€™ll follow up here when it finishes.",
            ephemeral=True,
        )

        async def runner():
            try:
                synced_global = synced_guild = None

                if scope in ("global", "both"):
                    # Force GLOBAL sync regardless of DEV_GUILD_ID
                    synced_global = await self._do_sync(
                        auto=False, guild_id=None, long_wait=True, global_scope=True
                    )

                if scope in ("guild", "both"):
                    gid: Optional[int] = None
                    if guild_id:
                        try:
                            gid = int(guild_id)
                        except ValueError:
                            gid = None
                    if gid is None and interaction.guild:
                        gid = interaction.guild.id
                    if gid is None and DEV_GUILD_ID:
                        gid = DEV_GUILD_ID
                    if not gid:
                        return await interaction.followup.send(
                            "No guild context for guild sync (pass guild_id or set DEV_GUILD_ID).",
                            ephemeral=True,
                        )
                    synced_guild = await self._do_sync(
                        auto=False, guild_id=gid, long_wait=True, global_scope=False
                    )

                parts: List[str] = []
                if synced_guild is not None:
                    if synced_guild == -1:
                        parts.append("Guild: timed out")
                    elif synced_guild == 0:
                        parts.append("Guild: failed")
                    else:
                        parts.append(f"Guild: {synced_guild}")
                if synced_global is not None:
                    if synced_global == -1:
                        parts.append("Global: timed out")
                    elif synced_global == 0:
                        parts.append("Global: failed")
                    else:
                        parts.append(f"Global: {synced_global}")

                summary = " â€¢ ".join(parts) if parts else "No operations"
                await interaction.followup.send(f"âœ… Sync complete â€” {summary}.", ephemeral=True)

            except Exception as e:
                log.exception("/sync runner failed")
                try:
                    await interaction.followup.send(f"âš ï¸ Sync error: `{type(e).__name__}: {e}`", ephemeral=True)
                except Exception:
                    pass

        asyncio.create_task(runner())

    @app_commands.command(
        name="sync_one",
        description="Upsert a single command to a guild (HTTP helper)."
    )
    @app_commands.describe(
        name="Command name to upsert",
        guild_id="Target guild id (defaults to current guild, else DEV_GUILD_ID)"
    )
    async def sync_one(
        self,
        interaction: discord.Interaction,
        name: str,
        guild_id: Optional[str] = None,
    ):
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message("Nope.", ephemeral=True)

        cmd = self._cmd_by_name(name)
        if not cmd:
            return await interaction.response.send_message(
                f"Unknown command **{name}** in this process.", ephemeral=True
            )

        gid: Optional[int] = None
        if guild_id:
            try:
                gid = int(guild_id)
            except ValueError:
                gid = None
        if gid is None and interaction.guild:
            gid = interaction.guild.id
        if gid is None and DEV_GUILD_ID:
            gid = DEV_GUILD_ID
        if not gid:
            return await interaction.response.send_message(
                "No guild context for sync_one (pass guild_id or set DEV_GUILD_ID).", ephemeral=True
            )

        await interaction.response.send_message(
            f"â³ Upserting `/{cmd.name}` to guild **{gid}**â€¦", ephemeral=True
        )

        async def runner():
            app_id = (self.bot.application_id or (self.bot.user.id if self.bot.user else None))  # type: ignore[attr-defined]
            if not app_id:
                return await interaction.followup.send("Cannot resolve application id.", ephemeral=True)

            payload = self._payload_for(cmd)
            try:
                existing = await self._get_guild_cmds_http(app_id, gid)
                found = next(
                    (
                        e
                        for e in existing
                        if str(e.get("name", "")).lower() == cmd.name.lower()
                        and int(e.get("type", 1)) == int(payload.get("type", 1))
                    ),
                    None,
                )
                if found:
                    await self._edit_guild_cmd_http(app_id, gid, int(found["id"]), payload)
                    what = "updated"
                else:
                    await self._create_guild_cmd_http(app_id, gid, payload)
                    what = "created"
                await interaction.followup.send(f"âœ… `/{cmd.name}` {what} on guild **{gid}**.", ephemeral=True)
            except discord.HTTPException as e:
                log.warning("sync_one failed: %s", e)
                await interaction.followup.send(f"âš ï¸ sync_one failed: `{e}`", ephemeral=True)
            except Exception as e:
                log.exception("sync_one unexpected error")
                await interaction.followup.send(f"âš ï¸ sync_one error: `{type(e).__name__}: {e}`", ephemeral=True)

        asyncio.create_task(runner())

    @app_commands.command(name="sync_preview", description="Show commands this process would register (no API calls).")
    async def sync_preview(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message("Nope.", ephemeral=True)
        cmds = [c for c in self.bot.tree.get_commands() if isinstance(c, app_commands.Command)]
        lines = [f"/{c.name} â€” {c.description or '(no desc)'}" for c in sorted(cmds, key=lambda x: x.name)]
        text = "\n".join(lines) if lines else "No commands found in this process."
        await interaction.response.send_message(text[:1900], ephemeral=True)

    @app_commands.command(name="sync_status", description="Show whether a bulk sync has run this session.")
    async def sync_status(self, interaction: discord.Interaction):
        flag = getattr(self.bot, "_synced_once", False)
        await interaction.response.send_message(
            f"synced_once={flag} â€¢ DEV_GUILD_ID={DEV_GUILD_ID} â€¢ SYNC_ON_READY={int(SYNC_ON_READY)}",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(SyncCog(bot))
