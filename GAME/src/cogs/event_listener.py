# GAME/src/cogs/event_listener.py
from __future__ import annotations
from typing import Any, Optional

import discord
from discord.ext import commands

# Import the module (safer than name imports during early init)
from src.core import audit as audit_core


def _sid(x: Any) -> Optional[int]:
    return getattr(x, "id", None)


class EventListener(commands.Cog):
    """Event listeners that write into audit_log via audit_core.log_action(...)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -------- Messages --------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        await audit_core.log_action(
            guild_id=_sid(message.guild),
            channel_id=_sid(message.channel),
            user_id=_sid(message.author),
            action_type="message",
            details={
                "message_id": message.id,
                "content": message.content,
                "attachments": [a.url for a in message.attachments],
            },
        )

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if after.author and after.author.bot:
            return
        await audit_core.log_action(
            guild_id=_sid(after.guild),
            channel_id=_sid(after.channel),
            user_id=_sid(after.author),
            action_type="message_edit",
            details={
                "message_id": after.id,
                "before": {"content": before.content},
                "after": {"content": after.content},
            },
        )

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        await audit_core.log_action(
            guild_id=payload.guild_id,
            channel_id=payload.channel_id,
            user_id=None,
            action_type="message_delete",
            details={"message_id": payload.message_id},
        )

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent):
        await audit_core.log_action(
            guild_id=payload.guild_id,
            channel_id=payload.channel_id,
            user_id=None,
            action_type="message_bulk_delete",
            details={"message_ids": list(payload.message_ids), "count": len(payload.message_ids)},
        )

    # -------- Reactions --------
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        await audit_core.log_action(
            guild_id=payload.guild_id,
            channel_id=payload.channel_id,
            user_id=payload.user_id,
            action_type="reaction_add",
            details={"message_id": payload.message_id, "emoji": str(payload.emoji)},
        )

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        await audit_core.log_action(
            guild_id=payload.guild_id,
            channel_id=payload.channel_id,
            user_id=payload.user_id,
            action_type="reaction_remove",
            details={"message_id": payload.message_id, "emoji": str(payload.emoji)},
        )

    # -------- Members / Presence / Voice --------
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        await audit_core.log_action(
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
    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        await audit_core.log_action(
            guild_id=_sid(after.guild),
            channel_id=None,
            user_id=_sid(after),
            action_type="presence_update",
            details={
                "status_before": str(before.status),
                "status_after": str(after.status),
                "activities": [getattr(a, "name", None) for a in (after.activities or []) if getattr(a, "name", None)],
            },
        )

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        await audit_core.log_action(
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
        await audit_core.log_action(
            guild_id=_sid(channel.guild),
            channel_id=_sid(channel),
            user_id=None,
            action_type="channel_create",
            details={"name": str(channel)},
        )

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        await audit_core.log_action(
            guild_id=_sid(channel.guild),
            channel_id=_sid(channel),
            user_id=None,
            action_type="channel_delete",
            details={"name": str(channel)},
        )

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        await audit_core.log_action(
            guild_id=_sid(after.guild),
            channel_id=_sid(after),
            user_id=None,
            action_type="channel_update",
            details={"before": str(before), "after": str(after)},
        )

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        await audit_core.log_action(
            guild_id=_sid(thread.guild),
            channel_id=_sid(thread),
            user_id=_sid(thread.owner),
            action_type="thread_create",
            details={"name": thread.name},
        )

    @commands.Cog.listener()
    async def on_thread_delete(self, thread: discord.Thread):
        await audit_core.log_action(
            guild_id=_sid(thread.guild),
            channel_id=_sid(thread),
            user_id=None,
            action_type="thread_delete",
            details={"name": thread.name},
        )

    @commands.Cog.listener()
    async def on_thread_update(self, before: discord.Thread, after: discord.Thread):
        await audit_core.log_action(
            guild_id=_sid(after.guild),
            channel_id=_sid(after),
            user_id=None,
            action_type="thread_update",
            details={"name": after.name, "locked": after.locked, "archived": after.archived},
        )

    # -------- Roles / Invites / Webhooks / Emojis --------
    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        await audit_core.log_action(
            guild_id=_sid(role.guild),
            channel_id=None,
            user_id=None,
            action_type="role_create",
            details={"role_id": role.id, "name": role.name},
        )

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        await audit_core.log_action(
            guild_id=_sid(role.guild),
            channel_id=None,
            user_id=None,
            action_type="role_delete",
            details={"role_id": role.id, "name": role.name},
        )

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        await audit_core.log_action(
            guild_id=_sid(after.guild),
            channel_id=None,
            user_id=None,
            action_type="role_update",
            details={"role_id": after.id, "name": after.name},
        )

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        await audit_core.log_action(
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
        await audit_core.log_action(
            guild_id=_sid(invite.guild),
            channel_id=_sid(invite.channel),
            user_id=None,
            action_type="invite_delete",
            details={"code": getattr(invite, "code", None)},
        )

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel):
        await audit_core.log_action(
            guild_id=_sid(channel.guild),
            channel_id=_sid(channel),
            user_id=None,
            action_type="webhook_update",
            details={},
        )

    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild: discord.Guild, before, after):
        await audit_core.log_action(
            guild_id=_sid(guild),
            channel_id=None,
            user_id=None,
            action_type="emoji_update",
            details={"before": [e.id for e in before], "after": [e.id for e in after]},
        )

    @commands.Cog.listener()
    async def on_guild_stickers_update(self, guild: discord.Guild, before, after):
        await audit_core.log_action(
            guild_id=_sid(guild),
            channel_id=None,
            user_id=None,
            action_type="sticker_update",
            details={"before": [s.id for s in before], "after": [s.id for s in after]},
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(EventListener(bot))
