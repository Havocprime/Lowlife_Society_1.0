# GAME/src/cogs/welcome.py
from __future__ import annotations

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

# ---- DAL (guarded import so the cog always loads) --------------------------
try:
    from src.db.dal import ensure_npc_intro_table, log_npc_intro
except Exception:
    ensure_npc_intro_table = None  # type: ignore

    async def log_npc_intro(**_kwargs):  # type: ignore
        return 0

# ---- Audit (optional) ------------------------------------------------------
try:
    from src.core.audit import audit_event
except Exception:  # pragma: no cover
    def audit_event(*_args, **_kwargs):
        def deco(fn): return fn
        return deco

IMG_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
Gender = Literal["male", "female"]


# ---------- helpers ----------
def _folder_from_config() -> Path:
    """Priority: ENV WELCOME_IMAGES_DIR -> GAME/assets/mugshots"""
    env = os.getenv("WELCOME_IMAGES_DIR")
    if env:
        return Path(env).expanduser().resolve()
    here = Path(__file__).resolve()
    game_dir = here.parents[2]  # .../GAME
    return (game_dir / "assets" / "mugshots").resolve()


def _welcome_channel_id() -> Optional[int]:
    """Priority: ENV WELCOME_CHANNEL_ID -> SETTINGS.welcome_channel_id"""
    raw = os.getenv("WELCOME_CHANNEL_ID") or getattr(SETTINGS, "welcome_channel_id", None)
    try:
        return int(raw) if raw else None
    except Exception:
        return None


def _pick_random_image(base: Path, gender: Gender | None) -> Path:
    """
    If male/female subfolders exist, pick from that gender.
    If not, fall back to the base folder.
    """
    folder = base
    if gender and (base / gender).exists():
        folder = base / gender
    files = [p for p in folder.glob("*") if p.is_file() and p.suffix.lower() in IMG_EXTS]
    if not files:
        raise FileNotFoundError(f"No image files found in {folder}")
    return random.choice(files)


# ---------- cog ----------
class WelcomeCog(commands.Cog):
    """Welcome system: random mugshot + NPC name + gritty intro w/ hand-off."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.folder = _folder_from_config()
        # Create the table if DAL provided it
        try:
            if ensure_npc_intro_table:
                ensure_npc_intro_table()
        except Exception:
            # Never block startup over DB problems
            pass

    async def _send_welcome(
        self,
        member: discord.Member,
        channel: discord.abc.Messageable,
        gender: Gender | None = None,
    ) -> None:
        # Decide a gender bucket if both exist and none provided
        if gender is None and (self.folder / "male").exists() and (self.folder / "female").exists():
            gender = random.choice(["male", "female"])  # type: ignore

        img_path = _pick_random_image(self.folder, gender)
        filename = img_path.name

        # Header (per your spec)
        title = f"Welcome to The City: <:: {member.display_name} ::>"

        # NPC identity + gritty intro + hand-off
        npc_name = random_name(gender=gender or "any")
        intro_text, handoff_type, contact_value, extra = build_intro(gender)

        file = discord.File(img_path, filename=filename)
        embed = discord.Embed(title=title, colour=discord.Color.gold())
        embed.description = intro_text                     # (above image)
        embed.set_image(url=f"attachment://{filename}")   # image
        embed.set_footer(text=f"– {npc_name}.\nLowlife Society")  # (below image)

        msg = await channel.send(embed=embed, file=file)

        # Log it (if DAL available)
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
            # Never crash a welcome over the DB
            pass

    # -------- Commands --------
    @app_commands.command(
        name="welcome_preview",
        description="Preview the welcome post (random mugshot + NPC).",
    )
    @app_commands.describe(
        user="Preview as if this user joined (default: you)",
        channel="Where to send the preview (default: here)",
        gender="Force a gender bucket for the mugshot/name",
    )
    @app_commands.choices(
        gender=[
            app_commands.Choice(name="male", value="male"),
            app_commands.Choice(name="female", value="female"),
        ]
    )
    @audit_event(action_type="admin.welcome_preview")
    async def welcome_preview(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.Member] = None,
        channel: Optional[discord.abc.GuildChannel] = None,
        gender: Optional[app_commands.Choice[str]] = None,
    ):
        await interaction.response.defer(ephemeral=True)
        target_user = user or interaction.user  # type: ignore
        target_channel = channel or interaction.channel  # type: ignore
        forced_gender: Gender | None = (gender.value if gender else None)  # type: ignore

        try:
            await self._send_welcome(target_user, target_channel, forced_gender)
        except Exception as e:
            await interaction.followup.send(
                f"Welcome preview failed — **{type(e).__name__}**: {e}\n"
                f"Folder: `{self.folder}`\n"
                f"Tip: set **WELCOME_IMAGES_DIR** and (optional) add `male/` and `female/` subfolders.",
                ephemeral=True,
            )
            return

        await interaction.followup.send("Sent ✅", ephemeral=True)

    # -------- Events --------
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Post a real welcome when someone joins (if a channel is configured)."""
        channel_id = _welcome_channel_id()
        if not channel_id:
            return
        ch = member.guild.get_channel(channel_id)
        if not ch:
            return
        try:
            await self._send_welcome(member, ch, None)
        except Exception:
            # Never block joins
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(WelcomeCog(bot))
