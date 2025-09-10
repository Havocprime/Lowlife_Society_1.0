from __future__ import annotations
import os, sys, asyncio, traceback, uuid, datetime as dt
from pathlib import Path
from typing import Any, Optional
import discord

CRASH_DIR = Path(__file__).resolve().parents[2] / "var" / "crash"
CRASH_DIR.mkdir(parents=True, exist_ok=True)

def _now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")

def _write_dump(title: str, body: str) -> str:
    tid = uuid.uuid4().hex[:8]
    path = CRASH_DIR / f"{_now_utc()}_{tid}_{title}.log"
    path.write_text(body, encoding="utf-8", errors="ignore")
    return f"{tid}:{path.name}"

def report_exception(exc: BaseException, *, context: Optional[dict[str, Any]] = None) -> str:
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    ctx = ""
    if context:
        for k, v in context.items():
            ctx += f"{k}: {v}\n"
    return _write_dump("exception", f"[context]\n{ctx}\n[traceback]\n{tb}")

def setup_error_reporting(bot: discord.Client) -> None:
    def excepthook(t, e, tb):
        _write_dump("sys", "".join(traceback.format_exception(t, e, tb)))
        sys.__excepthook__(t, e, tb)
    sys.excepthook = excepthook

    loop = asyncio.get_event_loop()

    def loop_handler(loop, context):
        exc = context.get("exception")
        msg = context.get("message")
        if exc:
            report_exception(exc, context={"loop_message": msg})
        else:
            _write_dump("loop", f"[loop_message]\n{msg}")
    loop.set_exception_handler(loop_handler)

    async def on_app_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
        from src.core.ack import ack_once
        info = {
            "user_id": getattr(interaction.user, "id", None),
            "guild_id": interaction.guild_id,
            "channel_id": interaction.channel_id,
            "command": getattr(getattr(interaction, "command", None), "qualified_name", None),
        }
        trace = report_exception(error, context=info)
        try:
            await ack_once(interaction, ephemeral=True)
            await interaction.followup.send(f"âš ï¸ Something broke. Trace **{trace.split(':')[0]}**", ephemeral=True)
        except Exception:
            pass

    try:
        bot.tree.on_error = on_app_error  # type: ignore[attr-defined]
    except Exception:
        pass

    dsn = os.getenv("SENTRY_DSN", "")
    if dsn:
        try:
            import sentry_sdk  # type: ignore
            sentry_sdk.init(dsn=dsn, traces_sample_rate=0.0)
        except Exception:
            _write_dump("sentry_init", "Failed to init Sentry")
