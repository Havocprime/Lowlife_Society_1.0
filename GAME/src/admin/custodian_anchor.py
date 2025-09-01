# GAME/src/admin/custodian_anchor.py
from __future__ import annotations
import os
import sqlite3
from pathlib import Path
import discord
from discord.ext import commands, tasks

# Try to reuse ledger DB path if available
try:
    from src.core.custodian import ledger
    DB_PATH = Path(getattr(ledger, "DB_PATH", Path(__file__).parents[2] / "db" / "audit.sqlite"))
except Exception:
    DB_PATH = Path(__file__).parents[2] / "db" / "audit.sqlite"

ANCHOR_CHANNEL_ID = int(os.getenv("CUSTODIAN_ANCHOR_CHANNEL_ID", "0") or "0")

# Post without pinging anyone
ALLOWED_NONE = discord.AllowedMentions.none()

def _last_chain() -> tuple[int | None, str | None]:
    if not DB_PATH.exists():
        return None, None
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT id, chain_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    return (row[0], row[1]) if row else (None, None)

def _status_text() -> str:
    # best-effort summary; don't import heavy modules
    try:
        from src.core.custodian import ledger as _ledger
        summary = _ledger.verify_chain(limit=5000)
        broken = summary.get("broken_ids", [])
        ok = "OK ✅" if not broken else f"ALERT ❌ broken={len(broken)} (e.g., {broken[:5]})"
    except Exception:
        ok = "status unavailable ⚠️"
        broken = []
    rid, ch = _last_chain()
    if rid and ch:
        return f"⛓️ Custodian anchor — last id `{rid}`, hash `{ch[:16]}…` — {ok}"
    return f"⛓️ Custodian anchor — no rows yet — {ok}"

class CustodianAnchor(commands.Cog):
    """Posts a periodic tamper-evident anchor of the audit chain to a private channel."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.anchor_task.start()

    def cog_unload(self):
        self.anchor_task.cancel()

    # Change minutes=60 for production; set to 1 temporarily to test
    @tasks.loop(minutes=60)
    async def anchor_task(self):
        if not ANCHOR_CHANNEL_ID:
            return
        ch = self.bot.get_channel(ANCHOR_CHANNEL_ID)
        if not isinstance(ch, (discord.TextChannel, discord.Thread)):
            return
        try:
            await ch.send(_status_text(), silent=True, allowed_mentions=ALLOWED_NONE)
        except Exception:
            pass

    @anchor_task.before_loop
    async def before_anchor_task(self):
        await self.bot.wait_until_ready()

    # Manual trigger so you can test instantly
    @discord.app_commands.command(name="anchor_now", description="Post the current audit chain anchor now.")
    async def anchor_now(self, interaction: discord.Interaction):
        if not ANCHOR_CHANNEL_ID:
            await interaction.response.send_message("Set CUSTODIAN_ANCHOR_CHANNEL_ID first.", ephemeral=True)
            return
        ch = interaction.client.get_channel(ANCHOR_CHANNEL_ID)  # type: ignore
        if not isinstance(ch, (discord.TextChannel, discord.Thread)):
            await interaction.response.send_message("Anchor channel not found or not a text channel.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            msg = _status_text()
            await ch.send(msg, silent=True, allowed_mentions=ALLOWED_NONE)
            await interaction.followup.send("Anchor posted ✅", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Failed to post anchor: `{type(e).__name__}: {e}`", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(CustodianAnchor(bot))
