# GAME/src/cogs/event_listener.py
from __future__ import annotations

from typing import Any, Optional, List
from importlib import import_module

import discord
from discord.ext import commands

# We import the module (not the symbol) so early import order wonâ€™t explode.
from src.core import audit as audit_core


# ---------------- internals ----------------

def _sid(x: Any) -> Optional[int]:
    """Return .id if present, else None."""
    return getattr(x, "id", None)


async def _audit_log_action(**kwargs):
    """
    Robust wrapper around src.core.audit.log_action(...).
    If the module hasnâ€™t finished initializing yet, we late-import and try again.
    Never raise out of event dispatch.
    """
    try:
        fn = getattr(audit_core, "log_action", None)
        if fn is None:
            mod = import_module("src.core.audit")
            fn = getattr(mod, "log_action", None)
        if fn is not None:
            await fn(**kwargs)
    except Exception:
        # Never crash event dispatch because of auditing
        pass


# ---------------- presence helpers ----------------

def _activity_names(acts: Optional[List[discord.Activity]]) -> List[str]:
    """Return up to 3 human names/states from activities for compact logging."""
    out: List[str] = []
    for a in acts or []:
        name = getattr(a, "name", None) or getattr(a, "state", None)
        if name:
            out.append(str(name))
        if len(out) >= 3:
            break
    return out


def _presence_snapshot(m: discord.Member) -> dict:
    """Capture a normalized snapshot of member presence/devices/activities."""
    return {
        "status": str(getattr(m, "status", "offline")),
        "desktop": str(getattr(m, "desktop_status", "offline")),
        "mobile":  str(getattr(m, "mobile_status", "offline")),
        "web":     str(getattr(m, "web_status", "offline")),
        "activities": _activity_names(getattr(m, "activities", None)),
    }


def _presence_changed(before: discord.Member, after: discord.Member) -> bool:
    """Return True if any presence/devices/activities changed."""
    if str(getattr(before, "status", "")) != str(getattr(after, "status", "")):
        return True
    if str(getattr(before, "desktop_status", "")) != str(getattr(after, "desktop_status", "")):
        return True
    if str(getattr(before, "mobile_status", "")) != str(getattr(after, "mobile_status", "")):
        return True
    if str(getattr(before, "web_status", "")) != str(getattr(after, "web_status", "")):
        return True
    if _activity_names(getattr(before, "activities", None)) != _activity_names(getattr(after, "activities", None)):
        return True
    return False


# ---------------- Cog ----------------

class EventListener(commands.Cog):
    """
    Comprehensive event listeners that write to the audit ledger via _audit_log_action(...).
    These are **separate** from the light-weight `events` table writers.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -------- Messages --------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        await _audit_log_action(
            guild_id=_sid(message.guild),
            channel_id=_sid(message.channel),
            user_id=_sid(message.author),
            action_type="message",
            details={
                "message_id": message.id,
                "content": message.content,
                "attachments": [a.url for a in message.attachments],
                "channel_name": getattr(message.channel, "name", None),
            },
        )

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if after.guild is None or (after.author and after.author.bot):
            return
        await _audit_log_action(
            guild_id=_sid(after.guild),
            channel_id=_sid(after.channel),
            user_id=_sid(after.author),
            action_type="message_edit",
            details={
                "message_id": after.id,
                "before": {"content": before.content},
                "after": {"content": after.content},
                "channel_name": getattr(after.channel, "name", None),
            },
        )

    # Cached single delete (has content if message was cached)
    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.guild is None:
            return
        await _audit_log_action(
            guild_id=_sid(message.guild),
            channel_id=_sid(message.channel),
            user_id=_sid(getattr(message, "author", None)),
            action_type="message_delete",
            details={
                "message_id": message.id,
                "before": {"content": message.content or ""},
                "channel_name": getattr(message.channel, "name", None),
            },
        )

    # Raw single delete (no cache required)
    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        if payload.guild_id is None:
            return
        await _audit_log_action(
            guild_id=payload.guild_id,
            channel_id=payload.channel_id,
            user_id=None,
            action_type="message_delete",
            details={"message_id": payload.message_id},
        )

    # Cached bulk delete
    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages: list[discord.Message]):
        if not messages:
            return
        m0 = messages[0]
        if m0.guild is None:
            return
        cached_with_text = sum(1 for m in messages if (m.content or "").strip())
        await _audit_log_action(
            guild_id=_sid(m0.guild),
            channel_id=_sid(m0.channel),
            user_id=None,
            action_type="message_bulk_delete",
            details={
                "count": len(messages),
                "cached_with_text": cached_with_text,
            },
        )

    # Raw bulk delete
    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent):
        if payload.guild_id is None:
            return
        await _audit_log_action(
            guild_id=payload.guild_id,
            channel_id=payload.channel_id,
            user_id=None,
            action_type="message_bulk_delete",
            details={"message_ids": list(payload.message_ids), "count": len(payload.message_ids)},
        )

    # -------- Reactions --------

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        await _audit_log_action(
            guild_id=payload.guild_id,
            channel_id=payload.channel_id,
            user_id=payload.user_id,
            action_type="reaction_add",
            details={"message_id": payload.message_id, "emoji": str(payload.emoji)},
        )

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        await _audit_log_action(
            guild_id=payload.guild_id,
            channel_id=payload.channel_id,
            user_id=payload.user_id,
            action_type="reaction_remove",
            details={"message_id": payload.message_id, "emoji": str(payload.emoji)},
        )

    # -------- Members / Presence / Voice --------

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        await _audit_log_action(
            guild_id=_sid(after.guild),
            channel_id=None,
            user_id=_sid(after),
            action_type="member_update",
            details={
                "roles_before": [r.id for r in before.roles],
                "roles_after": [r.id for r in after.roles],
                "nick_before": before.nick,
                "nick_after": after.nick,
            },
        )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await _audit_log_action(
            guild_id=_sid(member.guild),
            channel_id=None,
            user_id=_sid(member),
            action_type="member_join",
            details={"name": str(member)},
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        await _audit_log_action(
            guild_id=_sid(member.guild),
            channel_id=None,
            user_id=_sid(member),
            action_type="member_remove",
            details={"name": str(member)},
        )

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        # Reduce noise â€” only log when something truly changed.
        if not _presence_changed(before, after):
            return

        before_snap = _presence_snapshot(before)
        after_snap = _presence_snapshot(after)

        # Short human-readable summary so the generic text extractor shows content.
        devbits = []
        if after_snap["desktop"] != "offline":
            devbits.append(f"ðŸ–¥ {after_snap['desktop']}")
        if after_snap["mobile"] != "offline":
            devbits.append(f"ðŸ“± {after_snap['mobile']}")
        if after_snap["web"] != "offline":
            devbits.append(f"ðŸŒ {after_snap['web']}")
        devs = " | ".join(devbits)
        acts = ", ".join(after_snap["activities"][:2])
        tail = " â€¢ ".join([p for p in (devs, acts) if p])
        summary = f"{before_snap['status']} â†’ {after_snap['status']}"
        if tail:
            summary += f" â€” {tail}"

        await _audit_log_action(
            guild_id=_sid(after.guild),
            channel_id=None,  # presence is not channel-scoped
            user_id=_sid(after),
            action_type="presence",
            details={
                # backward-compat keys:
                "status_before": before_snap["status"],
                "status_after":  after_snap["status"],
                # richer structured snapshots:
                "before": before_snap,
                "after":  after_snap,
                # and a generic "text" so existing inspector logic can display it nicely
                "text": summary,
            },
        )

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ):
        await _audit_log_action(
            guild_id=_sid(member.guild),
            channel_id=None,
            user_id=_sid(member),
            action_type="voice_update",
            details={
                "before_channel": _sid(before.channel),
                "after_channel": _sid(after.channel),
                "mute_before": before.mute,
                "mute_after": after.mute,
                "deaf_before": before.deaf,
                "deaf_after": after.deaf,
                "self_mute_before": before.self_mute,
                "self_mute_after": after.self_mute,
            },
        )

    # -------- Channels / Threads --------

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        await _audit_log_action(
            guild_id=_sid(channel.guild),
            channel_id=_sid(channel),
            user_id=None,
            action_type="channel_create",
            details={"name": str(channel)},
        )

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        await _audit_log_action(
            guild_id=_sid(channel.guild),
            channel_id=_sid(channel),
            user_id=None,
            action_type="channel_delete",
            details={"name": str(channel)},
        )

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        await _audit_log_action(
            guild_id=_sid(after.guild),
            channel_id=_sid(after),
            user_id=None,
            action_type="channel_update",
            details={"before": str(before), "after": str(after)},
        )

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        await _audit_log_action(
            guild_id=_sid(thread.guild),
            channel_id=_sid(thread),
            user_id=_sid(thread.owner),
            action_type="thread_create",
            details={"name": thread.name},
        )

    @commands.Cog.listener()
    async def on_thread_delete(self, thread: discord.Thread):
        await _audit_log_action(
            guild_id=_sid(thread.guild),
            channel_id=_sid(thread),
            user_id=None,
            action_type="thread_delete",
            details={"name": thread.name},
        )

    @commands.Cog.listener()
    async def on_thread_update(self, before: discord.Thread, after: discord.Thread):
        await _audit_log_action(
            guild_id=_sid(after.guild),
            channel_id=_sid(after),
            user_id=None,
            action_type="thread_update",
            details={"name": after.name, "locked": after.locked, "archived": after.archived},
        )

    # -------- Roles / Invites / Webhooks / Emojis --------

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        await _audit_log_action(
            guild_id=_sid(role.guild),
            channel_id=None,
            user_id=None,
            action_type="role_create",
            details={"role_id": role.id, "name": role.name},
        )

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        await _audit_log_action(
            guild_id=_sid(role.guild),
            channel_id=None,
            user_id=None,
            action_type="role_delete",
            details={"role_id": role.id, "name": role.name},
        )

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        await _audit_log_action(
            guild_id=_sid(after.guild),
            channel_id=None,
            user_id=None,
            action_type="role_update",
            details={"role_id": after.id, "name": after.name},
        )

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        await _audit_log_action(
            guild_id=_sid(invite.guild),
            channel_id=_sid(invite.channel),
            user_id=_sid(invite.inviter),
            action_type="invite_create",
            details={
                "code": getattr(invite, "code", None),
                "max_uses": invite.max_uses,
                "expires_at": str(invite.expires_at) if invite.expires_at else None,
            },
        )

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        await _audit_log_action(
            guild_id=_sid(invite.guild),
            channel_id=_sid(invite.channel),
            user_id=None,
            action_type="invite_delete",
            details={"code": getattr(invite, "code", None)},
        )

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel):
        await _audit_log_action(
            guild_id=_sid(channel.guild),
            channel_id=_sid(channel),
            user_id=None,
            action_type="webhook_update",
            details={},
        )

    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild: discord.Guild, before, after):
        await _audit_log_action(
            guild_id=_sid(guild),
            channel_id=None,
            user_id=None,
            action_type="emoji_update",
            details={"before": [e.id for e in before], "after": [e.id for e in after]},
        )

    @commands.Cog.listener()
    async def on_guild_stickers_update(self, guild: discord.Guild, before, after):
        await _audit_log_action(
            guild_id=_sid(guild),
            channel_id=None,
            user_id=None,
            action_type="sticker_update",
            details={"before": [s.id for s in before], "after": [s.id for s in after]},
        )


# ---- extension entry point ----
async def setup(bot: commands.Bot):
    await bot.add_cog(EventListener(bot))
