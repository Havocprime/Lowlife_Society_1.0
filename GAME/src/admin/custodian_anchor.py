# GAME/src/admin/custodian_anchor.py
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from unicodedata import lookup

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


def _emoji(name: str, default: str) -> str:
    """Return the actual Unicode character by name; fall back to default if unavailable."""
    try:
        return lookup(name)  # e.g., "DNA DOUBLE HELIX" -> 🧬
    except KeyError:
        return default


def _dash() -> str:
    """Em dash with ASCII fallback if HEARTBEAT_ASCII=1."""
    if os.getenv("HEARTBEAT_ASCII", "").strip().lower() in ("1", "true", "yes", "on"):
        return "-"
    try:
        return "\N{EM DASH}"  # —
    except Exception:
        return "-"


def _ellipsis() -> str:
    try:
        return "\N{HORIZONTAL ELLIPSIS}"  # …
    except Exception:
        return "..."


def _demojibake(s: str | None) -> str:
    if not s:
        return ""
    if "â" not in s and "Ã" not in s:
        return s
    try:
        return s.encode("latin1").decode("utf-8")
    except Exception:
        return s


def _last_chain() -> tuple[int | None, str | None]:
    if not DB_PATH.exists():
        return None, None
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT id, chain_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    return (row[0], row[1]) if row else (None, None)


def _status_text() -> str:
    # Icons (with reasonable fallbacks)
    DNA = _emoji("DNA DOUBLE HELIX", "🧬")
    CHECK = "✅"
    CROSS = "❌"
    WARN = "⚠️"

    # best-effort summary; don't import heavy modules
    try:
        from src.core.custodian import ledger as _ledger
        summary = _ledger.verify_chain(limit=5000)
        broken = summary.get("broken_ids", []) or []
        ok = f"OK {CHECK}" if not broken else f"ALERT {CROSS} broken={len(broken)} (e.g., {broken[:5]})"
    except Exception:
        ok = f"status unavailable {WARN}"

    rid, ch = _last_chain()
    DASH = _dash()
    ELL = _ellipsis()

    if rid and ch:
        msg = f"{DNA} Custodian anchor {DASH} last id `{rid}`, hash `{ch[:16]}{ELL}` {DASH} {ok}"
    else:
        msg = f"{DNA} Custodian anchor {DASH} no rows yet {DASH} {ok}"

    return _demojibake(msg)


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
