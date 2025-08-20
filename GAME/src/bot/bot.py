# FILE: src/bot/bot.py
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import os
import json
import logging
import asyncio

import discord
from discord import app_commands
from discord.ext import commands

from dotenv import load_dotenv

# ---------- env ----------
load_dotenv(override=True)  # must run before creating the bot

# ---------- logging setup ----------
def setup_logging() -> logging.Logger:
    logs_dir = Path(__file__).resolve().parents[2] / "logs"  # GAME/logs
    logs_dir.mkdir(parents=True, exist_ok=True)
    logfile = logs_dir / "lowlife.log"

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Avoid duplicate handlers when reloading
    if not any(isinstance(h, logging.FileHandler) for h in root.handlers):
        fh = logging.FileHandler(logfile, encoding="utf-8")
        ch = logging.StreamHandler()

        fmt = logging.Formatter(
            "[%(asctime)s] [%(levelname)7s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        fh.setFormatter(fmt)
        ch.setFormatter(fmt)

        root.addHandler(fh)
        root.addHandler(ch)

    # quiet some noisy loggers
    logging.getLogger("discord.ext.commands.bot").setLevel(logging.WARNING)
    logging.getLogger("updates").setLevel(logging.INFO)
    return logging.getLogger("boot")


log = setup_logging()

# ---------- stylish boot banner ----------
# Big, elegant block-letter logo (Unicode safe in modern terminals)
BANNER_LINES = [
    
"          ",
"           ",
"           ██╗           ██████╗         ██╗    ██╗ ",
"            ██║           ██╔═══██╗       ██║    ██║  ",
"            ██║           ██║   ██║       ██║ █╗ ██║ ",
"            ██║           ██║   ██║       ██║███╗██║ ",
"            ███████╗       ╚██████╔╝      ╚███╔███╔╝",
"            ╚═════╝         ╚════╝         ╚══╝╚═╝",
" ",
"                L    O    W    L    I    F    E",
" ",
"             ██╗         ██═╗    ██████═╗    ██████╗",
"            ██║         ██ ║    ██ ╔═══╝    ██╔═══╝",
"            ██║         ██ ║    ████═╗      █████╗  ",
"            ██║         ██ ║    ██ ╔═╝      ██╔══╝  ",
"             ███████╗    ██ ║    ██ ║        ██████╗",
"             ╚═══════╝    ╚═══╝  ╚═══╝     ╚═════╝",

]

# 256-color gold→silver palette (classy, minimal)
PALETTE_256 = [220, 214, 187, 250]  # gold → khaki → light grey → silver
DIM, RESET = "\x1b[90m", "\x1b[0m"

def _ansi256(code: int) -> str:
    return f"\x1b[38;5;{code}m"

def _gradient_color(index: int, total: int) -> str:
    bucket = int((index / max(total - 1, 1)) * (len(PALETTE_256) - 1))
    return _ansi256(PALETTE_256[bucket])

def print_boot_banner(info: dict[str, str]) -> None:
    total = len(BANNER_LINES)
    for i, line in enumerate(BANNER_LINES):
        print(_gradient_color(i, total) + line + RESET)
    for k, v in info.items():
        print(f"{DIM}{k:<12}{RESET}: {v}")
    print()

# ---------- core imports ----------
from src.core import emotes as EM
from src.core.rules import load_rules, load_templates
from src.core.embeds import build_combat_embed

# commands / groups
from src.bot.commands.players import register as register_players
from src.bot.inventory_cmds import register_inventory_commands
from .duel import register_duel
from .updates import register_updates, maybe_start_updates_watcher
from src.bot.embed_demo import register_embed_demo

# ---------- bot wiring ----------
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise SystemExit("Missing DISCORD_TOKEN in environment")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

DATA_DIR = Path("data")
DB_COMBATS = DATA_DIR / "combats.json"

# Register groups that don’t depend on templates (safe pre-sync)
register_duel(tree)
register_updates(tree)
register_embed_demo(tree)

# ---------- errors ----------
@tree.error
async def on_app_command_error(inter: discord.Interaction, error: app_commands.AppCommandError):
    log.error(
        "App command error (guild=%s user=%s cmd=%s): %s",
        inter.guild_id,
        getattr(inter.user, "id", None),
        getattr(inter.command, "name", "?"),
        error,
        exc_info=True,
    )
    try:
        msg = "💥 Command failed. Check logs for details."
        if inter.response.is_done():
            await inter.followup.send(msg, ephemeral=True)
        else:
            await inter.response.send_message(msg, ephemeral=True)
    except Exception:
        pass

# ---------- ready ----------
@bot.event
async def on_ready():
    # set tileset once
    try:
        EM.set_active_tileset("custom_default")  # change to "unicode" if you want the fallback set
    except Exception as e:
        log.warning("Tileset set failed: %s", e)

    # Register things that need templates
    try:
        templates = load_templates()
        register_players(tree, templates)
        register_inventory_commands(tree, bot)
    except Exception as e:
        log.error("Template/command registration failed: %s", e, exc_info=True)

    # Sync
    try:
        dev_gid = os.getenv("DEV_GUILD_ID") or os.getenv("GUILD_ID")
        if dev_gid:
            g = discord.Object(id=int(dev_gid))
            tree.copy_global_to(guild=g)
            cmds = await tree.sync(guild=g)
            log.info("Synced commands to guild %s -> %s", dev_gid, [c.name for c in cmds])
        else:
            cmds = await tree.sync()
            log.info("Synced commands globally -> %s", [c.name for c in cmds])
    except Exception as e:
        log.error("Slash command sync error: %s", e, exc_info=True)

    # Updates watcher (guarded)
    try:
        if not getattr(bot, "_lowlife_updates_watch_started", False):
            _watcher = maybe_start_updates_watcher(bot)
            bot._lowlife_updates_watch_started = True if _watcher else False
    except Exception:
        pass

    # Banner + log lines
    boot_info = {
        "User":     f"{bot.user} (ID: {bot.user.id})",
        "Guilds":   str(len(bot.guilds)),
        "Commands": str(len([*tree.get_commands()])),
        "Tileset":  EM.get_active_tileset(),
        "Started":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Python":   f"{os.sys.version_info.major}.{os.sys.version_info.minor}",
    }
    print_boot_banner(boot_info)
    log.info("Logged in as %s (ID: %s)", bot.user, bot.user.id)
    log.info("Guilds: %d | Commands: %d", len(bot.guilds), len([*tree.get_commands()]))
    log.info("Active tileset: %s", EM.get_active_tileset())

# ---------- utility / debug ----------
@tree.command(name="sync", description="Force re-sync of slash commands.")
async def sync_cmd(inter: discord.Interaction):
    await inter.response.defer(ephemeral=True)
    dev_gid = os.getenv("DEV_GUILD_ID") or os.getenv("GUILD_ID")
    try:
        if dev_gid:
            g = discord.Object(id=int(dev_gid))
            tree.copy_global_to(guild=g)
            cmds = await tree.sync(guild=g)
            msg = f"🔄 Synced to guild {dev_gid}: " + ", ".join(c.name for c in cmds)
        else:
            cmds = await tree.sync()
            msg = "🔄 Synced globally: " + ", ".join(c.name for c in cmds)
        await inter.followup.send(msg, ephemeral=True)
    except Exception as e:
        await inter.followup.send(f"❌ Sync failed: {e}", ephemeral=True)

@tree.command(name="cmds", description="List loaded slash commands.")
async def list_cmds(inter: discord.Interaction):
    names = [c.name for c in tree.get_commands()]
    await inter.response.send_message("📜 " + ", ".join(names), ephemeral=True)

@tree.command(name="debug_state", description="Show raw duel JSON state for this server.")
async def debug_state(inter: discord.Interaction):
    k = str(inter.guild_id or 0)
    if DB_COMBATS.exists():
        try:
            db = json.loads(DB_COMBATS.read_text(encoding="utf-8"))
        except Exception as e:
            await inter.response.send_message(f"Could not read combats.json: {e}", ephemeral=True)
            return
        payload = json.dumps(db.get(k, {}), indent=2)
        await inter.response.send_message(f"```json\n{payload}\n```", ephemeral=True)
    else:
        await inter.response.send_message("No combats.json present.", ephemeral=True)

@tree.command(name="ping", description="Check if the Lowlife bot is alive")
async def ping(inter: discord.Interaction):
    await inter.response.send_message("pong 🫡")

@tree.command(name="mock_round", description="Render a full combat round using rules & templates")
async def mock_round(interaction: discord.Interaction):
    _ = load_rules()  # verifies YAML exists
    tpl = load_templates()["combat_log"]
    attacker, defender = "ChromeJack", "Bricks"
    before, after = "Mid", "Near"
    round_summary = (
        "**Round 2**\n"
        f"• {attacker} fires *9mm Pistol* at **{before}** — **HIT** (82%) → **8 dmg** to {defender}\n"
        f"• Status applied: **Bleed (2 turns)** on {defender}\n"
        f"• {defender} (AI) not in melee range → **Advance** to **{after}**\n"
        f"• End: Bleed tick deals **2** more to {defender}; Range is now **{after}**"
    )
    statuses = f"{defender}: Bleed (2t) • Range: {before}→{after}\n{attacker}: —"
    payload = build_combat_embed(
        tpl, attacker=attacker, defender=defender, range_state=before,
        round_summary=round_summary, hp_a=(50, 50), hp_b=(40, 50), statuses=statuses,
    )
    embed = discord.Embed(title=payload["title"], description=payload["description"])
    for fld in payload["fields"]:
        embed.add_field(name=fld["name"], value=fld["value"], inline=fld["inline"])
    await interaction.response.send_message(embed=embed)

# ---------- run ----------
if __name__ == "__main__":
    bot.run(TOKEN)
