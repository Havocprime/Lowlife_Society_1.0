# ======================================================================
# FILE: GAME/src/cogs/playerlog.py
# ======================================================================
from __future__ import annotations

import asyncio
import logging, traceback, uuid
from typing import Callable, Optional, Tuple
import os

import discord
from discord import app_commands, Interaction
from discord.ext import commands, tasks

from src.services.tags_iter import collect_players_with_damage_tags
from src.tags import registry as tag_registry

TICK_SECONDS = 5  # HP-drain tick cadence

from src.services import playerlog as plog  # for quiet append_event in /revive
from src.services.playerlog import (
    ensure_playerlog_schema,
    list_events,
    pull_due_expiries,
    mark_expiry_processed,
    log_tag_expired,
    log_player_death,
)
from src.db import dal as core_dal
from src.services import health as health_svc

# health instrumentation is optional; keep import safe
try:
    from src.services.health_instrumentation import install as install_health_instrumentation
except Exception:  # pragma: no cover
    def install_health_instrumentation():
        pass

log = logging.getLogger("playerlog.cog")


# --------------------------- owner resolver ---------------------------
def _resolve_owner(user: discord.abc.User) -> Tuple[str, int]:
    """
    Returns (owner_kind, owner_id). Prefer canonical 'player' id if available,
    else fall back to ('discord', <discord_id>).
    """
    candidates: list[tuple[str, Callable]] = []
    for name in ("get_or_create_player", "get_or_create_account", "player_get_or_create", "ensure_player"):
        fn = getattr(core_dal, name, None)
        if callable(fn):
            candidates.append((name, fn))

    discord_id = int(user.id)
    for _name, fn in candidates:
        try:
            try:
                pid = fn(discord_id=discord_id)  # keyword form
            except TypeError:
                pid = fn(discord_id)            # positional form
            return ("player", int(pid))
        except Exception:
            pass
    return ("discord", discord_id)


# ----------------------------- hp helpers -----------------------------
async def _force_hp_zero(owner_kind: str, owner_id: int) -> None:
    """
    Best-effort to set HP to 0 without knowing exact health API.
    We'll try a few known names; if all fail, we only log the death event.
    """
    try:
        hp, _maxhp = health_svc.get_state(owner_kind, owner_id)
    except Exception:
        hp = None

    # If already <=0 nothing to do
    if hp is not None and hp <= 0:
        return

    for name in ("set_hp", "apply_delta", "adjust_hp", "set_state", "modify_hp"):
        fn = getattr(health_svc, name, None)
        try:
            if callable(fn):
                if name == "set_state":
                    fn(owner_kind, owner_id, hp=0)   # type: ignore[misc]
                elif name in ("apply_delta", "adjust_hp", "modify_hp"):
                    if hp is None:
                        continue
                    fn(owner_kind, owner_id, -int(hp))  # type: ignore[misc]
                else:
                    fn(owner_kind, owner_id, 0)        # set_hp(owner_kind, owner_id, 0)
                return
        except Exception:
            continue


async def _set_hp(owner_kind: str, owner_id: int, value: int) -> bool:
    """
    Best-effort setter for HP, mirroring _force_hp_zero but with an explicit value.
    Returns True on first method that succeeds.
    """
    for name in ("set_hp", "set_state", "apply_delta", "adjust_hp", "modify_hp"):
        fn = getattr(health_svc, name, None)
        try:
            if not callable(fn):
                continue
            if name == "set_state":
                fn(owner_kind, owner_id, hp=int(value))   # type: ignore[misc]
                return True
            elif name in ("apply_delta", "adjust_hp", "modify_hp"):
                try:
                    cur, _ = health_svc.get_state(owner_kind, owner_id)
                except Exception:
                    continue
                fn(owner_kind, owner_id, int(value) - int(cur))  # type: ignore[misc]
                return True
            else:
                fn(owner_kind, owner_id, int(value))             # type: ignore[misc]
                return True
        except Exception:
            continue
    return False


# -------------------------------- cog --------------------------------
class PlayerLogCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._watch_task: Optional[asyncio.Task] = None
        self._death_channel_id: Optional[int] = int(os.getenv("DEATH_CHANNEL_ID", "0")) or None

    async def cog_load(self):
        # Ensure storage and optional instrumentation
        ensure_playerlog_schema()
        install_health_instrumentation()

        # Quiet noise; death will be CRITICAL via dedicated logger
        logging.getLogger("tags.registry").setLevel(logging.WARNING)
        logging.getLogger("health").setLevel(logging.WARNING)

        # Start expiry watcher and HP-drain loop
        self._watch_task = asyncio.create_task(self._run_expiry_watcher())
        self.hp_tick_loop.start()

    async def cog_unload(self):
        if self._watch_task:
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                pass
            except Exception:
                log.exception("expiry watcher join failed")

        if self.hp_tick_loop.is_running():
            self.hp_tick_loop.cancel()

    # --------------------------- HP drain loop ---------------------------
    @tasks.loop(seconds=TICK_SECONDS)
    async def hp_tick_loop(self):
        """
        Periodically drains HP for players with active damage tags by
        reading tag instances and mapping them to registry keys.
        """
        try:
            for player_id, tags in collect_players_with_damage_tags():
                tag_registry.on_tick(
                    player_id,
                    tags,
                    elapsed_s=TICK_SECONDS,
                    death_broadcast=True,
                )
        except Exception:
            log.exception("hp_tick_loop failed")

    @hp_tick_loop.before_loop
    async def _wait_ready_hp(self):
        await self.bot.wait_until_ready()

    # ---------------------- death broadcast helper ----------------------
    async def _broadcast_death(self, owner_kind: str, owner_id: int, tag_name: str, instance_id: Optional[int]):
        """Optionally announce a death to a configured channel."""
        if not self._death_channel_id:
            return
        ch = self.bot.get_channel(self._death_channel_id)
        if not isinstance(ch, (discord.TextChannel, discord.Thread, discord.VoiceChannel)):
            return
        mention = f"<@{owner_id}>" if owner_kind == "discord" else f"`{owner_kind}:{owner_id}`"
        try:
            await ch.send(f"💀 **DEAD** {mention} — reason: tag_expired:`{tag_name}` (inst:{instance_id})")
        except Exception:
            log.exception("death broadcast failed")

    # ------------------------- expiry watcher loop ----------------------
    async def _run_expiry_watcher(self):
        """
        Polls our watch table and emits tag.expired (+ optional death) events.
        Keeps the console quiet; only death emits CRITICAL.
        """
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                due = pull_due_expiries()
                for row in due:
                    try:
                        mark_expiry_processed(row["id"])

                        # Log the expiry to the player log
                        log_tag_expired(
                            owner_kind=row["owner_kind"],
                            owner_id=int(row["owner_id"]),
                            tag_id=int(row["tag_id"]),
                            tag_name=row["tag_name"],
                            anchor_path=row.get("anchor_path"),
                            fatal_on_expire=bool(row.get("fatal_on_expire")),
                            source_kind="engine",
                            source_ref="expire",
                        )

                        # If fatal_on_expire → declare death (and try to set HP=0)
                        if row.get("fatal_on_expire"):
                            await _force_hp_zero(row["owner_kind"], int(row["owner_id"]))
                            # Ensure a single death event + CRITICAL line
                            log_player_death(
                                owner_kind=row["owner_kind"],
                                owner_id=int(row["owner_id"]),
                                reason=f"tag_expired:{row['tag_name']}",
                            )
                            logging.getLogger("death").critical(
                                "DEAD owner=%s:%s reason=tag_expired tag=%s inst=%s",
                                row["owner_kind"], row["owner_id"], row["tag_name"], row["instance_id"]
                            )
                            await self._broadcast_death(
                                row["owner_kind"], int(row["owner_id"]), row["tag_name"], row.get("instance_id")
                            )
                    except Exception:
                        # do not break the loop on one bad row
                        log.exception("expiry watcher failed for row id=%s", row.get("id"))
            except Exception:
                log.exception("expiry watcher tick failed")

            await asyncio.sleep(3)  # light polling

    # ---------------------------- /playerlog ---------------------------
    @app_commands.command(name="playerlog", description="View recent events (HP, tags, etc.) for you or a target user")
    @app_commands.describe(
        user="Target user (defaults to you)",
        limit="How many recent events (max 100)",
        kinds="Comma-separated filters (e.g., hp.delta,tag.applied,tag.tick,tag.expired,player.death)",
    )
    async def playerlog_cmd(
        self,
        itx: Interaction,
        user: Optional[discord.Member] = None,
        limit: app_commands.Range[int, 1, 100] = 20,
        kinds: Optional[str] = None,
    ):
        await itx.response.defer(ephemeral=True)
        trace = uuid.uuid4().hex[:8]

        try:
            target = user or itx.user
            owner_kind, owner_id = _resolve_owner(target)

            kind_list = None
            if kinds:
                kind_list = [s.strip() for s in kinds.split(",") if s.strip()]

            rows = list_events(owner_kind, owner_id, limit=int(limit), kinds=kind_list)
            if not rows:
                return await itx.followup.send("No events yet.", ephemeral=True)

            def fmt_row(r: dict) -> str:
                k = r["kind"]
                t = r["ts"].replace("T", " ").replace("Z", "Z")
                anchor = f" @ `{r['anchor_path']}`" if r.get("anchor_path") else ""
                src = ""
                if r.get("source_kind"):
                    src = f" · src:`{r['source_kind']}{':' + r['source_ref'] if r.get('source_ref') else ''}`"
                if k == "hp.delta":
                    dh = r.get("delta_hp") or 0
                    ha = r.get("hp_after")
                    return f"- `{t}` · **HP {dh:+d}** → `{ha}`{src}"
                elif k in ("tag.applied", "tag.tick", "tag.expired"):
                    tag = r.get("tag_name") or f"id:{r.get('tag_id')}"
                    extra = ""
                    if k == "tag.tick" and r.get("delta_hp") is not None:
                        extra = f" · hp {r['delta_hp']:+d} → `{r.get('hp_after')}`"
                    if k == "tag.expired" and (r.get("metadata") or {}).get("fatal_on_expire"):
                        extra += " · **FATAL**"
                    return f"- `{t}` · **{k}** · *{tag}*{anchor}{extra}{src}"
                elif k == "player.death":
                    why = (r.get("metadata") or {}).get("reason") or "unknown"
                    return f"- `{t}` · **PLAYER DEATH** · reason:`{why}`"
                elif k == "player.revive":
                    md = (r.get("metadata") or {})
                    hp_to = md.get("set_hp")
                    ok = md.get("ok")
                    return f"- `{t}` · **PLAYER REVIVE** · hp→`{hp_to}` {'✅' if ok else '⚠️'}{src}"
                else:
                    return f"- `{t}` · **{k}**{anchor}{src}"

            lines = [f"**Owner:** `{owner_kind}:{owner_id}` · Showing last {len(rows)} event(s)"]
            lines += [fmt_row(r) for r in rows]
            await itx.followup.send("\n".join(lines), ephemeral=True)
        except Exception:
            log.error("[playerlog] trace=%s\n%s", trace, traceback.format_exc())
            await itx.followup.send(f"⚠️ Something broke. Trace `{trace}`.", ephemeral=True)

    # ------------------------------ /revive ----------------------------
    @app_commands.command(name="revive", description="Admin: restore HP and log a revive")
    @app_commands.describe(user="Target user (defaults to you)", hp="HP to set (default = max HP or 1)")
    @app_commands.default_permissions(administrator=True)
    async def revive_cmd(
        self,
        itx: Interaction,
        user: Optional[discord.Member] = None,
        hp: Optional[app_commands.Range[int, 1, 10_000]] = None,
    ):
        await itx.response.defer(ephemeral=True)
        target = user or itx.user
        owner_kind, owner_id = _resolve_owner(target)

        # choose target HP
        try:
            _cur_hp, max_hp = health_svc.get_state(owner_kind, owner_id)
        except Exception:
            _cur_hp, max_hp = None, None
        target_hp = int(hp) if hp is not None else (int(max_hp) if max_hp is not None else 1)

        ok = await _set_hp(owner_kind, owner_id, target_hp)

        # log a revive event (quiet)
        try:
            plog.append_event(
                owner_kind=owner_kind,
                owner_id=int(owner_id),
                kind="player.revive",
                metadata={"set_hp": target_hp, "ok": bool(ok)},
                source_kind="cmd",
                source_ref="revive",
            )
        except Exception:
            log.debug("revive append_event failed", exc_info=True)

        msg = f"Revive {'✅' if ok else '⚠️'} — set HP → `{target_hp}` for `{owner_kind}:{owner_id}`"
        await itx.followup.send(msg, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(PlayerLogCog(bot))
# ======================================================================
