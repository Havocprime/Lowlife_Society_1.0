from __future__ import annotations

import os
import asyncio
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv


def _make_logger():
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    )
    return logging.getLogger("boot")


log = _make_logger()

# <repo root>/GAME/src/bot/bot.py  → parents[3] = repo root
ROOT = Path(__file__).resolve().parents[3]
ENV_PATH = ROOT / ".env"


def build_intents() -> discord.Intents:
    intents = discord.Intents.default()
    intents.message_content = True  # disable later if not needed
    intents.members = True
    return intents


async def main() -> None:
    # Load .env from repo root (fallback to default search if not present)
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH)
    else:
        load_dotenv()

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise SystemExit("DISCORD_TOKEN missing in .env")

    guild_id = os.getenv("DISCORD_GUILD_ID")

    bot = commands.Bot(command_prefix="!", intents=build_intents())
    tree = bot.tree

    # Import command groups safely (skip if a module is absent)
    def _safe_import_register(module_path: str, register_name: str = "register"):
        try:
            mod = __import__(module_path, fromlist=[register_name])
            return getattr(mod, register_name)
        except Exception as e:
            log.warning("Module %s not available (%s) — skipping", module_path, e)
            return None

    reg_players = _safe_import_register("src.bot.commands.players")
    reg_inventory = _safe_import_register("src.bot.inventory_cmds", "register_inventory_commands")
    reg_duel = _safe_import_register("src.bot.duel", "register_duel")
    reg_updates = _safe_import_register("src.bot.updates", "register_updates")

    @bot.event
    async def on_ready():
        log.info("Logged in as %s (%s)", bot.user, getattr(bot.user, "id", "?"))

        for name, reg in [
            ("players", reg_players),
            ("inventory", reg_inventory),
            ("duel", reg_duel),
            ("updates", reg_updates),
        ]:
            if reg:
                try:
                    reg(tree)
                    log.info("registered %s commands", name)
                except Exception as e:
                    log.exception("failed registering %s: %s", name, e)

        # Guild sync (faster while developing)
        if guild_id:
            synced = await tree.sync(guild=discord.Object(id=int(guild_id)))
            log.info("Synced %d commands to guild %s", len(synced), guild_id)
        else:
            synced = await tree.sync()
            log.info("Synced %d commands globally", len(synced))

    await bot.start(token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
