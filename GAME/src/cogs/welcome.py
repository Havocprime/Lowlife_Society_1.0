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
from src.db.dal import ensure_npc_intro_table, log_npc_intro

# Audit is optional; fall back to a no-op decorator if it's not ready
try:
    from src.core.audit import audit_event
except Exception:  # pragma: no cover
    def audit_event(*_args, **_kwargs):
        def deco(fn): return fn
        return deco

IMG_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
Gender = Literal["male", "female"]

GUILD_ID = getattr(SETTINGS, "guild_id", None)


def _folder_from_config() -> Path:
    env = os.getenv("WELCOME_IMAGES_DIR")
    if env:
        return Path(env).expanduser().resolve()
    here = Path(__file__).resolve()
    game_dir = here.parents[2]
    return (game_dir / "assets" / "mugshots").resolve()


def _welcome_channel_id() -> Optional[int]:
    raw = os.getenv("WELCOME_CHANNEL_ID") or getattr(SETTINGS, "welcome_channel_id", None)
    try:
        return int(raw) if raw else None
    except Exception:
        return None


def _pick_random_image(base: Path, gender: Gender | None) -> Path:
    folder = base
    if gender and (base / gender).exists():
        folder = base / gender
    files = [p for p in folder.glob("*") if p.is_file() and p.suffix.lower() in IMG_EXTS]
    if not files:
        raise FileNotFoundError(f"No image files found in {folder}")
    return random.choice(files)


class WelcomeCog(commands.Cog):
    """Welcome system: random mugshot + NPC name + gritty intro w/ hand-off."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.folder = _folder_from_config()
        self._inflight: set[int] = set()  # dedupe per-interaction
        try:
            ensure_npc_intro_table()
        except Exception:
            pass

    async def _send_welcome(
        self,
        member: discord.Member,
        channel: discord.abc.Messageable,
        gender: Gender | None = None,
    ) -> None:
        if gender is None and (self.folder / "male").exists() and (self.folder / "female").exists():
            gender = random.choice(["male", "female"])  # type: ignore

        img_path = _pick_random_image(self.folder, gender)
        filename = img_path.name

        title = f"Welcome to The City: {member.display_name}"
        file = discord.File(img_path, filename=filename)

        npc_name = random_name(gender=gender or "any")
        intro_text, handoff_type, contact_value, extra = build_intro(gender)

        embed = discord.Embed(title=title, colour=discord.Color.gold())
        embed.description = intro_text
        embed.set_image(url=f"attachment://{filename}")
        embed.set_footer(text=f"– {npc_name}.\nLowlife Society")

        msg = await channel.send(embed=embed, file=file)

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

    # -------- shared handler for both command variants (safe against double-acks) --------
    async def _handle_welcome_preview(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.Member],
        channel: Optional[discord.abc.GuildChannel],
        gender_choice: Optional[app_commands.Choice[str]],
        suffix: str,
    ) -> None:
        # De-dupe by interaction id (covers rare double dispatch)
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

            target_user = user or interaction.user  # type: ignore
            target_channel = channel or interaction.channel  # type: ignore
            forced_gender: Gender | None = (gender_choice.value if gender_choice else None)  # type: ignore

            await self._send_welcome(target_user, target_channel, forced_gender)

            # Followup is safe even if something already responded; swallow errors
            try:
                await interaction.followup.send(f"Sent ✅ {suffix}", ephemeral=True)
            except discord.HTTPException:
                pass

        except Exception as e:
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

    # ----- Commands -----
    # Make the command guild-scoped when GUILD_ID is present (instant updates).
    if GUILD_ID:
        @app_commands.guilds(discord.Object(id=GUILD_ID))
        @app_commands.command(name="welcome_preview", description="Preview the welcome post (random mugshot + NPC).")
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
            await self._handle_welcome_preview(interaction, user, channel, gender, "(guild-scoped)")
    else:
        @app_commands.command(name="welcome_preview", description="Preview the welcome post (random mugshot + NPC).")
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
            note = "(global — if you ever see **Unknown Integration**, set `guild_id` in .env and /sync)"
            await self._handle_welcome_preview(interaction, user, channel, gender, note)

    # ----- Events -----
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        channel_id = _welcome_channel_id()
        if not channel_id:
            return
        ch = member.guild.get_channel(channel_id)
        if not ch:
            return
        try:
            await self._send_welcome(member, ch, None)
        except Exception:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(WelcomeCog(bot))
