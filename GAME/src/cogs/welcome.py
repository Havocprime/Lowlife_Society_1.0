# GAME/src/cogs/welcome.py
from __future__ import annotations

import logging
import os
import random
from pathlib import Path
from typing import Optional, Literal

import discord
from discord.ext import commands
from discord import app_commands

from src.core.settings import SETTINGS
from src.data.npc_index import random_name
from src.data.intro_templates import build_intro
from src.db.dal import ensure_npc_intro_table, log_npc_intro

# Audit is optional; fall back to a no-op decorator if it's not ready
try:
    from src.core.audit import audit_event
except Exception:  # pragma: no cover
    def audit_event(*_args, **_kwargs):
        def deco(fn): return fn
        return deco

log = logging.getLogger("welcome.cog")

IMG_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
Gender = Literal["male", "female"]

GUILD_ID: int | None = SETTINGS.guild_id


def _folder_from_config() -> Path:
    """Resolve the mugshot/images folder:
       1) WELCOME_IMAGES_DIR (or legacy MUGSHOT_DIR)
       2) GAME/assets/mugshots
    """
    env = os.getenv("WELCOME_IMAGES_DIR") or os.getenv("MUGSHOT_DIR")
    if env:
        return Path(env).expanduser().resolve()
    here = Path(__file__).resolve()
    game_dir = here.parents[2]
    return (game_dir / "assets" / "mugshots").resolve()


def _pick_random_image(base: Path, gender: Gender | None) -> Path:
    folder = base
    if gender and (base / gender).exists():
        folder = base / gender
    files = [p for p in folder.glob("*") if p.is_file() and p.suffix.lower() in IMG_EXTS]
    if not files:
        raise FileNotFoundError(f"No image files found in {folder}")
    return random.choice(files)


class WelcomeCog(commands.Cog):
    """Welcome system: random mugshot + NPC name + gritty intro."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.folder = _folder_from_config()
        self._inflight: set[int] = set()  # dedupe per-interaction
        try:
            ensure_npc_intro_table()
        except Exception:
            pass

    # ------------- helpers -------------
    def _resolve_welcome_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        """Prefer explicit channel id; fall back to common names."""
        if SETTINGS.welcome_channel_id:
            ch = guild.get_channel(SETTINGS.welcome_channel_id)
            if isinstance(ch, discord.TextChannel):
                return ch
        for name in ("welcome", "introductions", "start-here"):
            ch = discord.utils.get(guild.text_channels, name=name)
            if isinstance(ch, discord.TextChannel):
                return ch
        return None

    async def _send_welcome(
        self,
        member: discord.Member,
        channel: discord.abc.Messageable,
        gender: Gender | None = None,
    ) -> None:
        # Decide gender bucket from available subfolders if not forced
        if gender is None and (self.folder / "male").exists() and (self.folder / "female").exists():
            gender = random.choice(["male", "female"])  # type: ignore

        img_path = _pick_random_image(self.folder, gender)
        filename = img_path.name

        # NPC + intro text
        npc_name = random_name(gender=gender or "any")

        # Your intro builder — assumes it returns (intro_text, handoff_type, contact, extra_json)
        intro_text, handoff_type, contact_value, extra = build_intro(gender)

        # Compose embed
        title = f"Welcome to The City: {member.display_name}"
        embed = discord.Embed(title=title, colour=discord.Color.gold())
        embed.description = intro_text
        embed.set_footer(text=f"– {npc_name}.\nLowlife Society")

        file = discord.File(img_path, filename=filename)
        embed.set_image(url=f"attachment://{filename}")

        msg = await channel.send(embed=embed, file=file)

        # Persist the generated intro (best-effort)
        try:
            await log_npc_intro(
                guild_id=getattr(getattr(channel, "guild", None), "id", None),
                channel_id=getattr(channel, "id", None),
                message_id=getattr(msg, "id", None),
                member_id=getattr(member, "id", None),
                npc_fullname=npc_name,
                npc_gender=(gender or "any"),
                image_filename=filename,
                handoff_type=handoff_type,
                handoff_value=contact_value,
                intro_text=intro_text,
                extra_json=extra,
            )
        except Exception:
            pass

    # ------------- slash commands -------------
    @app_commands.command(name="welcome_status", description="Show Welcome wiring and readiness")
    async def welcome_status(self, interaction: discord.Interaction):
        g = interaction.guild
        ch = self._resolve_welcome_channel(g) if g else None
        await interaction.response.send_message(
            f"Guild: {g.name if g else 'N/A'} ({g.id if g else 'N/A'})\n"
            f"Configured GUILD_ID: {GUILD_ID}\n"
            f"Resolved Welcome Channel: {ch.mention if ch else 'None'}\n"
            f"Members intent: {'ON' if interaction.client.intents.members else 'OFF'}",
            ephemeral=True
        )

    # Scope to the configured guild (faster command updates) when available
    if GUILD_ID:
        @app_commands.guilds(discord.Object(id=GUILD_ID))
        @app_commands.command(name="welcome_preview", description="Preview the welcome post (random mugshot + NPC)")
        @app_commands.describe(
            user="Preview as if this user joined (default: you)",
            channel="Where to send the preview (default: here)",
            gender="Force a gender bucket for the mugshot/name",
        )
        @app_commands.choices(gender=[
            app_commands.Choice(name="male", value="male"),
            app_commands.Choice(name="female", value="female"),
        ])
        @audit_event(action_type="admin.welcome_preview")
        async def welcome_preview(  # type: ignore[no-redef]
            self,
            interaction: discord.Interaction,
            user: Optional[discord.Member] = None,
            channel: Optional[discord.abc.GuildChannel] = None,
            gender: Optional[app_commands.Choice[str]] = None,
        ):
            await self._handle_preview(interaction, user, channel, gender, "(guild-scoped)")
    else:
        @app_commands.command(name="welcome_preview", description="Preview the welcome post (random mugshot + NPC)")
        @app_commands.describe(
            user="Preview as if this user joined (default: you)",
            channel="Where to send the preview (default: here)",
            gender="Force a gender bucket for the mugshot/name",
        )
        @app_commands.choices(gender=[
            app_commands.Choice(name="male", value="male"),
            app_commands.Choice(name="female", value="female"),
        ])
        @audit_event(action_type="admin.welcome_preview")
        async def welcome_preview(  # type: ignore[no-redef]
            self,
            interaction: discord.Interaction,
            user: Optional[discord.Member] = None,
            channel: Optional[discord.abc.GuildChannel] = None,
            gender: Optional[app_commands.Choice[str]] = None,
        ):
            await self._handle_preview(interaction, user, channel, gender, "(global scope)")

    async def _handle_preview(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.Member],
        channel: Optional[discord.abc.GuildChannel],
        gender_choice: Optional[app_commands.Choice[str]],
        suffix: str,
    ) -> None:
        # De-dupe rare double-dispatches by interaction id
        iid: int | None
        try:
            iid = int(interaction.id)  # type: ignore[attr-defined]
        except Exception:
            iid = None

        if iid is not None:
            if iid in self._inflight:
                return
            self._inflight.add(iid)

        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)

            if GUILD_ID and interaction.guild and interaction.guild.id != GUILD_ID:
                await interaction.followup.send("This isn’t the configured Welcome guild.", ephemeral=True)
                return

            target_user = user or interaction.user  # type: ignore
            target_channel = channel or interaction.channel  # type: ignore
            forced_gender: Gender | None = (gender_choice.value if gender_choice else None)  # type: ignore

            if not target_channel:
                await interaction.followup.send("No channel to send to.", ephemeral=True)
                return

            await self._send_welcome(target_user, target_channel, forced_gender)

            try:
                await interaction.followup.send(f"Preview sent ✅ {suffix}", ephemeral=True)
            except discord.HTTPException:
                pass
        except Exception as e:  # best-effort error reporting
            try:
                if not interaction.response.is_done():
                    await interaction.response.defer(ephemeral=True)
                await interaction.followup.send(
                    f"Welcome preview failed — **{type(e).__name__}**: {e}\n"
                    f"Folder: `{self.folder}`\n"
                    f"Tip: set **WELCOME_IMAGES_DIR** and optional subfolders `male/` and `female/`.",
                    ephemeral=True,
                )
            except Exception:
                pass
        finally:
            if iid is not None:
                self._inflight.discard(iid)

    # ------------- events -------------
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if GUILD_ID and member.guild.id != GUILD_ID:
            return

        channel = self._resolve_welcome_channel(member.guild)
        if not channel:
            log.warning("Welcome: no channel found in %s (%s)", member.guild.name, member.guild.id)
            return

        try:
            await self._send_welcome(member, channel, None)
        except discord.Forbidden:
            log.error("Welcome: missing permissions to post in #%s", channel.name)
        except Exception:
            log.exception("Welcome: failed to send embed")


async def setup(bot: commands.Bot):
    await bot.add_cog(WelcomeCog(bot))
