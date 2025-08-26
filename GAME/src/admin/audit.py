# GAME/src/admin/audit.py
from __future__ import annotations
import sqlite3, discord
from discord import app_commands
from discord.ext import commands
from src.core.settings import SETTINGS
from src.core.perm import require_role, Role

PAGE = 10

class AuditCmds(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="audit_recent", description="Show recent events.")
    @require_role(Role.MOD)
    async def audit_recent(self, interaction: discord.Interaction, limit: int = 20):
        await interaction.response.defer(ephemeral=True)
        con = sqlite3.connect(SETTINGS.db_path); con.row_factory = sqlite3.Row
        rows = con.execute("""SELECT id,type,subject,created_at FROM events ORDER BY id DESC LIMIT ?""", (min(limit,200),)).fetchall()
        lines = [f"`{r['id']:>6}`  **{r['type']}**  ⟶  {r['subject'] or '-'}  ·  {r['created_at']}" for r in rows]
        txt = "\n".join(lines) or "_No events_"
        await interaction.followup.send(txt[:1900], ephemeral=True)

    @app_commands.command(name="audit_user", description="Events for a Discord user.")
    @require_role(Role.MOD)
    async def audit_user(self, interaction: discord.Interaction, user: discord.Member, limit: int = 20):
        await interaction.response.defer(ephemeral=True)
        con = sqlite3.connect(SETTINGS.db_path); con.row_factory = sqlite3.Row
        rows = con.execute("""SELECT id,type,subject,created_at FROM events
                              WHERE actor_discord_id=? ORDER BY id DESC LIMIT ?""",
                           (str(user.id), min(limit,200))).fetchall()
        lines = [f"`{r['id']:>6}`  **{r['type']}**  ⟶  {r['subject'] or '-'}  ·  {r['created_at']}" for r in rows]
        await interaction.followup.send(("\n".join(lines) or "_No events_")[:1900], ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(AuditCmds(bot))
