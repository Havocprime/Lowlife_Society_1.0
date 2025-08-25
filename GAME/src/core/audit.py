# GAME/src/core/audit.py
from __future__ import annotations
import os, json, uuid, time, functools, inspect
from typing import Any, Optional, Callable, Awaitable, Dict
import aiosqlite
import discord

# DB path: GAME/data/audit.sqlite (override via AUDIT_DB_PATH in .env)
_AUDIT_DB_PATH = os.getenv(
    "AUDIT_DB_PATH",
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "audit.sqlite")
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,
    ts INTEGER NOT NULL,
    guild_id INTEGER,
    channel_id INTEGER,
    user_id INTEGER,
    target_user_id INTEGER,
    action_type TEXT NOT NULL,
    command_name TEXT,
    details TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts);
CREATE INDEX IF NOT EXISTS idx_audit_guild_ts ON audit_log(guild_id, ts);
CREATE INDEX IF NOT EXISTS idx_audit_user_ts ON audit_log(user_id, ts);
CREATE INDEX IF NOT EXISTS idx_audit_action_ts ON audit_log(action_type, ts);
"""

async def ensure_db() -> None:
    os.makedirs(os.path.dirname(_AUDIT_DB_PATH), exist_ok=True)
    async with aiosqlite.connect(_AUDIT_DB_PATH) as db:
        await db.executescript(_SCHEMA)
        await db.commit()

async def log_action(
    *,
    id: Optional[str] = None,
    guild_id: Optional[int],
    channel_id: Optional[int],
    user_id: Optional[int],
    target_user_id: Optional[int] = None,
    action_type: str,
    command_name: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> str:
    trace_id = id or str(uuid.uuid4())
    ts = int(time.time() * 1000)
    payload = json.dumps(details or {}, separators=(",", ":"), ensure_ascii=False)
    async with aiosqlite.connect(_AUDIT_DB_PATH) as db:
        await db.execute(
            "INSERT INTO audit_log (id, ts, guild_id, channel_id, user_id, target_user_id, action_type, command_name, details) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (trace_id, ts, guild_id, channel_id, user_id, target_user_id, action_type, command_name, payload),
        )
        await db.commit()
    return trace_id

def audit_event(
    action_type: str,
    target_user: Optional[Callable[..., Optional[discord.User | discord.Member]]] = None,
    extra: Optional[Callable[..., Dict[str, Any]]] = None,
):
    """
    Decorator for slash commands. Logs each invocation to audit_log.
    """
    def _wrap(func: Callable[..., Awaitable[Any]]):
        @functools.wraps(func)
        async def inner(*args, **kwargs):
            interaction: Optional[discord.Interaction] = None
            for a in args:
                if isinstance(a, discord.Interaction):
                    interaction = a
                    break
            interaction = interaction or kwargs.get("interaction")

            guild_id = interaction.guild_id if interaction else None
            channel_id = interaction.channel_id if interaction else None
            user_id = interaction.user.id if interaction else None
            command_name = interaction.command.qualified_name if (interaction and interaction.command) else None

            tgt = None
            if target_user:
                try:
                    got = target_user(*args, **kwargs)
                    if got is not None:
                        tgt = got.id
                except Exception:
                    tgt = None

            details = {}
            if extra:
                try:
                    details = extra(*args, **kwargs) or {}
                except Exception:
                    details = {}

            trace_id = await log_action(
                guild_id=guild_id, channel_id=channel_id, user_id=user_id,
                target_user_id=tgt, action_type=action_type, command_name=command_name, details=details
            )

            if interaction is not None:
                interaction.extras = getattr(interaction, "extras", {})
                interaction.extras["trace_id"] = trace_id

            return await func(*args, **kwargs)
        return inner
    return _wrap
