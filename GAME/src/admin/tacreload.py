# GAME/src/admin/hotreload.py
from __future__ import annotations
import discord
from discord import app_commands
from discord.ext import commands

# make audit decorator optional/safe
try:
    from src.core.audit import audit_event
except Exception:
    def audit_event(*a, **k):
        def deco(f): return f
        return deco

def is_admin():
    async def pred(inter: discord.Interaction) -> bool:
        m = isinstance(inter.user, discord.Member) and inter.user.guild_permissions.administrator
        return m
    return app_commands.check(pred)

class HotReload(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ext_list", description="Admin: list loaded extensions.")
    @is_admin()
    @audit_event(action_type="admin.ext_list")
    async def ext_list(self, inter: discord.Interaction):
        await inter.response.send_message(
            "\n".join(sorted(self.bot.extensions.keys())) or "No extensions loaded.",
            ephemeral=True
        )

    @app_commands.command(name="ext_reload", description="Admin: reload an extension module.")
    @app_commands.describe(module="Python module path, e.g. src.cogs.analytics")
    @is_admin()
    @audit_event(action_type="admin.ext_reload", extra=lambda interaction, module: {"module": module})
    async def ext_reload(self, inter: discord.Interaction, module: str):
        await inter.response.defer(ephemeral=True, thinking=True)
        try:
            await self.bot.reload_extension(module)
        except commands.ExtensionNotLoaded:
            try:
                await self.bot.load_extension(module)
            except Exception as e:
                await inter.followup.send(f"Load failed: `{type(e).__name__}: {e}`", ephemeral=True)
                return
        except Exception as e:
            await inter.followup.send(f"Reload failed: `{type(e).__name__}: {e}`", ephemeral=True)
            return
        # quick guild sync so the updated slash schema is live "here"
        try:
            if inter.guild:
                await self.bot.tree.sync(guild=inter.guild)
        except Exception:
            pass
        await inter.followup.send(f"Reloaded `{module}` (guild synced).", ephemeral=True)

    @app_commands.command(name="ext_load", description="Admin: load a new extension module.")
    @app_commands.describe(module="Python module path, e.g. src.admin.welcome")
    @is_admin()
    @audit_event(action_type="admin.ext_load", extra=lambda interaction, module: {"module": module})
    async def ext_load(self, inter: discord.Interaction, module: str):
        await inter.response.defer(ephemeral=True, thinking=True)
        try:
            await self.bot.load_extension(module)
        except Exception as e:
            await inter.followup.send(f"Load failed: `{type(e).__name__}: {e}`", ephemeral=True)
            return
        try:
            if inter.guild:
                await self.bot.tree.sync(guild=inter.guild)
        except Exception:
            pass
        await inter.followup.send(f"Loaded `{module}`.", ephemeral=True)

    @app_commands.command(name="ext_unload", description="Admin: unload an extension module.")
    @app_commands.describe(module="Python module path, e.g. src.cogs.analytics")
    @is_admin()
    @audit_event(action_type="admin.ext_unload", extra=lambda interaction, module: {"module": module})
    async def ext_unload(self, inter: discord.Interaction, module: str):
        await inter.response.defer(ephemeral=True, thinking=True)
        try:
            await self.bot.unload_extension(module)
        except Exception as e:
            await inter.followup.send(f"Unload failed: `{type(e).__name__}: {e}`", ephemeral=True)
            return
        await inter.followup.send(f"Unloaded `{module}`.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(HotReload(bot))
