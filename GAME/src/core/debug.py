# src/core/debug.py
from __future__ import annotations
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import functools
import traceback
import uuid

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "lowlife.log"

_initialized = False

def get_logger(name: str = "lowlife") -> logging.Logger:
    global _initialized
    logger = logging.getLogger(name)
    if _initialized:
        return logger

    logger.setLevel(logging.DEBUG)

    # Console
    c = logging.StreamHandler()
    c.setLevel(logging.INFO)
    c.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s",
                                     datefmt="%H:%M:%S"))

    # Rotating file
    f = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    f.setLevel(logging.DEBUG)
    f.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))

    logger.addHandler(c)
    logger.addHandler(f)
    _initialized = True
    return logger


def slash_try(fn):
    """
    Decorator for slash commands: logs exceptions with a short error id
    and sends an ephemeral error back to the user.
    """
    logger = get_logger("commands")

    @functools.wraps(fn)
    async def wrapper(inter, *args, **kwargs):
        try:
            return await fn(inter, *args, **kwargs)
        except Exception as e:
            err_id = uuid.uuid4().hex[:8]
            # rich context
            gid = getattr(inter, "guild_id", None)
            uid = getattr(inter.user, "id", None)
            logger.error("Command %s failed [%s] (guild=%s user=%s): %s\n%s",
                         fn.__name__, err_id, gid, uid, e, traceback.format_exc())
            try:
                if inter.response.is_done():
                    await inter.followup.send(f"💥 Something went wrong. Error ID **{err_id}**.", ephemeral=True)
                else:
                    await inter.response.send_message(f"💥 Something went wrong. Error ID **{err_id}**.", ephemeral=True)
            except Exception:
                # last resort: swallow
                pass
    return wrapper
