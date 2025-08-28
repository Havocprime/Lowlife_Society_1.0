from __future__ import annotations
import discord
from discord import app_commands
from discord.ext import commands
from src.core.perm import require_role, Role
from src.core.config import set_role_ids, get_role_ids

class RoleAdmin(commands.Cog):
    def __init__(self, bot: commands.Bot): self.bot = bot

    @app_commands.command(name="set_admin_role", description="ADMIN: set admin role (replaces list).")
    @require_role(Role.ADMIN)
    async def set_admin_role(self, interaction: discord.Interaction, role: discord.Role):
        set_role_ids("admin_role_ids", {role.id})
        await interaction.response.send_message(f"✅ Admin role set to **{role.name}**.", ephemeral=True)

    @app_commands.command(name="set_mod_role", description="ADMIN: set moderator role (replaces list).")
    @require_role(Role.ADMIN)
    async def set_mod_role(self, interaction: discord.Interaction, role: discord.Role):
        set_role_ids("mod_role_ids", {role.id})
        await interaction.response.send_message(f"✅ Mod role set to **{role.name}**.", ephemeral=True)

    @app_commands.command(name="show_roles", description="Show configured admin/mod role IDs.")
    @require_role(Role.ADMIN)
    async def show_roles(self, interaction: discord.Interaction):
        a = ", ".join(str(x) for x in sorted(get_role_ids("admin_role_ids"))) or "_none_"
        m = ", ".join(str(x) for x in sorted(get_role_ids("mod_role_ids"))) or "_none_"
        await interaction.response.send_message(f"Admin IDs: {a}\nMod IDs: {m}", ephemeral=True)

async def setup(bot: commands.Bot): await bot.add_cog(RoleAdmin(bot))
