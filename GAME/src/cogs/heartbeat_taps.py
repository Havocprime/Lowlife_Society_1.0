# GAME/src/cogs/heartbeat_taps.py
from __future__ import annotations

import os
import logging
import discord
from discord import app_commands, Interaction
from discord.ext import commands

log = logging.getLogger("hb.taps")


def _hb(bot: commands.Bot):
    return getattr(bot, "_heartbeat", None)


def _dash() -> str:
    """Em dash with ASCII fallback if HEARTBEAT_ASCII=1."""
    if os.getenv("HEARTBEAT_ASCII", "").strip().lower() in ("1", "true", "yes", "on"):
        return "-"
    try:
        return "\N{EM DASH}"  # —
    except Exception:
        return "-"


def _demojibake(s: str | None) -> str:
    """Fix already-garbled text that was mis-decoded as latin-1."""
    if not s:
        return ""
    if "â" not in s and "Ã" not in s:
        return s
    try:
        return s.encode("latin1").decode("utf-8")
    except Exception:
        return s


class HeartbeatTaps(commands.Cog):
    """
    Taps the heartbeat when interactions/messages happen and when commands complete.
    Provides /hb (admin) to control or tick the heartbeat.
    NOTE: This cog does NOT call tree.sync(); registration is handled by bot.py.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- Activity taps ----------

    @commands.Cog.listener()
    async def on_interaction(self, interaction: Interaction):
        hb = _hb(self.bot)
        if hb:
            hb.mark_activity()

    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction: Interaction, command: app_commands.Command):
        hb = _hb(self.bot)
        if hb:
            hb.inc_work()

    @commands.Cog.listener()
    async def on_app_command_error(self, interaction: Interaction, error: app_commands.AppCommandError):
        hb = _hb(self.bot)
        if hb:
            hb.inc_work()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author and message.author.bot:
            return
        hb = _hb(self.bot)
        if hb:
            hb.mark_activity()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        hb = _hb(self.bot)
        if hb:
            hb.inc_work()

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        hb = _hb(self.bot)
        if hb:
            hb.inc_work()

    # ---------- Admin control ----------

    @app_commands.command(name="hb", description="Admin: control/tick the terminal heartbeat")
    @app_commands.describe(mode="on/off/tick/status")
    async def hb(self, interaction: Interaction, mode: str):
        # Admin-only
        if not (isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator):
            await interaction.response.send_message("Nope.", ephemeral=True)
            return

        h = _hb(self.bot)
        if not h:
            await interaction.response.send_message("Heartbeat is not running.", ephemeral=True)
            return

        m = (mode or "").lower().strip()
        if m == "on":
            h.cfg.enable_spinner = True
            h.cfg.enable_logging = True
            await interaction.response.send_message("Heartbeat: **ON** (spinner+logging)", ephemeral=True)
        elif m == "off":
            h.cfg.enable_spinner = False
            h.cfg.enable_logging = False
            await interaction.response.send_message("Heartbeat: **OFF** (spinner+logging)", ephemeral=True)
        elif m == "tick":
            h.mark_activity()
            h.inc_work()
            await interaction.response.send_message("Heartbeat ticked (activity+work).", ephemeral=True)
        else:
            DASH = _dash()
            msg = (
                f"Heartbeat {DASH} "
                f"spinner:`{getattr(h.cfg, 'enable_spinner', False)}` {DASH} "
                f"logging:`{getattr(h.cfg, 'enable_logging', False)}` {DASH} "
                f"tick:`{getattr(h, 'tick', getattr(h, '_tick', 0))}`"
            )
            await interaction.response.send_message(_demojibake(msg), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(HeartbeatTaps(bot))
