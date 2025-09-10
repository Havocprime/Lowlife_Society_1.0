# GAME/src/admin/freeze.py
from __future__ import annotations
import sqlite3
from pathlib import Path
import discord
from discord import app_commands
from discord.ext import commands

# Reuse custodian DB path if available
try:
    from src.core.custodian import ledger
    DB_PATH = Path(getattr(ledger, "DB_PATH"))
except Exception:
    DB_PATH = Path(__file__).parents[2] / "db" / "audit.sqlite"

ALLOWED_WHEN_FROZEN = {"unfreeze_user", "freeze_status"}  # <-- allow recovery

def _is_frozen(user_id: int) -> tuple[bool, str | None]:
    try:
        with sqlite3.connect(DB_PATH) as con:
            row = con.execute(
                "SELECT reason FROM account_freeze WHERE user_id=?",
                (str(user_id),)
            ).fetchone()
        return (row is not None, (row[0] if row else None))
    except Exception:
        return (False, None)

async def _freeze_gate(interaction: discord.Interaction) -> bool:
    # Whitelist certain commands so you can always recover
    name = getattr(getattr(interaction, "command", None), "qualified_name", "") or ""
    if name in ALLOWED_WHEN_FROZEN:
        return True

    uid = getattr(getattr(interaction, "user", None), "id", None)
    if not uid:
        return True

    frozen, reason = _is_frozen(int(uid))
    if frozen:
        # Quietly block
        try:
            await interaction.response.send_message(
                f"ðŸš« Your account is temporarily frozen: {reason or 'policy hold'}",
                ephemeral=True,
            )
        except discord.InteractionResponded:
            pass
        return False
    return True

class FreezeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Set a global app-command interaction check
        bot.tree.interaction_check = _freeze_gate

async def setup(bot: commands.Bot):
    await bot.add_cog(FreezeCog(bot))
