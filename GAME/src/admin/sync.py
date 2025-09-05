# src/admin/sync.py
from __future__ import annotations
import asyncio, logging, os, random
from typing import Literal, Any, Awaitable, Callable, Optional, List

import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger("admin.sync")

DEV_GUILD_ID   = int(os.getenv("DEV_GUILD_ID", "0"))
SYNC_ON_READY  = os.getenv("SYNC_ON_READY", "0") == "1"   # default OFF (no auto-sync)
SYNC_TIMEOUT_S = float(os.getenv("SYNC_TIMEOUT_S", "6.0"))  # used ONLY for auto-sync, not manual

class SyncCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._synced_once = False

        # ---- Guard: block external CommandTree.sync calls (other cogs) ----
        self._orig_sync: Callable[..., Awaitable[List[app_commands.AppCommand]]] = bot.tree.sync  # type: ignore[attr-defined]

        async def _guarded_sync(*args: Any, **kwargs: Any) -> List[app_commands.AppCommand]:
            if not getattr(self.bot, "_allow_sync_calls", False):
                guild = kwargs.get("guild", None)
                gid = getattr(guild, "id", None) if guild else None
                log.info("sync: blocked an external sync call%s; use /sync to run manually.",
                         f" for guild {gid}" if gid else "")
                return []
            return await self._orig_sync(*args, **kwargs)

        bot.tree.sync = _guarded_sync  # type: ignore[assignment]
        log.info("sync: guard installed; SYNC_ON_READY=%s, DEV_GUILD_ID=%s", int(SYNC_ON_READY), DEV_GUILD_ID)

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
        await self._do_sync(auto=True, long_wait=False)

    # --- Core sync runner ----------------------------------------------------------
    async def _do_sync(self, auto: bool, *, guild_id: int | None, long_wait: bool) -> int:
        """
        Run a real sync once, bypassing the guard.

        long_wait=True  -> no timeout; let discord.py honor Retry-After (manual /sync)
        long_wait=False -> short timeout; abort quickly if rate-limited (auto paths)
        """
        try:
            self.bot._allow_sync_calls = True
            async def _go():
                if guild_id is not None:
                    return await self._orig_sync(guild=discord.Object(id=guild_id))
                elif DEV_GUILD_ID:
                    return await self._orig_sync(guild=discord.Object(id=DEV_GUILD_ID))
                else:
                    return await self._orig_sync()

            if long_wait:
                cmds = await _go()  # NO timeout: library will wait & retry properly
            else:
                cmds = await asyncio.wait_for(_go(), timeout=SYNC_TIMEOUT_S)

            # Logging
            where = f"guild {guild_id or DEV_GUILD_ID}" if (guild_id or DEV_GUILD_ID) else "GLOBAL"
            log.info("sync: %s-synced %d commands to %s",
                     "auto" if auto else "manually", len(cmds), where)
            return len(cmds)

        except asyncio.TimeoutError:
            log.warning("sync: aborted due to timeout (likely rate-limited).")
            return -1
        except discord.HTTPException as e:
            log.warning("sync: sync failed: %s", e)
            return 0
        finally:
            self.bot._allow_sync_calls = False
            self._synced_once = True
            self.bot._synced_once = True

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
        description="Admin: bulk-sync slash commands (guild by default, or a specific guild)."
    )
    @app_commands.describe(
        scope="Where to sync (guild = fast/dev; global is slow & rate-limited)",
        guild_id="Optional explicit guild id (overrides current guild & DEV_GUILD_ID)"
    )
    async def sync_cmd(
        self,
        interaction: discord.Interaction,
        scope: Literal["guild", "global"] = "guild",
        guild_id: Optional[str] = None,
    ):
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message("Nope.", ephemeral=True)

        await interaction.response.send_message(
            "⏳ Bulk sync queued in background. I’ll follow up here when it finishes.",
            ephemeral=True,
        )

        async def runner():
            try:
                if scope == "guild":
                    gid: Optional[int] = None
                    if guild_id:
                        try: gid = int(guild_id)
                        except ValueError: gid = None
                    if gid is None and interaction.guild: gid = interaction.guild.id
                    if gid is None and DEV_GUILD_ID: gid = DEV_GUILD_ID
                    if not gid:
                        return await interaction.followup.send(
                            "No guild context for bulk sync (pass guild_id or set DEV_GUILD_ID).",
                            ephemeral=True,
                        )

                    # IMPORTANT: long_wait=True so discord.py waits through Retry-After
                    count = await self._do_sync(auto=False, guild_id=gid, long_wait=True)
                    if count == -1:
                        return await interaction.followup.send(
                            f"⚠️ Bulk sync for guild {gid} timed out early (unexpected).",
                            ephemeral=True,
                        )
                    if count == 0:
                        return await interaction.followup.send(
                            f"⚠️ Bulk sync for guild {gid} failed (see logs).",
                            ephemeral=True,
                        )
                    return await interaction.followup.send(
                        f"✅ Bulk-synced {count} commands to **{gid}**.",
                        ephemeral=True,
                    )

                # GLOBAL bulk sync (also long_wait=True)
                count = await self._do_sync(auto=False, guild_id=None, long_wait=True)
                if count <= 0:
                    msg = "timed out" if count == -1 else "failed"
                    return await interaction.followup.send(
                        f"⚠️ Global bulk sync {msg}. See logs.", ephemeral=True
                    )
                await interaction.followup.send(f"✅ Bulk-synced {count} global commands.", ephemeral=True)
            except Exception as e:
                log.exception("/sync runner failed")
                try:
                    await interaction.followup.send(f"⚠️ Sync error: `{type(e).__name__}: {e}`", ephemeral=True)
                except Exception:
                    pass

        asyncio.create_task(runner())

    @app_commands.command(
        name="sync_one",
        description="Admin: upsert a single command to a guild (bypasses bulk PUT)."
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
            try: gid = int(guild_id)
            except ValueError: gid = None
        if gid is None and interaction.guild: gid = interaction.guild.id
        if gid is None and DEV_GUILD_ID: gid = DEV_GUILD_ID
        if not gid:
            return await interaction.response.send_message(
                "No guild context for sync_one (pass guild_id or set DEV_GUILD_ID).", ephemeral=True
            )

        await interaction.response.send_message(
            f"⏳ Upserting `/{cmd.name}` to guild **{gid}**…", ephemeral=True
        )

        async def runner():
            app_id = (self.bot.application_id or (self.bot.user.id if self.bot.user else None))  # type: ignore[attr-defined]
            if not app_id:
                return await interaction.followup.send("Cannot resolve application id.", ephemeral=True)

            payload = self._payload_for(cmd)
            try:
                existing = await self._get_guild_cmds_http(app_id, gid)
                found = next((e for e in existing
                              if str(e.get("name","")).lower() == cmd.name.lower()
                              and int(e.get("type",1)) == int(payload.get("type",1))), None)
                if found:
                    await self._edit_guild_cmd_http(app_id, gid, int(found["id"]), payload)
                    what = "updated"
                else:
                    await self._create_guild_cmd_http(app_id, gid, payload)
                    what = "created"
                await interaction.followup.send(f"✅ `/{cmd.name}` {what} on guild **{gid}**.", ephemeral=True)
            except discord.HTTPException as e:
                log.warning("sync_one failed: %s", e)
                await interaction.followup.send(f"⚠️ sync_one failed: `{e}`", ephemeral=True)
            except Exception as e:
                log.exception("sync_one unexpected error")
                await interaction.followup.send(f"⚠️ sync_one error: `{type(e).__name__}: {e}`", ephemeral=True)

        asyncio.create_task(runner())

    @app_commands.command(name="sync_preview", description="Admin: show commands this process would register (no API calls).")
    async def sync_preview(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message("Nope.", ephemeral=True)
        cmds = [c for c in self.bot.tree.get_commands() if isinstance(c, app_commands.Command)]
        lines = [f"/{c.name} — {c.description or '(no desc)'}" for c in sorted(cmds, key=lambda x: x.name)]
        text = "\n".join(lines) if lines else "No commands found in this process."
        await interaction.response.send_message(text[:1900], ephemeral=True)

    @app_commands.command(name="sync_status", description="Admin: show whether a bulk sync has run this session.")
    async def sync_status(self, interaction: discord.Interaction):
        flag = getattr(self.bot, "_synced_once", False)
        await interaction.response.send_message(
            f"synced_once={flag} • DEV_GUILD_ID={DEV_GUILD_ID} • SYNC_ON_READY={int(SYNC_ON_READY)}",
            ephemeral=True,
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(SyncCog(bot))
