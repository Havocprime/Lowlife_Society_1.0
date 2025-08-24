import os, io, json, discord
from discord.ext import commands
from discord import app_commands

ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID", "0"))  # optional; admins always allowed

class AdminInspector(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _is_admin(self, i: discord.Interaction) -> bool:
        if isinstance(i.user, discord.Member) and i.user.guild_permissions.administrator:
            return True
        if ADMIN_ROLE_ID and isinstance(i.user, discord.Member):
            return any(r.id == ADMIN_ROLE_ID for r in i.user.roles)
        return False

    @app_commands.command(name="inspect", description="Admin: dump every possible field for a member")
    @app_commands.describe(user="Target member (defaults to you)")
    async def inspect(self, interaction: discord.Interaction, user: discord.Member | None = None):
        if not self._is_admin(interaction):
            return await interaction.response.send_message("Nope.", ephemeral=True)

        member = user or interaction.user  # type: ignore

        data = {
            "guild_id": str(interaction.guild_id),
            "user": {
                "id": str(member.id),
                "name": getattr(member, "name", None),
                "global_name": getattr(member, "global_name", None),
                "bot": bool(member.bot),
                "system": bool(member.system),
                "created_at": member.created_at.isoformat().replace("+00:00","Z"),
                "avatar_url": member.display_avatar.url if member.display_avatar else None,
                "banner_url": None,  # Fetch on demand if desired
                "accent_color": getattr(member, "accent_color", None).value if getattr(member, "accent_color", None) else None,
                "public_flags": getattr(member, "public_flags", 0).value if getattr(member, "public_flags", None) else 0,
            },
            "member": {
                "nick": member.nick,
                "joined_at": member.joined_at.isoformat().replace("+00:00","Z") if member.joined_at else None,
                "pending": bool(member.pending),
                "premium_since": member.premium_since.isoformat().replace("+00:00","Z") if member.premium_since else None,
                "roles": [{"id": str(r.id), "name": r.name, "position": r.position} for r in sorted(member.roles, key=lambda r: r.position)],
                "status": str(getattr(member, "status", "offline")),
                "activities": [getattr(a, "name", str(a)) for a in getattr(member, "activities", [])],
                "voice": {
                  "channel_id": str(member.voice.channel.id) if member.voice and member.voice.channel else None,
                  "mute": bool(member.voice.mute) if member.voice else False,
                  "deaf": bool(member.voice.deaf) if member.voice else False,
                  "stream": bool(getattr(member.voice, "self_stream", False)) if member.voice else False,
                },
                "communication_disabled_until": member.communication_disabled_until.isoformat().replace("+00:00","Z") if member.communication_disabled_until else None,
                "permissions_true": [p for p, allowed in dict(member.guild_permissions).items() if allowed],
                "permissions_false": [p for p, allowed in dict(member.guild_permissions).items() if not allowed],
            }
        }

        e = discord.Embed(title="🛠️ Admin Inspector", description=f"Full dump for {member.mention}", colour=discord.Color.blurple())
        e.add_field(name="ID", value=f"`{member.id}`", inline=True)
        e.add_field(name="Account Created", value=f"`{data['user']['created_at']}`", inline=True)
        e.add_field(name="Joined Guild", value=f"`{data['member']['joined_at'] or '—'}`", inline=True)
        e.add_field(name="Roles", value=(", ".join(r['name'] for r in data['member']['roles']) or "—")[:1024], inline=False)
        e.add_field(name="Status", value=data["member"]["status"], inline=True)
        e.add_field(name="Activities", value=", ".join(data["member"]["activities"]) or "—", inline=True)
        if data["user"]["avatar_url"]:
            e.set_thumbnail(url=data["user"]["avatar_url"])

        buf = io.BytesIO(json.dumps(data, indent=2).encode("utf-8"))
        file = discord.File(buf, filename=f"inspect_{member.id}.json")
        await interaction.response.send_message(embed=e, file=file, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminInspector(bot))