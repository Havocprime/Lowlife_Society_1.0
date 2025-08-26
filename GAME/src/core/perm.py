from __future__ import annotations
import os, time, functools, typing as t
import discord
from discord.ext import commands

# Optional: allow role IDs via env (comma-sep)
_ADMIN_ROLE_IDS = {int(x) for x in os.getenv("ADMIN_ROLE_IDS", "").split(",") if x.strip().isdigit()}
_MOD_ROLE_IDS   = {int(x) for x in os.getenv("MOD_ROLE_IDS",   "").split(",") if x.strip().isdigit()}

class Role:
    ADMIN = "ADMIN"
    MOD   = "MOD"
    USER  = "USER"

def _has_role(member: discord.Member, role_ids: set[int]) -> bool:
    if not role_ids:
        return False
    mem_ids = {r.id for r in getattr(member, "roles", [])}
    return bool(mem_ids & role_ids)

def user_role(member: discord.Member) -> str:
    # grant ADMIN either by discord permission or configured role ids
    if member.guild_permissions.administrator or _has_role(member, _ADMIN_ROLE_IDS):
        return Role.ADMIN
    if _has_role(member, _MOD_ROLE_IDS):
        return Role.MOD
    return Role.USER

def require_role(min_role: str):
    order = {Role.USER: 0, Role.MOD: 1, Role.ADMIN: 2}
    def deco(func):
        @functools.wraps(func)
        async def wrapper(self, interaction: discord.Interaction, *a, **kw):
            member: discord.Member = t.cast(discord.Member, interaction.user)
            if order[user_role(member)] < order[min_role]:
                await interaction.response.send_message(
                    f"🚫 You need **{min_role}** to use this.", ephemeral=True
                )
                return
            return await func(self, interaction, *a, **kw)
        return wrapper
    return deco

# Simple per-user cool-down for dangerous ops
_COOLDOWNS: dict[tuple[int, str], float] = {}

def dangerous_op_cooldown(key_name: str, seconds: int = 30):
    """Throttle by (user_id, key_name)."""
    def deco(func):
        @functools.wraps(func)
        async def wrapper(self, interaction: discord.Interaction, *a, **kw):
            k = (interaction.user.id, key_name)
            now = time.monotonic()
            last = _COOLDOWNS.get(k, 0.0)
            if now - last < seconds:
                remain = seconds - int(now - last)
                await interaction.response.send_message(
                    f"⏳ Slow down. Try again in **{remain}s**.", ephemeral=True
                )
                return
            _COOLDOWNS[k] = now
            return await func(self, interaction, *a, **kw)
        return wrapper
    return deco
