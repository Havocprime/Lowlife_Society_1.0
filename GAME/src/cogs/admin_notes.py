from __future__ import annotations

import os
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

# DB helpers
from src.core.events import add_admin_note, list_admin_notes, delete_admin_note  # type: ignore


def _is_admin(m: discord.Member) -> bool:
    """Gate all /notes commands to server admins."""
    if m.guild_permissions.administrator:
        return True
    # Optional extra role-based gate via env if you want it
    role_id = int(os.getenv("ADMIN_ROLE_ID", "0") or "0")
    return bool(role_id and any(r.id == role_id for r in m.roles))


# Export a top-level group so bot.py can `from src.cogs.admin_notes import notes`
notes = app_commands.Group(
    name="notes",
    description="Admin-only: manage private admin notes for members",
)


@notes.command(name="add", description="Add a private admin note to a member")
@app_commands.describe(user="Target member", note="Note text")
async def notes_add(interaction: discord.Interaction, user: discord.Member, note: str):
    if not isinstance(interaction.user, discord.Member) or not _is_admin(interaction.user):
        await interaction.response.send_message("Nope.", ephemeral=True)
        return

    note = (note or "").strip()
    if not note:
        await interaction.response.send_message("Note text cannot be empty.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True, thinking=True)

    # IMPORTANT: call add_admin_note POSITIONALLY to match its signature
    # expected order: (guild_id, user_id, admin_id, note_text)
    try:
        nid = add_admin_note(interaction.guild.id, user.id, interaction.user.id, note)  # type: ignore[arg-type]
    except TypeError:
        # If your events helper uses a slightly different order, you can try this
        # fallback; remove if not needed.
        nid = add_admin_note(interaction.guild.id, user.id, note, interaction.user.id)  # type: ignore[misc]

    await interaction.followup.send(
        f"🗒️ Added note `#{nid}` for {user.mention}: {discord.utils.escape_markdown(note)}",
        ephemeral=True,
    )


@notes.command(name="list", description="List recent admin notes for a member")
@app_commands.describe(user="Target member", limit="How many to show (1–50)")
async def notes_list(
    interaction: discord.Interaction,
    user: discord.Member,
    limit: Optional[int] = 10,
):
    if not isinstance(interaction.user, discord.Member) or not _is_admin(interaction.user):
        await interaction.response.send_message("Nope.", ephemeral=True)
        return

    limit = max(1, min(int(limit or 10), 50))
    rows = list_admin_notes(interaction.guild.id, user.id, limit)  # -> [(id, ts, admin_id, text), ...]

    if not rows:
        await interaction.response.send_message(f"No notes found for {user.mention}.", ephemeral=True)
        return

    lines = []
    for nid, ts, admin_id, text in rows:
        author = f"<@{admin_id}>" if admin_id else "—"
        safe = discord.utils.escape_markdown(text or "")
        lines.append(f"`#{nid}` `{ts}` — {author}: {safe}")

    e = discord.Embed(
        title=f"Admin Notes — {user} (latest {len(rows)})",
        colour=discord.Colour.blurple(),
        description="\n".join(lines)[:4096],
    )
    e.set_thumbnail(url=user.display_avatar.url)
    await interaction.response.send_message(embed=e, ephemeral=True)


@notes.command(name="delete", description="Delete a note by its ID")
@app_commands.describe(note_id="Note ID from /notes list")
async def notes_delete(interaction: discord.Interaction, note_id: int):
    if not isinstance(interaction.user, discord.Member) or not _is_admin(interaction.user):
        await interaction.response.send_message("Nope.", ephemeral=True)
        return

    # Most implementations only need the ID, but if yours requires guild_id too,
    # your helper can ignore the extra arg.
    try:
        deleted = delete_admin_note(note_id)  # type: ignore[call-arg]
    except TypeError:
        deleted = delete_admin_note(interaction.guild.id, note_id)  # type: ignore[misc]

    if deleted:
        await interaction.response.send_message(f"🗑️ Deleted note `#{note_id}`.", ephemeral=True)
    else:
        await interaction.response.send_message(f"Couldn't find note `#{note_id}`.", ephemeral=True)


class AdminNotes(commands.Cog):
    """Empty cog class so the extension can be loaded; commands are on the group above."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminNotes(bot))
    # If bot.py didn’t pre-register the group, register it here too:
    try:
        from ..bot.bot import GUILD_ID  # optional import
        if GUILD_ID:
            bot.tree.add_command(notes, guild=discord.Object(id=GUILD_ID))
        else:
            bot.tree.add_command(notes)
    except Exception:
        # Fallback: still add globally
        bot.tree.add_command(notes)
