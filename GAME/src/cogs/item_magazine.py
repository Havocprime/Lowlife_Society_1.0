# GAME/src/cogs/item_magazine.py
from __future__ import annotations

import os
import shlex
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, List

import discord
from discord.ext import commands, tasks

from src.inventory.manager import create_item, get_item_by_name
from src.models.item import ItemClass, Item

# Try to reuse your inventory embed builder if present
try:
    from src.cogs.inventory import build_item_embed as _inventory_item_embed  # type: ignore
except Exception:
    _inventory_item_embed = None


# ---------- Paths & config ----------
HERE = Path(__file__).resolve()
ROOT = HERE.parents[2]  # GAME/

MAG_FILE = Path(os.getenv("ITEM_MAG_FILE", str(ROOT / "data" / "item_magazine.txt"))).resolve()
MAG_INTERVAL_S = float(os.getenv("ITEM_MAG_INTERVAL_S", "60"))

MAG_CURSOR = Path(os.getenv("ITEM_MAG_CURSOR_FILE", str(MAG_FILE) + ".cursor")).resolve()
MAG_PROCESSED = Path(os.getenv("ITEM_MAG_PROCESSED_FILE", str(MAG_FILE) + ".processed.json")).resolve()

ANNOUNCE_FILE = ROOT / "data" / "item_mag_channel.txt"
CDN_FILE = ROOT / "data" / "item_mag_cdn_channel.txt"

# Provide safe module-level fallbacks so imports never crash
ANNOUNCE_CHANNEL_ID = 0
try:
    if ANNOUNCE_FILE.exists():
        ANNOUNCE_CHANNEL_ID = int((ANNOUNCE_FILE.read_text(encoding="utf-8").strip() or "0"))
    else:
        ANNOUNCE_CHANNEL_ID = int(os.getenv("MAG_ANNOUNCE_CHANNEL_ID", "0"))
except Exception:
    ANNOUNCE_CHANNEL_ID = 0

CDN_CHANNEL_ID = 0
try:
    if CDN_FILE.exists():
        CDN_CHANNEL_ID = int((CDN_FILE.read_text(encoding="utf-8").strip() or "0"))
except Exception:
    CDN_CHANNEL_ID = 0


# ---------- Helpers ----------
def _coerce_value(raw: str) -> Any:
    lowered = raw.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    if lowered.isdigit() or (lowered.startswith("-") and lowered[1:].isdigit()):
        try:
            return int(lowered)
        except Exception:
            pass
    try:
        if any(c in raw for c in (".", "e", "E")):
            return float(raw)
    except Exception:
        pass
    return raw


def _item_class_label(ic: Any) -> str:
    """Return a printable/sluggable class label regardless of enum/string."""
    return getattr(ic, "name", str(ic)).strip()


def _coerce_item_class(value: Any) -> Any:
    """Try to coerce a string into ItemClass; fall back to lowercase string."""
    if isinstance(value, ItemClass):
        return value
    if not isinstance(value, str):
        return value
    key = value.split(".")[-1].strip().lower()
    aliases = {
        "tools": "tool",
        "armour": "armor",
        "apparel": "clothing",
        "clothes": "clothing",
        "medicine": "medical",
        "consumables": "consumable",
        "components": "component",
        "materials": "material",
    }
    key = aliases.get(key, key)
    try:
        if hasattr(ItemClass, key):
            return getattr(ItemClass, key)
        return ItemClass[key.upper()]
    except Exception:
        return key  # keep as string; rest of code handles it


def _parse_createitem2(line: str) -> Optional[Dict[str, Any]]:
    """
    Accept lines like:
    /createitem2 name:"Torque Wrench" item_class:tool subcategory:Repair durability:75 cash:120 stack_max:1 equippable:true
    """
    s = line.strip()
    if not s.startswith("/createitem2"):
        return None

    tokens = shlex.split(s)
    raw_kwargs: Dict[str, Any] = {}
    for tok in tokens[1:]:
        if ":" not in tok:
            continue
        k, v = tok.split(":", 1)
        k, v = k.strip(), v.strip()
        if not k:
            continue
        raw_kwargs[k] = _coerce_value(v)

    field_map = {
        "name": "name",
        "item_class": "item_class",
        "subcategory": "subcategory",
        "durability": "durability",
        "cash": "cash_value",
        "stack_max": "stack_max",
        "equippable": "equippable",
        "rarity": "rarity",
        "scrap": "scrap_value",
        "quality": "quality_float",
        "bind_on_pickup": "bind_on_pickup",
        "hidden_trait": "hidden_trait",
    }

    mapped: Dict[str, Any] = {}
    for src, dst in field_map.items():
        if src in raw_kwargs:
            mapped[dst] = raw_kwargs[src]

    # Coerce item_class robustly; may remain a string if not in enum
    if "item_class" in mapped:
        mapped["item_class"] = _coerce_item_class(mapped["item_class"])

    if "name" not in mapped or "item_class" not in mapped:
        return None
    return mapped


def _build_item_from_kwargs(mapped: Dict[str, Any]) -> Item:
    """
    Create an Item without calling __init__ so the DAL assigns id/created_at.
    """
    it: Item = object.__new__(Item)  # bypass __init__

    it.name = str(mapped["name"])
    it.item_class = mapped["item_class"]

    it.bind_on_pickup = bool(mapped.get("bind_on_pickup", False))
    it.durability = int(mapped.get("durability", 0))
    it.cash_value = int(mapped.get("cash_value", 0))
    it.scrap_value = int(mapped.get("scrap_value", 0))
    it.hidden_trait = str(mapped.get("hidden_trait", ""))

    it.mint_index = int(mapped.get("mint_index", 0))
    it.rarity = str(mapped.get("rarity", "common"))
    it.stack_max = int(mapped.get("stack_max", 1))
    it.quality_float = float(mapped.get("quality_float", 100.0))
    it.equippable = bool(mapped.get("equippable", True))
    it.subcategory = mapped.get("subcategory")

    # Temporary placeholders; DB will overwrite
    it.id = 0
    it.created_at = datetime.now(timezone.utc)
    return it


def _slug(s: Optional[str]) -> str:
    if not s:
        return ""
    out: List[str] = []
    prev = "_"
    for ch in s.lower():
        if ch.isalnum():
            out.append(ch)
            prev = ch
        else:
            if prev != "_":
                out.append("_")
                prev = "_"
    return "".join(out).strip("_")


def _normalize_icon_key(name: str) -> str:
    """
    Normalize a pinned filename to a cache key:
    - lowercase, strip extension
    - replace dashes/spaces with underscores
    - remove common prefixes: icon_, ic_, item_, cat_, category_
    - drop trailing pure-number or @2x/_512 suffixes
    """
    base = name.lower()
    if "." in base:
        base = base.rsplit(".", 1)[0]
    base = base.replace("-", "_").replace(" ", "_")
    for pref in ("icon_", "ic_", "item_", "cat_", "category_"):
        if base.startswith(pref):
            base = base[len(pref):]
    for suf in ("_1024", "_512", "_256", "_128", "_64", "_32", "@2x", "@3x"):
        if base.endswith(suf):
            base = base[: -len(suf)]
    while "__" in base:
        base = base.replace("__", "_")
    return base.strip("_")


# ---------- Cog ----------
class ItemMagazine(commands.Cog):
    """
    Load items from a text 'magazine', create them on a cadence, and announce
    using embeds that include category/weapon/tool icons from a CDN channel's pins.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._cursor = 0
        self._processed: set[str] = set()

        # announce channel
        self._announce_channel_id = ANNOUNCE_CHANNEL_ID
        try:
            if ANNOUNCE_FILE.exists():
                self._announce_channel_id = int((ANNOUNCE_FILE.read_text("utf-8").strip() or "0"))
        except Exception:
            self._announce_channel_id = 0

        # CDN channel (pinned icons)
        self._cdn_channel_id = CDN_CHANNEL_ID
        try:
            if CDN_FILE.exists():
                self._cdn_channel_id = int((CDN_FILE.read_text("utf-8").strip() or "0"))
        except Exception:
            self._cdn_channel_id = 0

        # icon cache: key -> url
        self._icon_cache: Dict[str, str] = {}

        # restore cursor
        try:
            if MAG_CURSOR.exists():
                self._cursor = int((MAG_CURSOR.read_text().strip() or "0"))
        except Exception:
            self._cursor = 0

        # restore processed
        try:
            if MAG_PROCESSED.exists():
                data = json.loads(MAG_PROCESSED.read_text("utf-8"))
                if isinstance(data, list):
                    self._processed = set(map(str, data))
        except Exception:
            self._processed = set()

    async def cog_load(self) -> None:
        try:
            self.loader_loop.change_interval(seconds=MAG_INTERVAL_S)
            if not self.loader_loop.is_running():
                self.loader_loop.start()
        except Exception as e:
            print(f"[ItemMagazine] Failed to start loader loop: {e!r}")

    def cog_unload(self):
        try:
            if self.loader_loop.is_running():
                self.loader_loop.cancel()
        except Exception:
            pass

    # ---------- persistence ----------
    def _save_cursor(self) -> None:
        try:
            MAG_CURSOR.parent.mkdir(parents=True, exist_ok=True)
            MAG_CURSOR.write_text(str(self._cursor), encoding="utf-8")
        except Exception:
            pass

    def _save_processed(self) -> None:
        try:
            MAG_PROCESSED.parent.mkdir(parents=True, exist_ok=True)
            MAG_PROCESSED.write_text(json.dumps(sorted(self._processed)), encoding="utf-8")
        except Exception:
            pass

    def _save_channel(self) -> None:
        try:
            ANNOUNCE_FILE.parent.mkdir(parents=True, exist_ok=True)
            ANNOUNCE_FILE.write_text(str(self._announce_channel_id), encoding="utf-8")
        except Exception:
            pass

    def _save_cdn_channel(self) -> None:
        try:
            CDN_FILE.parent.mkdir(parents=True, exist_ok=True)
            CDN_FILE.write_text(str(self._cdn_channel_id), encoding="utf-8")
        except Exception:
            pass

    # ---------- magazine core ----------
    def _find_next_line(self) -> Tuple[Optional[Dict[str, Any]], Optional[str], int, Optional[str]]:
        if not MAG_FILE.exists():
            return None, None, self._cursor, None

        lines = MAG_FILE.read_text("utf-8", errors="ignore").splitlines()
        i = self._cursor
        while i < len(lines):
            raw = lines[i]
            s = raw.strip()
            i += 1

            if not s or s.startswith("#") or s.startswith("//"):
                continue

            mapped = _parse_createitem2(s)
            if not mapped:
                continue

            name_key = str(mapped.get("name") or f"line{i}")

            # de-dupe if already created previously
            if name_key in self._processed:
                continue

            try:
                # optional: skip if an item already exists by this name
                existing = get_item_by_name(str(mapped["name"]))
                if existing:
                    self._processed.add(name_key)
                    continue
            except Exception:
                pass

            return mapped, name_key, i, raw

        return None, None, len(lines), None

    async def _ensure_icons_loaded(self) -> None:
        if not self._icon_cache and self._cdn_channel_id:
            await self._load_icon_cache_from_pins()

    async def _tick(self, origin_channel: Optional[discord.abc.Messageable] = None):
        """Process exactly one actionable line (if any)."""
        mapped, name_key, next_index, _ = self._find_next_line()

        # nothing to do -> advance and persist
        if not mapped:
            self._cursor = next_index
            self._save_cursor()
            self._save_processed()
            if origin_channel:
                await origin_channel.send(f"â„¹ï¸ Magazine idle (cursor={self._cursor}).")
            return

        try:
            # Build a lightweight Item object (id=0 placeholder)
            item_obj = _build_item_from_kwargs(mapped)

            # Persist to DB; DAL returns the new primary key
            new_id = create_item(item=item_obj)

            # Copy the id back so embeds don't show 0
            try:
                item_obj.id = int(new_id)
            except Exception:
                item_obj.id = int(str(new_id))

            # Optional: refresh from DB to pick up DB-side defaults (created_at, etc.)
            try:
                persisted = get_item_by_name(item_obj.name)
                if persisted and getattr(persisted, "id", 0):
                    item_obj = persisted
            except Exception:
                pass

            # Advance cursor, mark processed, persist local state
            self._cursor = next_index
            if name_key:
                self._processed.add(name_key)
            self._save_cursor()
            self._save_processed()

            print(f"[ItemMagazine] Created item: {item_obj.name} (id={item_obj.id}, cursor={self._cursor})")

            # Acknowledge where the command was run (plain text, shows the id)
            if origin_channel:
                try:
                    await origin_channel.send(f"âœ… Created item: {item_obj.name} (ID {item_obj.id})")
                except Exception:
                    pass

            # Post the rich embed to the announce channel
            await self._announce_created(item_obj)

        except Exception as e:
            # advance cursor but do not mark processed so user can fix and retry
            self._cursor = next_index
            self._save_cursor()
            print(f"[ItemMagazine] Failed to create item at cursor {self._cursor}: {e!r}")
            if origin_channel:
                await origin_channel.send(f"âŒ Failed to create at cursor {self._cursor}: `{e!r}`")

    # ---------- icon CDN ----------
    async def _load_icon_cache_from_pins(self) -> int:
        self._icon_cache.clear()
        if not self._cdn_channel_id:
            return 0

        chan = self.bot.get_channel(self._cdn_channel_id)
        if not isinstance(chan, (discord.TextChannel, discord.Thread)):
            try:
                chan = await self.bot.fetch_channel(self._cdn_channel_id)  # type: ignore
            except Exception:
                return 0
        if not isinstance(chan, (discord.TextChannel, discord.Thread)):
            return 0

        try:
            pins = await chan.pins()
        except Exception:
            return 0

        count = 0
        for msg in pins:
            for att in msg.attachments:
                fname = (att.filename or "").strip()
                if not fname:
                    continue
                low = fname.lower()
                if not (low.endswith(".png") or low.endswith(".jpg") or low.endswith(".jpeg") or low.endswith(".webp")):
                    continue

                key = _normalize_icon_key(fname)
                self._icon_cache[key] = att.url
                count += 1

                # A couple convenience aliases:
                if "_" in key:
                    tail = key.split("_", 1)[1]
                    self._icon_cache.setdefault(tail, att.url)
        return count

    def _synonyms_for_sub(self, sub: str) -> List[str]:
        s = _slug(sub)
        synonyms = {
            "utility": ["utility", "util", "general", "misc"],
            "repair": ["repair", "toolrepair", "fix"],
            "rifle": ["rifle", "ar", "carbine"],
            "smg": ["smg"],
            "pistol": ["pistol", "handgun"],
        }
        return synonyms.get(s, [s]) if s else []

    def _resolve_icon_url(self, item: Item) -> Optional[str]:
        if not self._icon_cache:
            return None

        cls_key = _slug(_item_class_label(item.item_class))  # enum or string
        sub = _slug(item.subcategory) if item.subcategory else ""
        name_key = _slug(item.name)

        candidates: List[str] = []

        # class + subcategory (and subcategory synonyms)
        if cls_key and sub:
            for syn in self._synonyms_for_sub(sub):
                candidates.append(f"{cls_key}_{syn}")

        # plain subcategory (and synonyms)
        if sub:
            candidates.extend(self._synonyms_for_sub(sub))

        # class only
        if cls_key:
            candidates.append(cls_key)

        # exact name slug (lets you override per item)
        candidates.append(name_key)

        # defaults
        candidates.extend(["default", "misc"])

        for k in candidates:
            url = self._icon_cache.get(k)
            if url:
                return url

        print(
            f"[ItemMagazine] Icon not found for '{item.name}' (class={cls_key}, sub={sub}). "
            f"Tried: {', '.join(candidates)}"
        )
        return None

    # ---------- announcing ----------
    async def _announce_created(self, item: Item, origin_channel: Optional[discord.abc.Messageable] = None):
        await self._ensure_icons_loaded()

        # Prefer your inventory embed
        embed: Optional[discord.Embed] = None
        if _inventory_item_embed:
            try:
                try:
                    embed = _inventory_item_embed(item)  # type: ignore[arg-type]
                except TypeError:
                    embed = _inventory_item_embed(None, item)  # type: ignore[misc]
            except Exception:
                embed = None

        if embed is None:
            cls_label = _item_class_label(item.item_class)
            embed = discord.Embed(title="NEW Item", color=0xE74C3C)
            embed.description = (
                f"**\"{item.name}\"** â€” **ID** `{item.id}`\n"
                f"*{cls_label}* / *{item.subcategory or 'Utility'}* Â· **{item.rarity or 'common'}**\n\n"
                f"**Durability** {item.durability}   **Stack** {item.stack_max}   **Cash** {item.cash_value}\n"
                f"**Equippable** {'Yes' if item.equippable else 'No'}"
            )

        icon_url = self._resolve_icon_url(item)
        if icon_url:
            try:
                embed.set_thumbnail(url=icon_url)
            except Exception:
                pass

        # Announce to configured channel
        if self._announce_channel_id:
            ch = self.bot.get_channel(self._announce_channel_id)
            if not isinstance(ch, (discord.TextChannel, discord.Thread)):
                try:
                    ch = await self.bot.fetch_channel(self._announce_channel_id)  # type: ignore
                except Exception:
                    ch = None
            if isinstance(ch, (discord.TextChannel, discord.Thread)):
                try:
                    await ch.send(embed=embed)
                except Exception:
                    pass

        # Also acknowledge in the invoking channel (if any)
        if origin_channel:
            try:
                await origin_channel.send(f"âœ… Created item: {item.name}")
            except Exception:
                pass

    # ---------- background loop ----------
    @tasks.loop(seconds=60.0)
    async def loader_loop(self):
        await self.bot.wait_until_ready()
        await self._tick(None)

    # ---------- commands ----------
    @commands.hybrid_command(description="Manually process the next line in the item magazine now.")
    @commands.has_permissions(manage_guild=True)
    async def mag_next(self, ctx: commands.Context):
        await self._tick(ctx.channel)

    @commands.hybrid_command(description="Show item magazine status.")
    @commands.has_permissions(manage_guild=True)
    async def mag_status(self, ctx: commands.Context):
        ann = self.bot.get_channel(self._announce_channel_id) if self._announce_channel_id else None
        ann_str = f"<#{self._announce_channel_id}>" if isinstance(ann, (discord.TextChannel, discord.Thread)) else "â€”"

        cdn = self.bot.get_channel(self._cdn_channel_id) if self._cdn_channel_id else None
        cdn_str = f"<#{self._cdn_channel_id}>" if isinstance(cdn, (discord.TextChannel, discord.Thread)) else "â€”"

        await ctx.reply(
            f"**File:** `{MAG_FILE}`\n"
            f"**Interval:** {MAG_INTERVAL_S:.1f}s\n"
            f"**Cursor:** {self._cursor}\n"
            f"**Processed:** {len(self._processed)}\n"
            f"**Announce:** {ann_str}\n"
            f"**CDN:** {cdn_str} â€¢ **Icons cached:** {len(self._icon_cache)}"
        )

    @commands.hybrid_command(description="Preview the next actionable line without creating it.")
    @commands.has_permissions(manage_guild=True)
    async def mag_preview(self, ctx: commands.Context):
        mapped, name_key, _, raw = self._find_next_line()
        if not mapped:
            await ctx.reply("â„¹ï¸ No actionable line found (EOF).")
            return
        preview = " ".join(f"{k}:{v!r}" for k, v in mapped.items())
        await ctx.reply(f"**Next line @ index {self._cursor}:**\n{preview}\n*(internal key: {name_key})*")

    @commands.hybrid_command(description="Set the channel where created items are announced.")
    @commands.has_permissions(manage_guild=True)
    async def mag_set_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        self._announce_channel_id = channel.id
        self._save_channel()
        await ctx.reply(f"ðŸ”Š Announcements will post in {channel.mention}.")

    @commands.hybrid_command(description="Set the CDN (icons) channel; pinned images become your icon library.")
    @commands.has_permissions(manage_guild=True)
    async def mag_set_cdn_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        self._cdn_channel_id = channel.id
        self._save_cdn_channel()
        added = await self._load_icon_cache_from_pins()
        await ctx.reply(f"ðŸ–¼ï¸ CDN set to {channel.mention}. Cached **{added}** icon(s) from pins.")

    @commands.hybrid_command(description="Clear & rebuild the icon cache from the CDN channel's pinned images.")
    @commands.has_permissions(manage_guild=True)
    async def mag_icons_cache_clear(self, ctx: commands.Context):
        self._icon_cache.clear()
        added = await self._load_icon_cache_from_pins()
        await ctx.reply(f"ðŸ§¹ Icon cache rebuilt â€” **{added}** icon(s) loaded.")


async def setup(bot: commands.Bot):
    await bot.add_cog(ItemMagazine(bot))

async def setup(bot: commands.Bot):
    if bot.get_cog("ItemMagazine") is None:
        await bot.add_cog(ItemMagazine(bot))
