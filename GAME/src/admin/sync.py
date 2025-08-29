# GAME/src/admin/sync.py
from __future__ import annotations
import discord
from discord import app_commands, Forbidden
from discord.ext import commands

# Safe import of audit_event (no-op fallback)
try:
    from src.core.audit import audit_event
except Exception:
    def audit_event(*_a, **_k):
        def deco(fn): return fn
        return deco


def is_admin():
    async def predicate(inter: discord.Interaction) -> bool:
        return (
            isinstance(inter.user, discord.Member)
            and inter.user.guild_permissions.administrator
        )
    return app_commands.check(predicate)


class SyncCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="sync",
        description="Admin: resync slash commands (tries this server, then global)."
    )
    @is_admin()
    @audit_event(action_type="admin.sync")
    async def sync_cmd(self, inter: discord.Interaction):
        await inter.response.defer(ephemeral=True, thinking=True)
        parts: list[str] = []

        # Try syncing commands to the current guild (if any)
        if inter.guild:
            try:
                cmds = await inter.client.tree.sync(guild=inter.guild)  # type: ignore
                parts.append(f"Here: {len(cmds)}")
            except Forbidden:
                parts.append("Here: Missing Access")
            except Exception as e:
                parts.append(f"Here failed: {type(e).__name__}")

        # Always do global
        try:
            gcmds = await inter.client.tree.sync()
            parts.append(f"Global: {len(gcmds)}")
        except Exception as e:
            parts.append(f"Global failed: {type(e).__name__}")

        await inter.followup.send("Synced — " + " • ".join(parts), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(SyncCog(bot))
