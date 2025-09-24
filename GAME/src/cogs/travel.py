# GAME/src/cogs/travel.py
from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import discord
from discord import app_commands, Interaction
from discord.ext import commands

log = logging.getLogger("travel.cog")

# ---------- Helpers / Data ----------

NPC_NAMES = [
    "Greycoat Courier", "Dockhand", "Street Vendor", "Windbreaker Runner",
    "Pipefitter", "Courier on BMX", "Night-Shift Janitor", "Hooded Figure",
    "Courier Pigeon Guy", "Payphone Caller", "Hood Up, Hands in Pockets",
    "Back-Alley Medic", "Street Musician", "Newspaper Hawker"
]

@dataclass
class SeenPerson:
    label: str        # display name (player display_name or NPC tag)
    snowflake: int    # user id if player; 0 for NPC
    is_player: bool

@dataclass
class TravelSession:
    user_id: int
    guild_id: int
    origin_channel_id: int
    dest_channel_id: int
    duration_s: int = 30
    started_monotonic: float = field(default_factory=time.monotonic)
    seen: List[SeenPerson] = field(default_factory=list)
    message_id: Optional[int] = None  # not used now, we keep msg object
    done: bool = False

    def remaining(self) -> int:
        elapsed = int(time.monotonic() - self.started_monotonic)
        return max(0, self.duration_s - elapsed)


def _route_from_channel(ch: discord.TextChannel) -> List[discord.TextChannel]:
    """All text channels in the same category, ordered by position."""
    if ch.category is None:
        route = sorted(
            [c for c in ch.guild.text_channels if c.permissions_for(ch.guild.me).read_messages],
            key=lambda c: (c.position, c.id),
        )
    else:
        route = sorted(
            [c for c in ch.guild.text_channels
             if c.category_id == ch.category_id and c.permissions_for(ch.guild.me).read_messages],
            key=lambda c: (c.position, c.id),
        )
    return route


def _next_channel(current: discord.TextChannel, steps: int) -> Tuple[discord.TextChannel, int, int]:
    """Return (destination, idx_current, idx_dest). Steps forward; clamps at end."""
    route = _route_from_channel(current)
    if current not in route:
        route.append(current)
        route.sort(key=lambda c: (c.position, c.id))
    idx = route.index(current)
    dest_idx = min(len(route) - 1, idx + max(1, steps))
    return route[dest_idx], idx, dest_idx


def _pick_someone(guild: discord.Guild, walker_id: int) -> SeenPerson:
    """50/50 player vs NPC. Player chosen from guild members (non-bot)."""
    is_player = random.random() < 0.5
    if is_player:
        candidates = [m for m in guild.members if not m.bot and m.id != walker_id]
        if candidates:
            m = random.choice(candidates)
            label = m.display_name
            return SeenPerson(label=label, snowflake=m.id, is_player=True)
    label = random.choice(NPC_NAMES)
    return SeenPerson(label=label, snowflake=0, is_player=False)


def _people_block(seen: List[SeenPerson]) -> str:
    if not seen:
        return "*No one yet… keep walking.*"
    lines = []
    for i, p in enumerate(seen, 1):
        mark = "🧍" if p.is_player else "👤"
        lines.append(f"{i}. {mark} **{discord.utils.escape_markdown(p.label)}**")
    return "\n".join(lines)


# ---------- UI ----------

class ProfileButton(discord.ui.Button):
    """Edits the SAME walking embed to show a one-card 'Profile Peek'."""
    def __init__(self, person: SeenPerson, index: int):
        super().__init__(
            label=f"View Profile #{index}",
            style=discord.ButtonStyle.secondary,
            custom_id=f"profile:{('u' if person.is_player else 'n')}:{person.snowflake}:{index}",
            row=min(4, (index - 1) // 5),
        )
        self.person = person
        self.index = index

    async def callback(self, itx: Interaction) -> None:
        p = self.person

        # Start from the current message's first embed (our walking card)
        base = itx.message.embeds[0] if itx.message and itx.message.embeds else discord.Embed(title="Travel")
        new = discord.Embed(
            title=base.title,
            description=base.description,
            color=base.color
        )
        # copy non-peek fields
        for f in base.fields:
            if f.name != "🪪 Profile Peek":
                new.add_field(name=f.name, value=f.value, inline=f.inline)
        if base.footer and base.footer.text:
            new.set_footer(text=base.footer.text)

        # add/replace the peek field
        desc = f"**Name:** {discord.utils.escape_markdown(p.label)}\n"
        if p.is_player:
            desc += f"**Discord:** <@{p.snowflake}>\n"
            desc += "*Character sheet coming soon…*"
        else:
            desc += "*Mysterious passerby. Details obscured…*"
        new.add_field(name="🪪 Profile Peek", value=desc, inline=False)

        await itx.response.edit_message(embed=new, view=self.view)


class TravelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    def rebuild_buttons(self, seen: List[SeenPerson]) -> None:
        self.clear_items()
        for idx, person in enumerate(seen[:25], start=1):
            self.add_item(ProfileButton(person, idx))


# ---------- Cog ----------

class Travel(commands.Cog):
    """City travel & location system."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._sessions: Dict[int, TravelSession] = {}  # key: user_id

    def get_seen_for_user(self, user_id: int) -> List[dict]:
        """Expose seen list to the Action Bar."""
        sess = self._sessions.get(user_id)
        if not sess or not sess.seen:
            return []
        return [{"label": p.label, "snowflake": p.snowflake, "is_player": p.is_player} for p in sess.seen]

    # ===== Commands =====

    @app_commands.command(name="travel", description="Open the travel menu.")
    async def travel_root(self, itx: Interaction):
        await itx.response.send_message(
            "Use `/travel_walk` to move to the next channel, or `/travel_go steps:<n>` to skip multiple.",
            ephemeral=True,
        )

    @app_commands.command(name="travel_status", description="Show your current travel status.")
    async def travel_status(self, itx: Interaction):
        sess = self._sessions.get(itx.user.id)
        if not sess:
            await itx.response.send_message("Not traveling. You are here.", ephemeral=True)
            return
        dest = itx.client.get_channel(sess.dest_channel_id)
        remaining = sess.remaining()
        await itx.response.send_message(
            f"Traveling to {dest.mention if dest else '#unknown'} — **{remaining}s** remaining.",
            ephemeral=True,
        )

    @app_commands.command(name="travel_go", description="Travel multiple channels at once (vehicle-like).")
    @app_commands.describe(steps="How many channels to skip forward (default 2).")
    async def travel_go(self, itx: Interaction, steps: app_commands.Range[int, 1, 10] = 2):
        await self._start_walk(itx, steps)

    @app_commands.command(name="travel_walk", description="Walk to the next channel in this category.")
    @app_commands.describe(steps="How many channels forward (1 = walk to next).")
    async def travel_walk(self, itx: Interaction, steps: app_commands.Range[int, 1, 10] = 1):
        await self._start_walk(itx, steps)

    # ===== Core logic =====

    async def _start_walk(self, itx: Interaction, steps: int) -> None:
        # Prevent overlapping sessions
        prior = self._sessions.get(itx.user.id)
        if prior and not prior.done and prior.remaining() > 0:
            if not itx.response.is_done():
                await itx.response.send_message("You’re already traveling. Try `/travel_status`.", ephemeral=True)
            else:
                await itx.followup.send("You’re already traveling. Try `/travel_status`.", ephemeral=True)
            return

        # Resolve destination
        if not isinstance(itx.channel, discord.TextChannel):
            if not itx.response.is_done():
                await itx.response.send_message("You can only travel from a text channel.", ephemeral=True)
            else:
                await itx.followup.send("You can only travel from a text channel.", ephemeral=True)
            return

        dest, idx, dest_idx = _next_channel(itx.channel, steps)
        if dest.id == itx.channel.id:
            if not itx.response.is_done():
                await itx.response.send_message("This is the end of the route. Nowhere further to walk.", ephemeral=True)
            else:
                await itx.followup.send("This is the end of the route. Nowhere further to walk.", ephemeral=True)
            return

        view = TravelView()
        embed = discord.Embed(
            title="🚶 Walking…",
            description=f"Destination: {dest.mention}\nRoute: position **{idx+1} → {dest_idx+1}**",
        )
        embed.add_field(name="Passing By", value="*No one yet…*", inline=False)
        embed.set_footer(text="Travel time: 30s • New passerby checks every 3–5s (50% chance)")

        if not itx.response.is_done():
            await itx.response.send_message(embed=embed, view=view, ephemeral=True)
            msg = await itx.original_response()
        else:
            msg = await itx.followup.send(embed=embed, view=view, ephemeral=True, wait=True)

        sess = TravelSession(
            user_id=itx.user.id,
            guild_id=itx.guild.id,
            origin_channel_id=itx.channel.id,
            dest_channel_id=dest.id,
            duration_s=30,
        )
        self._sessions[itx.user.id] = sess

        # Start the background task
        self.bot.loop.create_task(self._walk_task(itx, msg, view, sess))

    async def _walk_task(
        self,
        itx: Interaction,
        msg: discord.Message,
        view: TravelView,
        sess: TravelSession,
    ) -> None:
        try:
            while sess.remaining() > 0:
                await asyncio.sleep(random.uniform(3.0, 5.0))
                if sess.remaining() <= 0:
                    break

                # 50/50: pass someone
                if random.random() < 0.5:
                    person = _pick_someone(itx.guild, sess.user_id)
                    if all(p.label != person.label or p.is_player != person.is_player for p in sess.seen):
                        sess.seen.append(person)

                # Update the one walking card (embed edit)
                view.rebuild_buttons(sess.seen)
                embed = discord.Embed(
                    title=f"🚶 Walking… {sess.remaining()}s left",
                    description=f"Destination: <#{sess.dest_channel_id}>",
                )
                embed.add_field(name="Passing By", value=_people_block(sess.seen), inline=False)
                embed.set_footer(text="Travel time: 30s • New passerby checks every 3–5s (50% chance)")
                try:
                    await msg.edit(embed=embed, view=view)
                except Exception as e:
                    log.warning("Failed to edit travel message: %r", e)

            # Arrived
            sess.done = True
            destination = itx.client.get_channel(sess.dest_channel_id)
            origin = itx.client.get_channel(sess.origin_channel_id)

            # Public arrival (no passersby listed)
            if isinstance(destination, discord.TextChannel):
                arrival_embed = discord.Embed(
                    title="🏁 Arrival",
                    description=f"{itx.user.mention} arrives from {origin.mention if origin else '#unknown'}.",
                )
                await destination.send(embed=arrival_embed)

            # Finalize the same walking card (keep buttons so you can still peek)
            final_embed = discord.Embed(
                title="🏁 Arrived!",
                description=f"You’ve arrived at {destination.mention if destination else '#unknown'}.",
            )
            final_embed.add_field(name="You passed:", value=_people_block(sess.seen), inline=False)
            try:
                await msg.edit(embed=final_embed, view=view)
            except Exception:
                pass

            # Auto-open a fresh Action Bar so controls are always visible
            acog = itx.client.get_cog("ActionMenu")
            if acog and hasattr(acog, "open_menu"):
                try:
                    await acog.open_menu(itx)
                except Exception as e:
                    log.warning("Failed to auto-open Action Bar: %r", e)

        finally:
            self._sessions.pop(sess.user_id, None)


async def setup(bot: commands.Bot):
    await bot.add_cog(Travel(bot))
