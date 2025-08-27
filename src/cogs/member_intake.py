from __future__ import annotations

import os
from datetime import datetime, timezone

import discord
from discord.ext import commands

from src.core.db import upsert_player
from src.core.portraits import pick_portrait_for_user
from src.core.risk import compute_risk

WELCOME_CHANNEL_ID = int(os.getenv("WELCOME_CHANNEL_ID", "0"))


def veteran_rank(days: int) -> str:
    return (
        "Legend"
        if days >= 365 * 4
        else (
            "Vanguard"
            if days >= 365 * 2
            else (
                "Regular"
                if days >= 365
                else "Streetwise" if days >= 90 else "Rookie" if days >= 7 else "Fresh Meat"
            )
        )
    )


class MemberIntake(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        now = datetime.now(timezone.utc)

        inv_cog = self.bot.get_cog("InviteTracker")
        invite_code = inviter_id = invite_channel_id = None
        if inv_cog:
            try:
                invite_code, inviter_id, invite_channel_id = await inv_cog.diff_invites(
                    member.guild
                )
            except Exception:
                pass

        created = member.created_at.replace(tzinfo=timezone.utc)
        age_days = (now - created).days
        accent = getattr(member, "accent_color", None)
        accent_val = accent.value if accent else None
        flags = getattr(member, "public_flags", None)
        flags_val = flags.value if flags else 0
        cdu = getattr(member, "communication_disabled_until", None)

        snapshot = {
            "user": {
                "id": str(member.id),
                "name": getattr(member, "name", None),
                "global_name": getattr(member, "global_name", None),
                "bot": bool(member.bot),
                "system": bool(member.system),
                "created_at": created.isoformat().replace("+00:00", "Z"),
                "avatar_url": member.display_avatar.url if member.display_avatar else None,
                "banner_url": None,
                "accent_color": accent_val,
                "public_flags": flags_val,
            },
            "member": {
                "nick": member.nick,
                "joined_at": (member.joined_at or now).isoformat().replace("+00:00", "Z"),
                "pending": bool(getattr(member, "pending", False)),
                "premium_since": (
                    member.premium_since.isoformat().replace("+00:00", "Z")
                    if member.premium_since
                    else None
                ),
                "roles": [
                    {"id": str(r.id), "name": r.name}
                    for r in sorted(member.roles, key=lambda r: r.position)
                ],
                "status": str(getattr(member, "status", "offline")),
                "activities": [
                    getattr(a, "name", str(a)) for a in getattr(member, "activities", [])
                ],
                "voice": {
                    "channel_id": (
                        str(member.voice.channel.id)
                        if member.voice and member.voice.channel
                        else None
                    ),
                    "mute": bool(member.voice.mute) if member.voice else False,
                    "deaf": bool(member.voice.deaf) if member.voice else False,
                    "stream": (
                        bool(getattr(member.voice, "self_stream", False)) if member.voice else False
                    ),
                },
                "communication_disabled_until": (
                    cdu.isoformat().replace("+00:00", "Z") if cdu else None
                ),
                "permissions": [
                    p for p, allowed in dict(member.guild_permissions).items() if allowed
                ],
            },
            "join_context": {
                "invite_code": invite_code,
                "inviter_id": str(inviter_id) if inviter_id else None,
                "invite_channel_id": str(invite_channel_id) if invite_channel_id else None,
            },
            "derived": {},
        }

        snapshot["derived"]["veteran_rank"] = veteran_rank(age_days)
        portrait = pick_portrait_for_user(member.id)
        if portrait:
            snapshot["derived"]["portrait_asset"] = portrait
        risk_score, reasons = compute_risk(snapshot)
        snapshot["derived"]["risk_score"] = risk_score
        snapshot["derived"]["risk_reasons"] = reasons

        upsert_player(snapshot)
        await self.post_mugshot(member, snapshot)

    async def post_mugshot(self, member: discord.Member, snap: dict):
        if not WELCOME_CHANNEL_ID:
            return
        channel = member.guild.get_channel(WELCOME_CHANNEL_ID)
        if not channel or not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return
        portrait = snap["derived"].get("portrait_asset")
        file = discord.File(portrait, filename="mug.png") if portrait else None
        e = discord.Embed(
            title="📸 NEW ARRIVAL — FIRST MUGSHOT",
            description=f"**Alias:** {member.mention}\n**Rank:** {snap['derived'].get('veteran_rank','—')}",
            colour=discord.Color.dark_embed(),
        )
        if member.display_avatar:
            e.set_thumbnail(url=member.display_avatar.url)
        e.add_field(name="Discord ID", value=f"`{member.id}`", inline=True)
        e.add_field(name="Account Created", value=f"`{snap['user']['created_at']}`", inline=True)
        join_str = snap["member"]["joined_at"].replace("T", " ").replace("Z", " UTC")
        e.add_field(name="Booked At", value=f"`{join_str}`", inline=True)
        inv = snap.get("join_context", {})
        inv_line = f"`{inv.get('invite_code') or 'unknown'}`"
        if inv.get("inviter_id"):
            inv_line += f" • by <@{inv['inviter_id']}>"
        e.add_field(name="Referral", value=inv_line, inline=False)
        risk = snap["derived"].get("risk_score", 0)
        reasons = ", ".join(snap["derived"].get("risk_reasons", [])) or "—"
        e.add_field(name="Risk Index", value=f"`{risk}` ({reasons})", inline=False)
        e.set_footer(text="LOWLIFE SOCIETY — Intake Bureau")
        if file:
            e.set_image(url="attachment://mug.png")
            await channel.send(embed=e, file=file)
        else:
            await channel.send(embed=e)


async def setup(bot: commands.Bot):
    await bot.add_cog(MemberIntake(bot))
