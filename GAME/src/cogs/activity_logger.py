from __future__ import annotations

import json
import os
import re
import sqlite3
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any

import discord
from discord.ext import commands

from src.core.events import DB_PATH

URL_RE = re.compile(r"https?://\S+", re.I)
DISCORD_INVITE_RE = re.compile(r"(discord\.gg|discord\.com/invite)/\S+", re.I)

RISKY_PERMS = {
    "administrator",
    "manage_guild",
    "manage_roles",
    "manage_channels",
    "manage_messages",
    "manage_webhooks",
    "ban_members",
    "kick_members",
    "mention_everyone",
    "priority_speaker",
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _insert(kind: str, user_id: int, guild_id: int, payload: dict[str, Any]) -> None:
    try:
        with sqlite3.connect(DB_PATH) as con:
            con.execute(
                "INSERT INTO events (ts_utc, user_id, guild_id, kind, payload) VALUES (?,?,?,?,?)",
                (
                    _utcnow(),
                    int(user_id),
                    int(guild_id),
                    kind,
                    json.dumps(payload, separators=(",", ":")),
                ),
            )
    except Exception:
        pass


def _attachment_type(att: discord.Attachment) -> str:
    ct = (att.content_type or "").lower()
    if ct.startswith("image/"):
        return "image"
    if ct.startswith("video/"):
        return "video"
    if ct.startswith("audio/"):
        return "audio"
    if ct.startswith("text/"):
        return "text"
    if ct:
        return ct.split(";")[0]
    name = (att.filename or "").lower()
    for ext, tag in (
        (".png", "image"),
        (".jpg", "image"),
        (".jpeg", "image"),
        (".gif", "image"),
        (".mp4", "video"),
        (".mov", "video"),
        (".webm", "video"),
        (".mp3", "audio"),
        (".wav", "audio"),
        (".flac", "audio"),
    ):
        if name.endswith(ext):
            return tag
    return "file"


def _perm_names(perms: discord.Permissions) -> set[str]:
    out = set()
    for name, allowed in perms:
        if allowed:
            out.add(name)
    return out


def _agg_member_perms(m: discord.Member) -> discord.Permissions:
    value = 0
    for r in m.roles:
        value |= r.permissions.value
    return discord.Permissions(value=value)


class ActivityLogger(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.alert_channel_id = int(os.getenv("ADMIN_ALERT_CHANNEL_ID", "0") or 0)

        # small in-memory cache so deleted messages can include text
        self._msg_cache: "OrderedDict[int, dict]" = OrderedDict()
        self._msg_cache_max = int(os.getenv("LOG_MSG_CACHE", "5000") or 5000)

        # optional: exclude channels entirely (comma-separated IDs)
        raw_exclude = os.getenv("LOG_EXCLUDE_CHANNEL_IDS", "")
        self._exclude_channel_ids = {int(x) for x in raw_exclude.split(",") if x.strip().isdigit()}

    def _cache_put(self, m: discord.Message, body: str) -> None:
        try:
            self._msg_cache[m.id] = {
                "channel_id": m.channel.id,
                "author_id": m.author.id,
                "content": body,
            }
            self._msg_cache.move_to_end(m.id)
            if len(self._msg_cache) > self._msg_cache_max:
                self._msg_cache.popitem(last=False)
        except Exception:
            pass

    def _is_excluded(self, channel_id: int) -> bool:
        return channel_id in self._exclude_channel_ids

    # -------- messages --------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        if self._is_excluded(getattr(message.channel, "id", 0)):
            return
        body_limit = 500 if os.getenv("LOG_MESSAGE_BODY", "1") == "1" else 0
        content = message.content or ""
        body = content[:body_limit] if body_limit else ""
        urls = URL_RE.findall(content) if content else []
        payload = {
            "channel_id": str(message.channel.id),
            "channel_name": getattr(message.channel, "name", ""),
            "message_id": str(message.id),
            "content": body,
            "content_len": len(content),
            "has_invite": bool(DISCORD_INVITE_RE.search(content or "")),
            "url_count": len(urls),
            "attachment_count": len(message.attachments or []),
            "attachment_types": [_attachment_type(a) for a in (message.attachments or [])],
        }
        _insert("message", message.author.id, message.guild.id, payload)
        if body:
            self._cache_put(message, body)

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent):
        guild_id = payload.guild_id or 0
        if not guild_id:
            return
        if self._is_excluded(payload.channel_id):
            return
        data = payload.data or {}
        content = data.get("content")
        if content is None and os.getenv("LOG_MESSAGE_BODY_FETCH", "0") == "1":
            try:
                ch = self.bot.get_channel(payload.channel_id)
                if isinstance(ch, discord.abc.Messageable):
                    m = await ch.fetch_message(payload.message_id)  # type: ignore
                    content = m.content
            except Exception:
                content = None
        body = (content or "")[:500] if content else ""
        _insert(
            "message_edit",
            int(data.get("author", {}).get("id", 0)) or 0,
            guild_id,
            {
                "channel_id": str(payload.channel_id),
                "message_id": str(payload.message_id),
                "content": body,
                "content_len": len(content or ""),
            },
        )
        try:
            if payload.message_id in self._msg_cache and body:
                self._msg_cache[payload.message_id]["content"] = body
                self._msg_cache.move_to_end(payload.message_id)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        cached = self._msg_cache.pop(payload.message_id, None)
        _insert(
            "message_delete",
            int((cached or {}).get("author_id") or 0),
            payload.guild_id or 0,
            {
                "channel_id": str(payload.channel_id),
                "message_id": str(payload.message_id),
                "content": (cached or {}).get("content"),
            },
        )

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent):
        cached_count = sum(1 for mid in payload.message_ids if mid in self._msg_cache)
        for mid in list(payload.message_ids):
            self._msg_cache.pop(mid, None)
        _insert(
            "message_bulk_delete",
            0,
            payload.guild_id or 0,
            {
                "channel_id": str(payload.channel_id),
                "ids": [str(i) for i in payload.message_ids],
                "count": len(payload.message_ids),
                "cached_with_text": cached_count,
            },
        )

    # -------- reactions (raw) --------
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        _insert(
            "reaction_add",
            payload.user_id,
            payload.guild_id or 0,
            {
                "channel_id": str(payload.channel_id),
                "message_id": str(payload.message_id),
                "emoji": {
                    "name": payload.emoji.name,
                    "id": str(payload.emoji.id) if payload.emoji.id else None,
                    "animated": payload.emoji.animated,
                },
            },
        )

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        _insert(
            "reaction_remove",
            payload.user_id,
            payload.guild_id or 0,
            {
                "channel_id": str(payload.channel_id),
                "message_id": str(payload.message_id),
                "emoji": {
                    "name": payload.emoji.name,
                    "id": str(payload.emoji.id) if payload.emoji.id else None,
                    "animated": payload.emoji.animated,
                },
            },
        )

    @commands.Cog.listener()
    async def on_raw_reaction_clear(self, payload: discord.RawReactionClearEvent):
        _insert(
            "reaction_clear",
            0,
            payload.guild_id or 0,
            {
                "channel_id": str(payload.channel_id),
                "message_id": str(payload.message_id),
            },
        )

    @commands.Cog.listener()
    async def on_raw_reaction_clear_emoji(self, payload: discord.RawReactionClearEmojiEvent):
        _insert(
            "reaction_clear_emoji",
            0,
            payload.guild_id or 0,
            {
                "channel_id": str(payload.channel_id),
                "message_id": str(payload.message_id),
                "emoji": {
                    "name": payload.emoji.name,
                    "id": str(payload.emoji.id) if payload.emoji.id else None,
                    "animated": payload.emoji.animated,
                },
            },
        )

    # -------- presence / activity --------
    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        if not after.guild:
            return
        if str(before.status) != str(after.status):
            _insert(
                "presence",
                after.id,
                after.guild.id,
                {"before": str(before.status), "after": str(after.status)},
            )
        bname = (before.activities or [None])[0].name if before.activities else None
        aname = (after.activities or [None])[0].name if after.activities else None
        if bname != aname:
            _insert("activity", after.id, after.guild.id, {"before": bname, "after": aname})

    # -------- voice --------
    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ):
        g = member.guild.id if member.guild else 0
        if before.channel != after.channel:
            _insert(
                "voice_channel",
                member.id,
                g,
                {
                    "before": str(getattr(before.channel, "id", "")) if before.channel else None,
                    "after": str(getattr(after.channel, "id", "")) if after.channel else None,
                },
            )
        if before.self_mute != after.self_mute or before.mute != after.mute:
            _insert("voice_mute", member.id, g, {"self": after.self_mute, "server": after.mute})
        if before.self_deaf != after.self_deaf or before.deaf != after.deaf:
            _insert("voice_deaf", member.id, g, {"self": after.self_deaf, "server": after.deaf})
        if before.self_stream != after.self_stream:
            _insert("voice_stream", member.id, g, {"streaming": after.self_stream})

    # -------- pins --------
    @commands.Cog.listener()
    async def on_guild_channel_pins_update(
        self, channel: discord.abc.GuildChannel, last_pin: datetime | None
    ):
        gid = getattr(getattr(channel, "guild", None), "id", 0)
        if gid:
            _insert(
                "pins_update",
                0,
                gid,
                {
                    "channel_id": str(channel.id),
                    "last_pin_utc": (
                        last_pin.isoformat().replace("+00:00", "Z") if last_pin else None
                    ),
                },
            )

    # -------- guild scheduled events --------
    @commands.Cog.listener()
    async def on_scheduled_event_create(self, event: discord.ScheduledEvent):
        if event.guild:
            _insert(
                "scheduled_event_create",
                0,
                event.guild.id,
                {"id": str(event.id), "name": event.name},
            )

    @commands.Cog.listener()
    async def on_scheduled_event_delete(self, event: discord.ScheduledEvent):
        if event.guild:
            _insert(
                "scheduled_event_delete",
                0,
                event.guild.id,
                {"id": str(event.id), "name": event.name},
            )

    @commands.Cog.listener()
    async def on_scheduled_event_update(
        self, before: discord.ScheduledEvent, after: discord.ScheduledEvent
    ):
        if after.guild:
            _insert("scheduled_event_update", 0, after.guild.id, {"id": str(after.id)})

    # -------- stage (if used) --------
    @commands.Cog.listener()
    async def on_stage_instance_create(self, stage: discord.StageInstance):
        if stage.guild:
            _insert("stage_create", 0, stage.guild.id, {"channel_id": str(stage.channel.id)})

    @commands.Cog.listener()
    async def on_stage_instance_delete(self, stage: discord.StageInstance):
        if stage.guild:
            _insert("stage_delete", 0, stage.guild.id, {"channel_id": str(stage.channel.id)})

    # -------- emoji / sticker updates --------
    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild: discord.Guild, before, after):
        before_ids = {e.id for e in before}
        after_ids = {e.id for e in after}
        _insert(
            "emoji_update",
            0,
            guild.id,
            {
                "added": [str(i) for i in (after_ids - before_ids)],
                "removed": [str(i) for i in (before_ids - after_ids)],
            },
        )

    @commands.Cog.listener()
    async def on_guild_stickers_update(self, guild: discord.Guild, before, after):
        before_ids = {s.id for s in before}
        after_ids = {s.id for s in after}
        _insert(
            "sticker_update",
            0,
            guild.id,
            {
                "added": [str(i) for i in (after_ids - before_ids)],
                "removed": [str(i) for i in (before_ids - after_ids)],
            },
        )

    # -------- role updates --------
    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        diffs = {}
        for attr in ("name", "color", "position", "mentionable", "hoist"):
            b = getattr(before, attr, None)
            a = getattr(after, attr, None)
            if b != a:
                diffs[attr] = {"before": str(b), "after": str(a)}
        if before.permissions.value != after.permissions.value:
            diffs["permissions"] = {
                "before": before.permissions.value,
                "after": after.permissions.value,
            }
        if diffs:
            _insert("role_update", 0, after.guild.id, {"role_id": str(after.id), **diffs})

    # -------- guild updates --------
    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        diffs = {}
        for attr in (
            "name",
            "icon",
            "banner",
            "verification_level",
            "afk_timeout",
            "vanity_url_code",
        ):
            b = getattr(before, attr, None)
            a = getattr(after, attr, None)
            if b != a:
                diffs[attr] = {"before": str(b), "after": str(a)}
        if diffs:
            _insert("guild_update", 0, after.id, diffs)

    # -------- channel updates --------
    @commands.Cog.listener()
    async def on_guild_channel_update(
        self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel
    ):
        diffs = {}
        for attr in ("name", "topic", "nsfw"):
            b = getattr(before, attr, None)
            a = getattr(after, attr, None)
            if b != a:
                diffs[attr] = {"before": b, "after": a}
        try:
            if getattr(before, "slowmode_delay", None) != getattr(after, "slowmode_delay", None):
                diffs["slowmode"] = {
                    "before": getattr(before, "slowmode_delay", None),
                    "after": getattr(after, "slowmode_delay", None),
                }
        except Exception:
            pass
        if before.overwrites != after.overwrites:
            diffs["overwrites_changed"] = True
        if diffs:
            _insert("channel_update", 0, after.guild.id, {"channel_id": str(after.id), **diffs})

    # -------- audit log --------
    @commands.Cog.listener()
    async def on_audit_log_entry_create(self, entry: discord.AuditLogEntry):
        try:
            changes = []
            if entry.changes:
                for c in entry.changes:
                    changes.append(
                        {
                            "attr": c.attribute,
                            "before": getattr(c, "before", None),
                            "after": getattr(c, "after", None),
                        }
                    )
            payload = {
                "action": str(entry.action),
                "executor_id": str(getattr(entry.user, "id", "") or ""),
                "target_id": str(getattr(entry.target, "id", "") or ""),
                "reason": entry.reason or None,
                "changes": changes or None,
            }
            guild_id = entry.guild.id if entry.guild else 0
            tgt_id = getattr(entry.target, "id", None) or 0
            _insert("audit_log", int(tgt_id), int(guild_id), payload)
        except Exception:
            pass

    # -------- bans / unbans --------
    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        _insert("member_ban", user.id, guild.id, {})

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        _insert("member_unban", user.id, guild.id, {})

    # -------- members / roles / perm diff --------
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        g = after.guild.id if after.guild else 0
        if before.nick != after.nick:
            _insert("nick", after.id, g, {"before": before.nick, "after": after.nick})

        bset = {r.id for r in before.roles}
        aset = {r.id for r in after.roles}
        added = list(aset - bset)
        removed = list(bset - aset)
        if added or removed:
            _insert(
                "roles",
                after.id,
                g,
                {"added": [str(i) for i in added], "removed": [str(i) for i in removed]},
            )

        bp = _agg_member_perms(before)
        ap = _agg_member_perms(after)
        bnames = _perm_names(bp)
        anames = _perm_names(ap)
        gained = sorted((anames - bnames) & RISKY_PERMS)
        lost = sorted((bnames - anames) & RISKY_PERMS)
        if gained or lost:
            _insert("perm_diff", after.id, g, {"gained": gained, "lost": lost})
            if self.alert_channel_id and gained:
                ch = after.guild.get_channel(self.alert_channel_id) or self.bot.get_channel(
                    self.alert_channel_id
                )
                if isinstance(ch, discord.abc.Messageable):
                    e = discord.Embed(title="⚠ Risky permissions changed", color=0xFD9644)
                    e.add_field(name="User", value=f"{after.mention} (`{after.id}`)", inline=False)
                    if gained:
                        e.add_field(name="Gained", value=", ".join(gained), inline=False)
                    if lost:
                        e.add_field(name="Lost", value=", ".join(lost), inline=False)
                    e.timestamp = datetime.now(timezone.utc)
                    try:
                        await ch.send(embed=e)
                    except Exception:
                        pass

        bto = getattr(before, "communication_disabled_until", None) or getattr(
            before, "timed_out_until", None
        )
        ato = getattr(after, "communication_disabled_until", None) or getattr(
            after, "timed_out_until", None
        )
        if bto != ato:
            _insert(
                "timeout",
                after.id,
                g,
                {
                    "before": bto.isoformat().replace("+00:00", "Z") if bto else None,
                    "after": ato.isoformat().replace("+00:00", "Z") if ato else None,
                },
            )
        if before.premium_since != after.premium_since:
            _insert(
                "boost",
                after.id,
                g,
                {
                    "before": (
                        before.premium_since.isoformat().replace("+00:00", "Z")
                        if before.premium_since
                        else None
                    ),
                    "after": (
                        after.premium_since.isoformat().replace("+00:00", "Z")
                        if after.premium_since
                        else None
                    ),
                },
            )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.guild:
            _insert("member_join", member.id, member.guild.id, {})

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.guild:
            _insert("member_leave", member.id, member.guild.id, {})

    # -------- invites --------
    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        if invite.guild:
            _insert(
                "invite_create",
                invite.inviter.id if invite.inviter else 0,
                invite.guild.id,
                {
                    "code": invite.code,
                    "channel_id": str(getattr(invite.channel, "id", "")),
                    "uses": invite.uses or 0,
                },
            )

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        if invite.guild:
            _insert("invite_delete", 0, invite.guild.id, {"code": invite.code})

    # -------- threads --------
    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        if thread.guild:
            _insert(
                "thread_create",
                thread.owner_id or 0,
                thread.guild.id,
                {"thread_id": str(thread.id), "parent_id": str(thread.parent_id)},
            )

    @commands.Cog.listener()
    async def on_thread_delete(self, thread: discord.Thread):
        if thread.guild:
            _insert(
                "thread_delete",
                thread.owner_id or 0,
                thread.guild.id,
                {"thread_id": str(thread.id)},
            )

    @commands.Cog.listener()
    async def on_thread_member_join(self, member: discord.ThreadMember):
        if member.thread and member.thread.guild:
            _insert(
                "thread_member_join",
                member.id,
                member.thread.guild.id,
                {"thread_id": str(member.thread.id)},
            )

    @commands.Cog.listener()
    async def on_thread_member_remove(self, member: discord.ThreadMember):
        if member.thread and member.thread.guild:
            _insert(
                "thread_member_remove",
                member.id,
                member.thread.guild.id,
                {"thread_id": str(member.thread.id)},
            )

    # -------- channel/role/webhook/meta --------
    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        if channel.guild:
            _insert(
                "channel_create",
                0,
                channel.guild.id,
                {"channel_id": str(channel.id), "type": channel.__class__.__name__},
            )

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        if channel.guild:
            _insert(
                "channel_delete",
                0,
                channel.guild.id,
                {"channel_id": str(channel.id), "type": channel.__class__.__name__},
            )

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        _insert("role_create", 0, role.guild.id, {"role_id": str(role.id), "name": role.name})

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        _insert("role_delete", 0, role.guild.id, {"role_id": str(role.id), "name": role.name})

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel):
        if channel.guild:
            _insert("webhooks_update", 0, channel.guild.id, {"channel_id": str(channel.id)})

    @commands.Cog.listener()
    async def on_typing(self, channel: discord.abc.Messageable, user: discord.User, when):
        if os.getenv("LOG_TYPING", "0") != "1":
            return
        guild_id = getattr(getattr(channel, "guild", None), "id", 0)
        if not guild_id:
            return
        _insert("typing", user.id, guild_id, {"channel_id": str(getattr(channel, "id", ""))})


async def setup(bot: commands.Bot):
    await bot.add_cog(ActivityLogger(bot))
