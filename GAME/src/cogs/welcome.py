# GAME/src/cogs/welcome.py
from __future__ import annotations

import os
import random
from pathlib import Path
from typing import Optional, Iterable, Tuple

import discord
from discord import app_commands
from discord.ext import commands

# Optional settings via env (or leave defaults)
WELCOME_CHANNEL_ID = int(os.getenv("WELCOME_CHANNEL_ID", "0") or "0")
MUGSHOT_DIR = os.getenv(
    "MUGSHOT_DIR",
    str(Path(__file__).resolve().parents[2] / "assets" / "mugshots"),
)

# Guild scoping so commands appear instantly after /sync
try:
    from src.core.settings import SETTINGS
    _GUILD_ID = int(SETTINGS.guild_id or 0)
except Exception:
    _GUILD_ID = int(os.getenv("GUILD_ID", "0") or "0")

_GUILD_OBJ = discord.Object(id=_GUILD_ID) if _GUILD_ID else None
def _guild_deco():
    return (lambda f: app_commands.guilds(_GUILD_OBJ)(f)) if _GUILD_OBJ else (lambda f: f)

# --- best-effort audit ---
try:
    from src.core import audit as audit_core
except Exception:
    audit_core = None

async def _audit_log(**kwargs):
    try:
        fn = getattr(audit_core, "log_action", None)
        if fn:
            await fn(**kwargs)
    except Exception:
        pass


def _iter_images(d: Path) -> Iterable[Path]:
    exts = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
    try:
        for p in d.iterdir():
            if p.is_file() and p.suffix.lower() in exts:
                yield p
    except FileNotFoundError:
        # directory doesn't exist
        return


def _pick_random_image(directory: Path) -> Optional[Path]:
    try:
        imgs = [p for p in _iter_images(directory)]
        if not imgs:
            return None
        return random.choice(imgs)
    except Exception:
        return None


def _is_admin(member: discord.Member) -> bool:
    return bool(getattr(member, "guild_permissions", None) and member.guild_permissions.administrator)


class WelcomeCog(commands.Cog):
    """Welcome new members with a random mugshot + shoutout."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._channel_id: int = WELCOME_CHANNEL_ID
        self._mug_dir = Path(MUGSHOT_DIR)

    # ---------- channel picking & permission checks ----------
    def _pick_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        # 1) explicit env channel
        if self._channel_id:
            ch = guild.get_channel(self._channel_id)
            if isinstance(ch, discord.TextChannel):
                return ch

        # 2) system channel if sendable
        if guild.system_channel and isinstance(guild.system_channel, discord.TextChannel):
            return guild.system_channel

        # 3) first text channel
        for ch in guild.text_channels:
            return ch
        return None

    @staticmethod
    def _bot_perms(ch: discord.TextChannel) -> discord.Permissions:
        me = ch.guild.me
        return ch.permissions_for(me) if me else discord.Permissions.none()

    # returns (ok, reason)
    async def _send_welcome(self, ch: discord.TextChannel, member: discord.Member) -> Tuple[bool, str]:
        perms = self._bot_perms(ch)
        if not perms.send_messages:
            return False, "Bot lacks Send Messages in the target channel."
        if not perms.embed_links:
            return False, "Bot lacks Embed Links in the target channel."

        text = f"Welcome to the City, {member.mention}."
        embed = discord.Embed(title="🪪 New Arrival", description=text, colour=discord.Color.dark_gold())
        embed.set_author(name=str(member), icon_url=getattr(member.display_avatar, "url", discord.Embed.Empty))

        # Pick image; try to attach it if possible
        fp: Optional[Path] = _pick_random_image(self._mug_dir)
        file = None
        if fp and perms.attach_files:
            try:
                file = discord.File(fp, filename=fp.name)  # open inside try
                embed.set_image(url=f"attachment://{fp.name}")
            except Exception:
                # fall back to embed-only if the file can't be opened
                file = None
                embed.set_footer(text=f"(Failed to open mugshot {fp.name} — using embed only.)")
        elif not fp:
            embed.set_footer(text="(No mugshot found — add images to MUGSHOT_DIR to enable.)")
        elif fp and not perms.attach_files:
            embed.set_footer(text="(No Attach Files permission — using embed only.)")

        try:
            if file:
                await ch.send(embed=embed, file=file)
            else:
                await ch.send(embed=embed)
            await _audit_log(
                guild_id=member.guild.id,
                channel_id=ch.id,
                user_id=member.id,
                action_type="member_welcome_sent",
                details={"mugshot": (str(fp) if fp else None), "channel_name": ch.name, "status": "ok"},
            )
            return True, "ok"
        except discord.Forbidden:
            await _audit_log(
                guild_id=member.guild.id,
                channel_id=ch.id,
                user_id=member.id,
                action_type="member_welcome_sent",
                details={"mugshot": (str(fp) if fp else None), "channel_name": ch.name, "status": "forbidden"},
            )
            return False, "Forbidden when sending the welcome message."

    # ---------- events ----------
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot or not member.guild:
            return
        ch = self._pick_channel(member.guild)
        if not ch:
            return
        await self._send_welcome(ch, member)

    # ---------- admin test commands ----------
    @_guild_deco()
    @app_commands.command(name="welcome_preview", description="Admin: preview the welcome message (uses random mugshot).")
    @app_commands.describe(user="Preview for a specific user (defaults to you).")
    async def welcome_preview(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        if not (isinstance(interaction.user, discord.Member) and _is_admin(interaction.user)):
            await interaction.response.send_message("Nope.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)

        member = user or interaction.user  # type: ignore
        ch = self._pick_channel(interaction.guild) if interaction.guild else None  # type: ignore
        if ch is None:
            await interaction.followup.send("I don’t have a text channel to use here.", ephemeral=True)
            return

        ok, reason = await self._send_welcome(ch, member)
        msg = "Sent a preview." if ok else f"Couldn’t send: {reason}"
        await interaction.followup.send(msg, ephemeral=True)

    # Alias
    @_guild_deco()
    @app_commands.command(name="welcome", description="Admin: preview the welcome message (alias).")
    @app_commands.describe(user="Preview for a specific user (defaults to you).")
    async def welcome(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        await self.welcome_preview(interaction, user)

    # Quick diagnostics
    @_guild_deco()
    @app_commands.command(name="welcome_debug", description="Admin: show resolved welcome channel & mugshot stats.")
    async def welcome_debug(self, interaction: discord.Interaction):
        if not (isinstance(interaction.user, discord.Member) and _is_admin(interaction.user)):
            await interaction.response.send_message("Nope.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)

        ch = self._pick_channel(interaction.guild) if interaction.guild else None  # type: ignore
        img_list = [p.name for p in _iter_images(self._mug_dir)] or []
        ch_txt = getattr(ch, "mention", "—")
        perms = self._bot_perms(ch) if isinstance(ch, discord.TextChannel) else None
        details = [
            f"Channel: {ch_txt}",
            f"Images found: {len(img_list)}",
            f"Dir: `{self._mug_dir}`",
        ]
        if perms:
            details.append(f"Perms — send:{perms.send_messages} embed:{perms.embed_links} attach:{perms.attach_files}")
        await interaction.followup.send("\n".join(details), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(WelcomeCog(bot))
