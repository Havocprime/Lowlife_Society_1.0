# FILE: src/bot/updates.py
from __future__ import annotations

import os
import re
import json
import time
import hashlib
import logging
import asyncio
from pathlib import Path
from typing import Optional, Tuple, List

import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger("updates")

# -----------------------
# Env helpers
# -----------------------
def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(int(default))).strip().lower() in {"1", "true", "yes", "y"}

def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default

# -----------------------
# Paths & state
# -----------------------
STATE_FILE = ".updates_state.json"

def _repo_root() -> Path:
    p = Path(__file__).resolve()
    return p.parents[2] if len(p.parents) >= 2 else p.parent

def _state_path() -> Path:
    return _repo_root() / STATE_FILE

def _load_state() -> dict:
    try:
        fp = _state_path()
        if fp.exists():
            return json.loads(fp.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        pass
    return {}

def _save_state(data: dict) -> None:
    try:
        _state_path().write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass

# -----------------------
# Changelog discovery / parsing
# -----------------------
def _norm_path(p: str, base: Path) -> Path:
    q = p.replace("\\", "/").strip()
    path = Path(q)
    if not path.is_absolute():
        path = (base.parent / q)
    return path.expanduser().resolve()

def find_changelog_file() -> Optional[Path]:
    env_path = os.getenv("CHANGELOG_PATH")
    if env_path:
        p = _norm_path(env_path, Path(__file__).resolve())
        if p.exists():
            log.info(f"[updates] Using CHANGELOG from env: {p}")
            return p
        log.warning(f"[updates] CHANGELOG_PATH set but file not found: {p}")

    here = Path(__file__).resolve()
    candidates: list[Path] = []
    for parent in [here.parent, *here.parents[:4]]:
        candidates.extend([
            parent / "CHANGELOG.md",
            parent / "changelog.md",
            parent / "CHANGELOG.txt",
            parent / "docs" / "CHANGELOG.md",
            parent / "docs" / "changelog.md",
            parent / "tools" / "CHANGELOG.md",
            parent / "tools" / "changelog.md",
        ])
    for c in candidates:
        try:
            if c.exists():
                log.info(f"[updates] Found CHANGELOG at: {c}")
                return c
        except Exception:
            pass
    log.error("[updates] No CHANGELOG file found via discovery.")
    return None

_SECTION_RE = re.compile(r"^\s{0,3}##\s+(.*)$", re.MULTILINE)
_IMG_RE = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<path>[^)]+)\)")

def parse_latest_changelog_section(text: str) -> Tuple[str, str]:
    sections = list(_SECTION_RE.finditer(text))
    if not sections:
        return "Latest Changes", text.strip()
    first = sections[0]
    heading = first.group(1).strip()
    start = first.end()
    end = sections[1].start() if len(sections) > 1 else len(text)
    body = text[start:end].strip()
    return heading, body

def read_changelog() -> Optional[Tuple[str, str, Path]]:
    p = find_changelog_file()
    if not p:
        return None
    try:
        raw = p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        log.exception(f"[updates] Failed reading CHANGELOG: {p} :: {e}")
        return None
    heading, body = parse_latest_changelog_section(raw)
    if not body:
        log.warning(f"[updates] CHANGELOG parsed but body empty from: {p}")
        return None
    return heading, body, p

# -----------------------
# Media extraction (Seal/Thumbnail + Footer/Image)
# -----------------------
class Media:
    def __init__(self, body_md: str, files: List[discord.File], seal_url: Optional[str], footer_url: Optional[str]):
        self.body_md = body_md
        self.files = files
        self.seal_url = seal_url
        self.footer_url = footer_url

def _extract_media(body_md: str, changelog_path: Path) -> Media:
    """
    Parse Markdown image tags from the section body.
    - If alt contains 'seal' => set as thumbnail (top-right)
    - If alt contains 'footer' => set as bottom image
    - If neither, use first as footer by default
    Also supports env overrides: UPDATES_SEAL_PATH, UPDATES_FOOTER_PATH
    """
    seal_file: Optional[Path] = None
    footer_file: Optional[Path] = None

    def replacer(m: re.Match) -> str:
        nonlocal seal_file, footer_file
        alt = (m.group("alt") or "").strip().lower()
        p = _norm_path(m.group("path"), changelog_path)
        # SAFETY: only accept real files
        if (not p.exists()) or (not p.is_file()):
            log.warning(f"[updates] Skipping media path (not a file): {p}")
            return m.group(0)
        if "seal" in alt and seal_file is None:
            seal_file = p
            return ""  # strip the tag from description
        if "footer" in alt and footer_file is None:
            footer_file = p
            return ""
        # default: first non-tag image becomes footer if none set
        if footer_file is None:
            footer_file = p
            return ""
        return ""  # strip additional images from description

    cleaned = _IMG_RE.sub(replacer, body_md).strip()

    # Env fallbacks (SAFETY: guard against directories)
    if seal_file is None and os.getenv("UPDATES_SEAL_PATH"):
        p = _norm_path(os.getenv("UPDATES_SEAL_PATH", ""), changelog_path)
        if p.exists() and p.is_file():
            seal_file = p
        else:
            log.warning(f"[updates] UPDATES_SEAL_PATH not a file: {p}")
    if footer_file is None and os.getenv("UPDATES_FOOTER_PATH"):
        p = _norm_path(os.getenv("UPDATES_FOOTER_PATH", ""), changelog_path)
        if p.exists() and p.is_file():
            footer_file = p
        else:
            log.warning(f"[updates] UPDATES_FOOTER_PATH not a file: {p}")

    files: List[discord.File] = []
    seal_url = footer_url = None
    if seal_file and seal_file.exists() and seal_file.is_file():
        files.append(discord.File(str(seal_file), filename="seal.png"))
        seal_url = "attachment://seal.png"
    if footer_file and footer_file.exists() and footer_file.is_file():
        files.append(discord.File(str(footer_file), filename="footer.png"))
        footer_url = "attachment://footer.png"

    return Media(cleaned, files, seal_url, footer_url)

# -----------------------
# Embeds
# -----------------------
def build_updates_embed(heading: str, body_md: str, seal_url: Optional[str] = None, footer_url: Optional[str] = None) -> discord.Embed:
    em = discord.Embed(title=f"Lowlife — {heading}", description=body_md, color=0x00FF88)
    if seal_url:
        em.set_thumbnail(url=seal_url)   # top-right
    if footer_url:
        em.set_image(url=footer_url)     # bottom full-width
    em.set_footer(text="Source: CHANGELOG.md")
    return em

# -----------------------
# Cog (commands)
# -----------------------
class Updates(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="updates", description="Post the latest changes from the changelog.")
    async def updates(self, interaction: discord.Interaction):
        parsed = read_changelog()
        if not parsed:
            await interaction.response.send_message(
                "I couldn't find any changelog entries. Double-check the file path or format (## section headings).",
                ephemeral=True
            )
            return
        heading, body, path = parsed
        media = _extract_media(body, path)
        em = build_updates_embed(heading, media.body_md, media.seal_url, media.footer_url)
        # Send with attachments (if any)
        await interaction.response.send_message(embed=em, files=media.files)

    @app_commands.command(name="updates_test", description="Diagnostics for the updates watcher (ephemeral).")
    async def updates_test(self, interaction: discord.Interaction):
        watcher_enabled = _env_bool("UPDATES_WATCHER", False)
        poll = _env_int("UPDATES_POLL_SEC", 5)
        chan_env = os.getenv("UPDATES_CHANNEL_ID", "")
        state = _load_state()
        chan_state = state.get("channel_id", "")

        parsed = read_changelog()
        if parsed:
            heading, body, path = parsed
            media = _extract_media(body, path)
            preview = (media.body_md[:200] + "…") if len(media.body_md) > 200 else media.body_md
            seal_status = "found" if media.seal_url else "none"
            footer_status = "found" if media.footer_url else "none"
            path_str = str(path)
        else:
            heading, preview, path_str = "(none)", "(n/a)", "(not found)"
            seal_status = footer_status = "n/a"

        msg = (
            f"**Watcher enabled:** {watcher_enabled}\n"
            f"**Channel ID (env):** {chan_env or '(not set)'}\n"
            f"**Channel ID (state):** {chan_state or '(not set)'}\n"
            f"**Poll interval:** {poll}s\n"
            f"**Changelog path:** `{path_str}`\n"
            f"**Top heading:** {heading}\n"
            f"**Preview:** {preview}\n"
            f"**Media:** seal={seal_status}, footer={footer_status}\n"
            f"**State file:** `{_state_path()}`\n"
            f"**Last hash:** `{state.get('last_body_hash','')}`\n"
            f"**Last heading:** {state.get('last_heading','')}\n"
            f"**Last posted_at:** {state.get('posted_at','')}\n"
        )
        await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(name="updates_set_here", description="Set the auto-post channel to this channel (persists in state).")
    async def updates_set_here(self, interaction: discord.Interaction):
        state = _load_state()
        state["channel_id"] = interaction.channel_id
        _save_state(state)
        await interaction.response.send_message(
            f"Auto-post channel set to this channel (ID: `{interaction.channel_id}`).", ephemeral=True
        )

# -----------------------
# Registration at the right time
# -----------------------
def _install_setup_hook(bot: commands.Bot):
    original_setup_hook = getattr(bot, "setup_hook", None)

    async def setup_hook():
        if callable(original_setup_hook):
            res = original_setup_hook()
            if asyncio.iscoroutine(res):
                await res
        await bot.add_cog(Updates(bot))
        if _env_bool("UPDATES_WATCHER", False):
            _schedule_watcher(bot)
        log.info("[updates] setup_hook complete (cog + watcher).")

    bot.setup_hook = setup_hook  # type: ignore[attr-defined]
    log.info("[updates] Cog registration scheduled via setup_hook.")

def register(tree: app_commands.CommandTree | commands.Bot):
    if isinstance(tree, commands.Bot):
        _install_setup_hook(tree)
        return
    bot = getattr(tree, "client", None)
    if isinstance(bot, commands.Bot):
        _install_setup_hook(bot)
        return

    @tree.command(name="updates", description="Post the latest changes from the changelog.")
    async def _updates_cmd(interaction: discord.Interaction):
        parsed = read_changelog()
        if not parsed:
            await interaction.response.send_message(
                "I couldn't find any changelog entries. Double-check the file path or format (## section headings).",
                ephemeral=True
            )
            return
        heading, body, path = parsed
        media = _extract_media(body, path)
        em = build_updates_embed(heading, media.body_md, media.seal_url, media.footer_url)
        await interaction.response.send_message(embed=em, files=media.files)

# -----------------------
# Watcher (polling, robust channel resolution)
# -----------------------
def _resolve_channel_id() -> Optional[int]:
    chan_env = os.getenv("UPDATES_CHANNEL_ID")
    if chan_env:
        try:
            return int(chan_env)
        except Exception:
            log.warning(f"[updates] UPDATES_CHANNEL_ID invalid: {chan_env!r}")
    chan_state = _load_state().get("channel_id")
    if isinstance(chan_state, int):
        return chan_state
    return None

async def _watch_loop(bot: commands.Bot, poll_sec: int):
    parsed = read_changelog()
    if not parsed:
        log.warning("[updates] Watcher: changelog not found; watcher idle.")
        return
    _, body, path = parsed
    state = _load_state()
    last_hash = state.get("last_body_hash", "")
    last_heading = state.get("last_heading", "")
    try:
        last_mtime = path.stat().st_mtime
    except Exception:
        last_mtime = 0.0

    while True:
        await asyncio.sleep(max(1, poll_sec))

        channel_id = _resolve_channel_id()
        if not channel_id:
            continue
        try:
            channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
        except discord.NotFound:
            log.warning(f"[updates] Channel {channel_id} not found or bot lacks access. Watcher continuing.")
            await asyncio.sleep(10)
            continue
        except Exception as e:
            log.warning(f"[updates] Channel fetch error for {channel_id}: {e!r}")
            await asyncio.sleep(10)
            continue

        try:
            stat_mtime = path.stat().st_mtime
        except Exception:
            continue
        if stat_mtime <= last_mtime:
            continue
        last_mtime = stat_mtime

        await asyncio.sleep(0.6)  # debounce
        parsed_now = read_changelog()
        if not parsed_now:
            continue
        heading, body_now, p_now = parsed_now
        body_hash = hashlib.sha256(body_now.strip().encode("utf-8", errors="replace")).hexdigest()

        if body_hash != last_hash or heading != last_heading:
            media = _extract_media(body_now, p_now)
            em = build_updates_embed(heading, media.body_md, media.seal_url, media.footer_url)
            try:
                await channel.send(embed=em, files=media.files)
                log.info(f"[updates] Auto-posted changelog update to channel {channel_id}.")
                last_hash = body_hash
                last_heading = heading
                state.update({"last_body_hash": last_hash, "last_heading": last_heading, "last_mtime": last_mtime, "posted_at": time.time()})
                _save_state(state)
            except Exception as e:
                log.warning(f"[updates] Failed to post auto update to {channel_id}: {e!r}")

def _schedule_watcher(bot: commands.Bot):
    poll_sec = _env_int("UPDATES_POLL_SEC", 5)
    bot.loop.create_task(_watch_loop(bot, poll_sec))
    log.info(f"[updates] Watcher scheduled (poll={poll_sec}s).")

# -----------------------
# Back-compat exports for your bot.py
# -----------------------
def register_updates(tree: app_commands.CommandTree | commands.Bot):
    return register(tree)

def maybe_start_updates_watcher(_bot: commands.Bot):
    # no-op; watcher starts from setup_hook based on env flags
    log.info("[updates] maybe_start_updates_watcher: no-op (use UPDATES_WATCHER=1).")
