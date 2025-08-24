from __future__ import annotations
import os, asyncio, logging
from pathlib import Path

import discord
from discord import app_commands
from dotenv import load_dotenv

# ---------- logging ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
log = logging.getLogger("boot")

# ---------- find & load .env ----------
def find_env_file(start: Path) -> Path | None:
    # Walk up from this file to repo root and look for ".env"
    for p in [start, *start.parents]:
        cand = p / ".env"
        if cand.exists():
            return cand
    return None

HERE = Path(__file__).resolve()
ENV_FILE = find_env_file(HERE)
if ENV_FILE:
    load_dotenv(ENV_FILE)
    log.info("Loaded .env from: %s", ENV_FILE)
else:
    load_dotenv()  # try current working directory / OS env
    log.info("No .env file found by path-walk; relying on process environment.")

TOKEN = os.getenv("DISCORD_TOKEN", "")
GUILD_ID = os.getenv("DISCORD_GUILD_ID", "")
if not TOKEN:
    log.warning("No DISCORD_TOKEN found in environment (.env). Bot will fail to login.")

GUILD = None
try:
    if GUILD_ID:
        GUILD = discord.Object(id=int(GUILD_ID))
except Exception:
    log.warning("DISCORD_GUILD_ID was not an integer: %r", GUILD_ID)

# ---------- discord client / command tree ----------
intents = discord.Intents.default()
intents.message_content = True  # needed for some dev/testing flows

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# ---------- register commands from submodules ----------
def _safe_register(register_fn, label: str):
    try:
        register_fn(tree)
        log.info("registered %s commands", label)
    except Exception as e:
        log.warning("Module %s not available (%s) — skipping", label, e)

def register_all():
    from src.bot.players import register_players
    from src.bot.inventory_cmds import register_inventory
    # duel + updates are optional; guard with try/except to avoid hard-crash
    try:
        from src.bot.duel import register_duel  # type: ignore
    except Exception as e:
        register_duel = None  # noqa
        log.warning("Module src.bot.duel not available (%s) — skipping", e)
    try:
        from src.bot.updates import register_updates  # type: ignore
    except Exception as e:
        register_updates = None  # noqa
        log.warning("Module src.bot.updates not available (%s) — skipping", e)

    _safe_register(register_players, "players")
    _safe_register(register_inventory, "inventory")
    if 'register_duel' in locals() and callable(register_duel):
        _safe_register(register_duel, "duel")
    if 'register_updates' in locals() and callable(register_updates):
        _safe_register(register_updates, "updates")

@client.event
async def on_ready():
    log.info("Logged in as %s (%s)", client.user, getattr(client.user, "id", "?"))
    # Sync commands
    local = [c.name for c in tree.get_commands()]
    log.info("Local commands: %s", local)
    try:
        if GUILD:
            cmds = await tree.sync(guild=GUILD)
            log.info("Synced %d commands to guild %s", len(cmds), getattr(GUILD, "id", "?"))
        else:
            cmds = await tree.sync()
            log.info("Synced %d commands globally", len(cmds))
    except Exception as e:
        log.warning("Command sync failed: %s", e)

async def main():
    register_all()
    if not TOKEN:
        log.error("Bot crashed: missing/invalid DISCORD_TOKEN.")
        return
    try:
        log.info("logging in using static token")
        await client.start(TOKEN)
    except discord.LoginFailure as e:
        log.error("Bot crashed: %s", e)
    except Exception as e:
        log.exception("Unhandled exception")

if __name__ == "__main__":
    asyncio.run(main())
