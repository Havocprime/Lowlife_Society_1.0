# GAME/src/core/audit.py
from __future__ import annotations

import functools
import json
import os
import time
import uuid
from typing import Any, Awaitable, Callable, Dict, Optional

import aiosqlite
import discord

# --- Storage: GAME/data/audit.sqlite (override via AUDIT_DB_PATH) ---
_AUDIT_DB_PATH = os.getenv(
    "AUDIT_DB_PATH",
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "audit.sqlite"),
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
CREATE INDEX IF NOT EXISTS idx_audit_ts        ON audit_log(ts);
CREATE INDEX IF NOT EXISTS idx_audit_guild_ts  ON audit_log(guild_id, ts);
CREATE INDEX IF NOT EXISTS idx_audit_user_ts   ON audit_log(user_id, ts);
CREATE INDEX IF NOT EXISTS idx_audit_action_ts ON audit_log(action_type, ts);
"""

_DB_READY = False


async def ensure_db() -> None:
    """Initialize the audit DB schema if needed."""
    os.makedirs(os.path.dirname(_AUDIT_DB_PATH), exist_ok=True)
    async with aiosqlite.connect(_AUDIT_DB_PATH) as db:
        await db.executescript(_SCHEMA)
        await db.commit()


async def _ensure_db_once() -> None:
    global _DB_READY
    if not _DB_READY:
        await ensure_db()
        _DB_READY = True


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
    """Append an audit row."""
    await _ensure_db_once()
    trace_id = id or str(uuid.uuid4())
    ts = int(time.time() * 1000)
    payload = json.dumps(details or {}, separators=(",", ":"), ensure_ascii=False)
    async with aiosqlite.connect(_AUDIT_DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO audit_log
                (id, ts, guild_id, channel_id, user_id, target_user_id, action_type, command_name, details)
            VALUES (?,  ?,  ?,        ?,         ?,       ?,              ?,           ?,            ?)
            """,
            (
                trace_id,
                ts,
                guild_id,
                channel_id,
                user_id,
                target_user_id,
                action_type,
                command_name,
                payload,
            ),
        )
        await db.commit()
    return trace_id


def audit_event(
    action_type: str,
    target_user: Optional[Callable[..., Optional[discord.User | discord.Member]]] = None,
    extra: Optional[Callable[..., Dict[str, Any]]] = None,
    *,
    ack: bool = False,  # set True only if you want the decorator to ack early
    skip_commands: tuple[str, ...] = ("sync",),  # never touch /sync's token
):
    """
    Decorator for slash commands.
    - Does NOT perform any I/O before the handler runs (prevents 'Unknown interaction').
    - Optionally acknowledges once up-front (ack=True) using ack_once, except for commands in skip_commands.
    - Always logs after the handler finishes (success or error), including status & error info.
    """

    def _wrap(func: Callable[..., Awaitable[Any]]):
        @functools.wraps(func)
        async def inner(*args, **kwargs):
            # Extract interaction from args/kwargs
            interaction: Optional[discord.Interaction] = None
            for a in args:
                if isinstance(a, discord.Interaction):
                    interaction = a
                    break
            if interaction is None:
                interaction = kwargs.get("interaction")

            # Snapshot lightweight context (no I/O)
            guild_id = interaction.guild_id if interaction else None
            channel_id = interaction.channel_id if interaction else None
            user_id = interaction.user.id if interaction else None
            cmd_name = (
                (interaction.command and interaction.command.qualified_name)
                if interaction
                else None
            )

            # Resolve target user (pure Python)
            tgt_id: Optional[int] = None
            if target_user:
                try:
                    got = target_user(*args, **kwargs)
                    if got is not None:
                        tgt_id = got.id
                except Exception:
                    tgt_id = None

            # Extra fields (pure Python)
            extra_details: Dict[str, Any] = {}
            if extra:
                try:
                    extra_details = extra(*args, **kwargs) or {}
                except Exception:
                    extra_details = {}

            # Optional safe ack (never for /sync to avoid token races)
            if ack and interaction is not None and (cmd_name or "") not in skip_commands:
                try:
                    from src.core.ack import ack_once  # local import to avoid cycles

                    await ack_once(interaction, ephemeral=True)
                except Exception:
                    # ack is best-effort; never fail the command because of the decorator
                    pass

            # Generate a trace id and stick it on the interaction for downstream use
            trace_id = str(uuid.uuid4())
            if interaction is not None:
                interaction.extras = getattr(interaction, "extras", {})
                interaction.extras["trace_id"] = trace_id

            # Run the command, then log outcome
            status = "ok"
            err_txt = None
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                status = "error"
                err_txt = f"{type(e).__name__}: {e}"
                raise
            finally:
                # Log asynchronously after the handler, so we don't delay the initial ack
                try:
                    details = dict(extra_details)
                    details["status"] = status
                    if err_txt:
                        details["error"] = err_txt
                    await log_action(
                        id=trace_id,
                        guild_id=guild_id,
                        channel_id=channel_id,
                        user_id=user_id,
                        target_user_id=tgt_id,
                        action_type=action_type,
                        command_name=cmd_name,
                        details=details,
                    )
                except Exception:
                    # Never let audit logging crash the command
                    pass

        return inner

    return _wrap
