from __future__ import annotations
import os, time, sqlite3
from collections import deque, defaultdict
from dataclasses import dataclass
from pathlib import Path
import discord
from discord.ext import commands

SPAM_N = int(os.getenv("CUSTODIAN_SPAM_N", "8"))        # messages
SPAM_T = int(os.getenv("CUSTODIAN_SPAM_T", "10"))       # seconds
AUTO_FREEZE = os.getenv("CUSTODIAN_SPAM_AUTOFREEZE", "0") == "1"

DB_PATH = Path(__file__).parents[2] / "db" / "audit.sqlite"

def _ensure_tables():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS admin_flags(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts_utc TEXT NOT NULL,
          subject_id TEXT NOT NULL,
          reason TEXT NOT NULL,
          severity INTEGER NOT NULL,
          opened_by TEXT NOT NULL,
          closed_ts_utc TEXT,
          closed_by TEXT
        );
        CREATE TABLE IF NOT EXISTS account_freeze(
          user_id TEXT PRIMARY KEY,
          ts_utc TEXT NOT NULL,
          reason TEXT NOT NULL,
          by_admin TEXT NOT NULL
        );
        """)
        c.commit()

@dataclass
class Bucket:
    times: deque

class CustodianDetectors(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.win: dict[int, Bucket] = defaultdict(lambda: Bucket(deque()))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # ignore bots / DMs
        if message.author.bot or not isinstance(message.channel, discord.TextChannel):
            return
        now = time.time()
        b = self.win[message.author.id].times
        b.append(now)
        # trim window
        while b and (now - b[0] > SPAM_T):
            b.popleft()

        if len(b) >= SPAM_N:
            # Flag once per window; clear to avoid repeated triggers
            self.win[message.author.id].times.clear()
            _ensure_tables()
            try:
                import datetime
                with sqlite3.connect(DB_PATH) as c:
                    c.execute(
                        "INSERT INTO admin_flags(ts_utc, subject_id, reason, severity, opened_by) VALUES (?,?,?,?,?)",
                        (datetime.datetime.utcnow().isoformat(timespec="seconds"),
                         str(message.author.id),
                         f"spam burst: {SPAM_N} msgs/{SPAM_T}s in #{message.channel.name}",
                         3,
                         "custodian.detector")
                    )
                    if AUTO_FREEZE:
                        c.execute(
                            "INSERT OR REPLACE INTO account_freeze(user_id, ts_utc, reason, by_admin) VALUES (?,?,?,?)",
                            (str(message.author.id),
                             datetime.datetime.utcnow().isoformat(timespec="seconds"),
                             "auto-freeze: spam burst", "custodian.detector")
                        )
                    c.commit()
            except Exception:
                pass
            # ping mods quietly (best-effort)
            try:
                await message.channel.send(
                    f"⚠️ Custodian: flagged <@{message.author.id}> for spam burst "
                    f"({SPAM_N}/{SPAM_T}s).{' Auto-frozen.' if AUTO_FREEZE else ''}",
                    delete_after=10
                )
            except Exception:
                pass

async def setup(bot: commands.Bot):
    await bot.add_cog(CustodianDetectors(bot))
