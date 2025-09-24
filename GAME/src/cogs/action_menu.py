# GAME/src/cogs/action_menu.py
from __future__ import annotations

import logging
from typing import List, Dict, Optional

import discord
from discord import app_commands, Interaction
from discord.ext import commands

log = logging.getLogger("actions.cog")

# ---------------------------
# Context helpers (stubs now)
# ---------------------------

def _has_vehicle(user_id: int) -> bool:
    return False

def _travel_cog(bot: commands.Bot):
    return bot.get_cog("Travel")

def _nearby_people(bot: commands.Bot, user_id: int) -> List[Dict]:
    tcog = _travel_cog(bot)
    if tcog and hasattr(tcog, "get_seen_for_user"):
        try:
            return list(tcog.get_seen_for_user(user_id))  # type: ignore
        except Exception:
            pass
    return []


# ---------------------------
# UI: Launcher (persistent)
# ---------------------------

class OpenActionsButton(discord.ui.Button):
    def __init__(self, cog: "ActionMenu"):
        super().__init__(
            label="Open Action Bar",
            style=discord.ButtonStyle.primary,
            custom_id="actions:open",
        )
        self.cog = cog

    async def callback(self, itx: Interaction) -> None:
        await self.cog.open_menu(itx)

class ActionLauncherView(discord.ui.View):
    """A persistent 'Open Actions' button you can pin in channels."""
    def __init__(self, cog: "ActionMenu", *, timeout: Optional[float] = None):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.add_item(OpenActionsButton(cog))

    async def interaction_check(self, itx: Interaction) -> bool:
        return True

    async def on_error(self, itx: Interaction, error: Exception, item) -> None:
        log.exception("Launcher error: %r", error)
        try:
            await itx.response.send_message("Something went wrong opening your action bar.", ephemeral=True)
        except Exception:
            pass


# ---------------------------
# UI: Main Action Menu
# ---------------------------

CATS = ("Move", "Interact", "Observe", "Social", "Inventory", "Profile", "Help")

class ActionMenuView(discord.ui.View):
    """Ephemeral, per-user action bar."""
    def __init__(self, cog: "ActionMenu", user_id: int, channel_id: int, active_cat: str = "Move"):
        super().__init__(timeout=180)
        self.cog = cog
        self.user_id = user_id
        self.channel_id = channel_id
        self.active_cat = active_cat
        self._rebuild()

    def _rebuild(self):
        self.clear_items()
        for cat in CATS:
            style = discord.ButtonStyle.primary if cat == self.active_cat else discord.ButtonStyle.secondary
            self.add_item(CategoryButton(cat, style, self))

        if self.active_cat == "Move":
            self._add_move()
        elif self.active_cat == "Interact":
            self._add_interact()
        elif self.active_cat == "Observe":
            self._add_observe()
        elif self.active_cat == "Social":
            self._add_social()
        elif self.active_cat == "Inventory":
            self._add_inventory()
        elif self.active_cat == "Profile":
            self._add_profile()
        elif self.active_cat == "Help":
            self._add_help()

        self.add_item(CloseButton())

    def _add_move(self):
        has_vehicle = _has_vehicle(self.user_id)
        self.add_item(ActWalkButton(self.cog, steps=1))
        self.add_item(ActWalkButton(self.cog, steps=2, label="Walk 2"))
        self.add_item(ActVehicleHopButton(self.cog, steps=3, disabled=not has_vehicle))
        self.add_item(ActVehicleHopButton(self.cog, steps=5, label="Hop x5", disabled=not has_vehicle))

    def _add_interact(self):
        nearby = _nearby_people(self.cog.bot, self.user_id)
        if nearby:
            self.add_item(TargetSelect(nearby, self.cog))
        else:
            btn = discord.ui.Button(label="No one nearby (yet)", style=discord.ButtonStyle.secondary, disabled=True)
            self.add_item(btn)

        self.add_item(SimpleActionButton(self.cog, "Search Area", "You search the immediate area… (stub)"))
        self.add_item(SimpleActionButton(self.cog, "Use Object", "You fiddle with the nearby object… (stub)"))
        self.add_item(SimpleActionButton(self.cog, "Trade Post", "Opening trade screen… (stub)"))

    def _add_observe(self):
        self.add_item(SimpleActionButton(self.cog, "Look Around", "You take a careful look around… (stub)"))
        self.add_item(SimpleActionButton(self.cog, "Listen", "You pause and listen for a moment… (stub)"))
        self.add_item(SimpleActionButton(self.cog, "Scan (quick)", "Quick scan ping… (stub)"))

    def _add_social(self):
        self.add_item(SimpleActionButton(self.cog, "Emote: 👋 Wave", "You wave. (stub)"))
        self.add_item(SimpleActionButton(self.cog, "Emote: 👍 Nod", "You nod. (stub)"))
        self.add_item(SimpleActionButton(self.cog, "Broadcast Hello", "You greet everyone nearby. (stub)"))

    def _add_inventory(self):
        self.add_item(SimpleActionButton(self.cog, "Open Inventory", "Opening your inventory… (stub)"))
        self.add_item(SimpleActionButton(self.cog, "Equip Last Item", "Equipping your last acquired item… (stub)"))
        self.add_item(SimpleActionButton(self.cog, "Use Medkit", "You use a medkit… (stub)"))

    def _add_profile(self):
        self.add_item(SimpleActionButton(self.cog, "My Status", "HP/Tags/Effects… (stub)"))
        self.add_item(SimpleActionButton(self.cog, "Skills", "Showing your skills… (stub)"))
        self.add_item(SimpleActionButton(self.cog, "Map", "Opening city map… (stub)"))

    def _add_help(self):
        self.add_item(SimpleActionButton(self.cog, "How this works", "Tap a category, then pick an action. (stub)"))
        self.add_item(SimpleActionButton(self.cog, "Tutorial", "Starting interactive tutorial… (stub)"))


class CategoryButton(discord.ui.Button):
    def __init__(self, cat: str, style: discord.ButtonStyle, view_ref: ActionMenuView):
        super().__init__(label=cat, style=style, custom_id=f"actions:cat:{cat}")
        self.cat = cat
        self.view_ref = view_ref

    async def callback(self, itx: Interaction) -> None:
        self.view_ref.active_cat = self.cat
        self.view_ref._rebuild()
        await itx.response.edit_message(view=self.view_ref, embed=self.view_ref.cog.build_embed(self.view_ref))


# ----- Generic action buttons -----

class SimpleActionButton(discord.ui.Button):
    def __init__(self, cog: "ActionMenu", label: str, reply: str):
        super().__init__(label=label, style=discord.ButtonStyle.secondary, custom_id=f"actions:do:{label}")
        self.cog = cog
        self.reply = reply

    async def callback(self, itx: Interaction) -> None:
        try:
            await itx.response.edit_message(content="(done)", embed=None, view=None)
        except Exception:
            if not itx.response.is_done():
                await itx.response.send_message(self.reply, ephemeral=True)
        try:
            await itx.followup.send(self.reply, ephemeral=True)
        except Exception:
            pass
        try:
            await self.cog.open_menu(itx)
        except Exception:
            pass


# ----- Move buttons -----

class ActWalkButton(discord.ui.Button):
    def __init__(self, cog: "ActionMenu", steps: int, label: Optional[str] = None):
        super().__init__(
            label=label or ("Walk" if steps == 1 else f"Walk {steps}"),
            style=discord.ButtonStyle.success,
            custom_id=f"actions:move:walk:{steps}"
        )
        self.cog = cog
        self.steps = steps

    async def callback(self, itx: Interaction) -> None:
        try:
            await itx.response.edit_message(content="(opening travel…)", embed=None, view=None)
        except Exception:
            pass
        await self.cog._start_walk_bridge(itx, self.steps)


class ActVehicleHopButton(discord.ui.Button):
    def __init__(self, cog: "ActionMenu", steps: int, label: Optional[str] = None, disabled: bool = False):
        super().__init__(
            label=label or f"Vehicle Hop x{steps}",
            style=discord.ButtonStyle.primary,
            custom_id=f"actions:move:veh:{steps}",
            disabled=disabled
        )
        self.cog = cog
        self.steps = steps

    async def callback(self, itx: Interaction) -> None:
        try:
            await itx.response.edit_message(content="(opening travel…)", embed=None, view=None)
        except Exception:
            pass
        await self.cog._start_walk_bridge(itx, self.steps)


# ----- Target select & per-target actions -----

class TargetSelect(discord.ui.Select):
    def __init__(self, targets: List[Dict], cog: "ActionMenu"):
        opts = []
        for i, t in enumerate(targets[:25], start=1):
            prefix = "🧍" if t.get("is_player") else "👤"
            name = str(t.get("label", "Unknown"))
            opts.append(discord.SelectOption(
                label=f"{name}",
                description="Player" if t.get("is_player") else "Citizen",
                emoji=prefix,
                value=f"{'u' if t.get('is_player') else 'n'}:{t.get('snowflake', 0)}:{i}"
            ))
        super().__init__(placeholder="Choose someone nearby…", min_values=1, max_values=1, options=opts, custom_id="actions:tgt:pick")
        self.cog = cog
        self.targets = targets

    async def callback(self, itx: Interaction) -> None:
        value = self.values[0]
        _kind, _snowflake, idx = value.split(":")
        idx = int(idx) - 1
        touched = self.targets[idx]
        await self.cog._open_target_actions(itx, touched)


class TargetActionsView(discord.ui.View):
    def __init__(self, cog: "ActionMenu", person: Dict):
        super().__init__(timeout=120)
        self.cog = cog
        self.person = person
        who = person.get("label", "Unknown")
        self.add_item(ViewProfileButton(person))
        self.add_item(SimpleActionButton(self.cog, f"Say hi to {who}", f"You greet **{who}**. (stub)"))
        self.add_item(SimpleActionButton(self.cog, f"Whisper to {who}", f"You whisper to **{who}**. (stub)"))
        self.add_item(SimpleActionButton(self.cog, f"Offer trade to {who}", f"You offer a trade to **{who}**. (stub)"))
        self.add_item(CloseButton())

class ViewProfileButton(discord.ui.Button):
    def __init__(self, person: Dict):
        super().__init__(label="View Profile", style=discord.ButtonStyle.secondary, custom_id="actions:tgt:view")
        self.person = person

    async def callback(self, itx: Interaction) -> None:
        p = self.person
        title = "Player Profile" if p.get("is_player") else "Citizen Profile"
        desc = f"**Name:** {discord.utils.escape_markdown(str(p.get('label','Unknown')))}\n"
        if p.get("is_player") and (pid := int(p.get("snowflake", 0))):
            desc += f"**Discord:** <@{pid}>\n"
        desc += "*Character sheet coming soon…*"
        embed = discord.Embed(title=title, description=desc)
        await itx.response.send_message(embed=embed, ephemeral=True)


class CloseButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Close", style=discord.ButtonStyle.danger, custom_id="actions:close")

    async def callback(self, itx: Interaction) -> None:
        await itx.response.edit_message(content="(closed)", embed=None, view=None)


# ---------------------------
# Cog
# ---------------------------

class ActionMenu(commands.Cog):
    """Global Action Bar system: category buttons + context actions."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def open_menu(self, itx: Interaction, cat: str = "Move"):
        view = ActionMenuView(self, itx.user.id, getattr(itx.channel, "id", 0), active_cat=cat)
        embed = self.build_embed(view)
        if not itx.response.is_done():
            await itx.response.send_message(embed=embed, view=view, ephemeral=True)
        else:
            await itx.followup.send(embed=embed, view=view, ephemeral=True)

    def build_embed(self, view: ActionMenuView) -> discord.Embed:
        titles = {
            "Move": "Move — travel the city",
            "Interact": "Interact — with people & objects",
            "Observe": "Observe — gather information",
            "Social": "Social — emotes & greetings",
            "Inventory": "Inventory — items & equipment",
            "Profile": "Profile — you & your stats",
            "Help": "Help — tips & tutorial",
        }
        e = discord.Embed(title=f"🎮 Action Bar: {titles.get(view.active_cat, view.active_cat)}")
        nearby = _nearby_people(self.bot, view.user_id)
        if nearby:
            names = ", ".join(str(t.get("label")) for t in nearby[:5])
            e.description = f"Nearby: {names}" + ("…" if len(nearby) > 5 else "")
        else:
            e.description = "Nearby: (no one yet)"
        e.set_footer(text="Tap a category, then pick an action. No typing needed.")
        return e

    async def _start_walk_bridge(self, itx: Interaction, steps: int):
        tcog = _travel_cog(self.bot)
        if tcog and hasattr(tcog, "_start_walk"):
            await tcog._start_walk(itx, steps)  # type: ignore
        else:
            if not itx.response.is_done():
                await itx.response.send_message("Travel system not loaded.", ephemeral=True)
            else:
                await itx.followup.send("Travel system not loaded.", ephemeral=True)

    async def _open_target_actions(self, itx: Interaction, person: Dict):
        embed = discord.Embed(
            title=f"Target: {person.get('label','Unknown')}",
            description="Choose what you want to do:",
        )
        view = TargetActionsView(self, person)
        await itx.response.edit_message(embed=embed, view=view)

    # ===== Slash commands =====

    @app_commands.command(name="actions", description="Open your action bar.")
    async def actions_open(self, itx: Interaction):
        await self.open_menu(itx)

    @app_commands.command(name="actions_deploy", description="(Admin) Drop an 'Open Actions' launcher here or across this category.")
    @app_commands.describe(scope="Where to deploy the launcher message", pin="Pin the launcher messages after sending?")
    @app_commands.choices(scope=[
        app_commands.Choice(name="Here (this channel)", value="here"),
        app_commands.Choice(name="This category (all text channels)", value="category"),
    ])
    @commands.has_permissions(manage_guild=True)
    async def actions_deploy(self, itx: Interaction, scope: app_commands.Choice[str], pin: bool = True):
        await itx.response.defer(ephemeral=True, thinking=True)

        launcher = ActionLauncherView(self, timeout=None)  # persistent view
        sent = []

        async def _send_in(ch: discord.TextChannel):
            msg = await ch.send("🎮 **Player Controls** — click to open your Action Bar.", view=launcher)
            if pin:
                try:
                    await msg.pin()
                except Exception:
                    pass
            sent.append(f"{ch.mention}")

        if scope.value == "here":
            if isinstance(itx.channel, discord.TextChannel):
                await _send_in(itx.channel)
        else:
            if isinstance(itx.channel, discord.TextChannel) and itx.channel.category:
                for ch in sorted(itx.channel.category.text_channels, key=lambda c: (c.position, c.id)):
                    if ch.permissions_for(itx.guild.me).send_messages:
                        await _send_in(ch)

        await itx.followup.send(f"Deployed action launcher to: {', '.join(sent)}", ephemeral=True)

    @actions_deploy.error
    async def actions_deploy_error(self, itx: Interaction, error: Exception):
        await itx.response.send_message(f"Could not deploy: {error}", ephemeral=True)


async def setup(bot: commands.Bot):
    cog = ActionMenu(bot)
    await bot.add_cog(cog)
    bot.add_view(ActionLauncherView(cog, timeout=None))
