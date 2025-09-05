# ======================================================================
# FILE: GAME/src/cogs/suggestions.py
# ======================================================================
from __future__ import annotations

import csv
import io
import os
import time
import logging
import difflib
from enum import Enum
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from src.core.settings import SETTINGS
from src.suggestions import dal

log = logging.getLogger("suggestions.cog")
PRIMARY_GUILD_ID = getattr(SETTINGS, "guild_id", None)

# ---------- Config ----------
REVIEW_CHANNEL_ID = int(os.getenv("SUGGESTIONS_REVIEW_CHANNEL_ID", "0")) or None
COOLDOWN_SECONDS = int(os.getenv("SUGGESTIONS_COOLDOWN_S", "60"))  # (3) cooldown
DUP_SIM_THRESHOLD = 0.80  # (6) duplicate hint threshold
CONSUMABLE_SUBCATS = {"food", "drink", "medical", "other"}  # NEW: subcategories for Consumables

# Control whether THIS cog runs tree.sync (default off; let src/admin/sync.py do it)
SYNC_FROM_SUGGESTIONS = os.getenv("SYNC_FROM_SUGGESTIONS", "0") == "1"

# ---------- Status Enum ----------
class TicketStatus(str, Enum):
    NEW = "NEW"
    ACCEPTED = "ACCEPTED"
    HESITANT = "HESITANT"
    DENIED = "DENIED"
    DENIED_SILENT = "DENIED_SILENT"
    DUPLICATE = "DUPLICATE"
    NEEDS_INFO = "NEEDS_INFO"
    SPAM = "SPAM"
    IN_PROGRESS = "IN_PROGRESS"
    BACKLOG = "BACKLOG"

# ---------- Helpers ----------
def _spam_score(txt: str) -> int:
    """Very small heuristic; escalate if you want."""
    t = txt.strip()
    score = 0
    if len(t) < 10:
        score += 1
    if any(proto in t.lower() for proto in ("http://", "https://")):
        score += 1
    if len(set(t)) <= 3:  # e.g., 'aaaaaa'
        score += 1
    if sum((hasattr(ch, "isemoji") and ch.isemoji()) for ch in t) > 10:
        score += 1  # best-effort
    return score

def _duplicate_hint(guild_id: int, content: str) -> tuple[Optional[int], float]:
    best_id, best_ratio = None, 0.0
    for tid, prev in dal.fetch_recent_for_duplicate_check(guild_id, 100):
        ratio = difflib.SequenceMatcher(None, content.lower(), prev.lower()).ratio()
        if ratio > best_ratio:
            best_ratio, best_id = ratio, tid
    return best_id, best_ratio

# ---------- Modal: Add Detail (5) ----------
class AddDetailModal(discord.ui.Modal):
    def __init__(self, parent_cog: "SuggestionsCog", ticket_id: int):
        super().__init__(title=f"Add details to Ticket #{ticket_id}")
        self.parent_cog = parent_cog
        self.ticket_id = ticket_id

        self.more = discord.ui.TextInput(
            label="More details",
            style=discord.TextStyle.paragraph,
            min_length=5,
            max_length=1500,
            placeholder="Add clarifications, examples, steps, etc.",
        )
        self.add_item(self.more)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        ok = dal.add_note(self.ticket_id, interaction.user.id, str(self.more.value).strip())
        if ok:
            await interaction.response.send_message(
                f"Added details to **#{self.ticket_id}**. Thanks!", ephemeral=True
            )
        else:
            await interaction.response.send_message("Ticket not found.", ephemeral=True)

class AddDetailView(discord.ui.View):
    def __init__(self, parent_cog: "SuggestionsCog", ticket_id: int):
        super().__init__(timeout=None)
        self.parent_cog = parent_cog
        self.ticket_id = ticket_id

    @discord.ui.button(
        label="Add more detail",
        style=discord.ButtonStyle.secondary,
        custom_id="lowlife:suggest:add_detail",
    )
    async def add_detail(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddDetailModal(self.parent_cog, self.ticket_id))

# ---------- Review Panel (2) ----------
class ReviewView(discord.ui.View):
    def __init__(self, parent_cog: "SuggestionsCog", ticket_id: int):
        super().__init__(timeout=None)
        self.parent_cog = parent_cog
        self.ticket_id = ticket_id

    def _is_staff(self, interaction: discord.Interaction) -> bool:
        m = interaction.user
        return isinstance(m, discord.Member) and (
            m.guild_permissions.manage_guild or m.guild_permissions.administrator
        )

    async def _apply(
        self, interaction: discord.Interaction, status: TicketStatus, reason: Optional[str] = None
    ):
        if not self._is_staff(interaction):
            await interaction.response.send_message("Nope.", ephemeral=True)
            return

        t = dal.get_ticket(self.ticket_id)
        if not t:
            await interaction.response.send_message("Ticket no longer exists.", ephemeral=True)
            return

        ok = dal.set_status(self.ticket_id, interaction.user.id, status.value, reason)
        if not ok:
            await interaction.response.send_message("Failed to update status.", ephemeral=True)
            return

        dm_text = None
        if status == TicketStatus.DENIED:
            dm_text = (
                f"Hey! Your Lowlife ticket **#{self.ticket_id}** wasn’t accepted this time.\n"
                f"Moderator note: {reason or '(none)'}"
            )
        elif status == TicketStatus.HESITANT:
            dm_text = (
                f"Thanks for your ticket **#{self.ticket_id}**. We need a bit more info.\n"
                f"Note: {reason or '(none)'}"
            )
        elif status == TicketStatus.ACCEPTED:
            dm_text = (
                f"Good news! Your Lowlife ticket **#{self.ticket_id}** was **accepted**.\n"
                f"Note: {reason or '(none)'}"
            )
        elif status == TicketStatus.DENIED_SILENT:
            dal.append_silent_log(self.ticket_id, t.user_id, t.content, interaction.user.id, reason)

        if dm_text:
            try:
                user = await interaction.client.fetch_user(t.user_id)
                await user.send(dm_text)
            except Exception:
                pass

        await interaction.response.send_message(
            f"Ticket #{self.ticket_id} → **{status.value}**", ephemeral=True
        )

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success, custom_id="lowlife:suggest:accept")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._apply(interaction, TicketStatus.ACCEPTED)

    @discord.ui.button(label="Hesitant", style=discord.ButtonStyle.primary, custom_id="lowlife:suggest:hesitant")
    async def hesitant(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._apply(interaction, TicketStatus.HESITANT, reason="Needs more detail/justification")

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.danger, custom_id="lowlife:suggest:deny")
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._apply(interaction, TicketStatus.DENIED)

    @discord.ui.button(
        label="Silent Deny", style=discord.ButtonStyle.secondary, custom_id="lowlife:suggest:deny_silent"
    )
    async def deny_silent(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._apply(interaction, TicketStatus.DENIED_SILENT)

# ---------- Submission Modal (1/3/4/5/6) ----------
class SuggestionModal(discord.ui.Modal):
    def __init__(self, parent_cog: "SuggestionsCog"):
        super().__init__(title="Submit a Ticket")
        self.parent_cog = parent_cog

        # (4) category selector via short input (stored inline, no DB change)
        self.kind = discord.ui.TextInput(
            label="Type (Suggestion/Bug/QoL/Balance/Consumables)",  # 45 chars total
            style=discord.TextStyle.short,
            min_length=3,
            max_length=20,
            placeholder="Suggestion",
            required=False,
        )
        # NEW: subcategory only used when Type is Consumables
        self.subkind = discord.ui.TextInput(
            label="Consumables (Food/Drink/Medical/Other)",  # shortened to ≤45 chars
            style=discord.TextStyle.short,
            min_length=0,
            max_length=12,
            placeholder="Leave blank unless Consumables",
            required=False,
        )
        self.body_input = discord.ui.TextInput(
            label="Suggestion / request / bug report",
            style=discord.TextStyle.paragraph,
            min_length=8,
            max_length=2000,
            placeholder="Be specific: what/why/impact; examples help.",
        )
        self.add_item(self.kind)
        self.add_item(self.subkind)   # NEW
        self.add_item(self.body_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        # (3) per-user cooldown (staff bypass)
        now = time.time()
        last = self.parent_cog._cooldowns.get(interaction.user.id, 0)
        remain = COOLDOWN_SECONDS - (now - last)
        is_staff = isinstance(interaction.user, discord.Member) and (
            interaction.user.guild_permissions.manage_guild or interaction.user.guild_permissions.administrator
        )
        if remain > 0 and not is_staff:
            await interaction.response.send_message(
                f"You're submitting too fast — try again in {int(remain)}s.", ephemeral=True
            )
            return
        if not is_staff:
            self.parent_cog._cooldowns[interaction.user.id] = now

        # Build content with (4) inline tag + (NEW) subcategory for Consumables
        raw_kind = (str(self.kind.value).strip() or "Suggestion").split()[0]
        k_norm = raw_kind.lower()
        body = str(self.body_input.value).strip()

        if k_norm in ("consumables", "consumable"):
            raw_sub = (self.subkind.value or "").strip().lower()
            sub = raw_sub if raw_sub in CONSUMABLE_SUBCATS else "other"
            content = f"[Consumables/{sub.capitalize()}] {body}"
        else:
            content = f"[{raw_kind}] {body}"

        # (6) duplicate hint
        dup_id, dup_ratio = _duplicate_hint(interaction.guild_id or 0, content)

        # (3) spam guard (simple)
        if _spam_score(content) >= 2:
            # still store, but mark SPAM directly
            t_id = dal.create_ticket(
                interaction.guild_id or 0,
                interaction.user.id,
                content,
                interaction.channel_id,
                interaction.message.id if interaction.message else None,
            )
            dal.set_status(t_id, interaction.user.id, TicketStatus.SPAM.value, "auto-flagged heuristic")
            await interaction.response.send_message("Received. (Flagged for review.)", ephemeral=True)
            return

        # Normal NEW ticket
        t_id = dal.create_ticket(
            guild_id=interaction.guild_id or 0,
            user_id=interaction.user.id,
            content=content,
            channel_id=interaction.channel_id,
            message_id=interaction.message.id if interaction.message else None,
        )

        # (2) staff relay + one-click review + duplicate hint
        if REVIEW_CHANNEL_ID and interaction.client.get_channel(REVIEW_CHANNEL_ID):
            ch = interaction.client.get_channel(REVIEW_CHANNEL_ID)
            embed = discord.Embed(
                title=f"New Ticket #{t_id}", description=content, color=discord.Color.blurple()
            )
            embed.add_field(name="Author", value=f"{interaction.user.mention} ({interaction.user.id})", inline=False)
            if dup_id and dup_ratio >= DUP_SIM_THRESHOLD:
                embed.add_field(
                    name="Possible Duplicate", value=f"Looks like **#{dup_id}** ({dup_ratio*100:.0f}%)", inline=False
                )
            msg = await ch.send(embed=embed, view=ReviewView(self.parent_cog, t_id))

            # optional: try a private thread for triage
            try:
                await ch.create_thread(name=f"ticket-#{t_id}", message=msg, auto_archive_duration=10080)
            except Exception:
                # permissions or plan may not allow private threads; buttons still work in-channel
                pass

        # (5) user receipt + "Add more detail" button
        try:
            user = await interaction.client.fetch_user(interaction.user.id)
            await user.send(
                f"Thanks! Your ticket **#{t_id}** has been received.\n"
                "You can add more detail at any time:",
                view=AddDetailView(self.parent_cog, t_id),
            )
        except Exception:
            pass

        await interaction.response.send_message(
            f"Thanks! Ticket **#{t_id}** received. Staff will review it soon.", ephemeral=True
        )

# ---------- Public Submit Button ----------
class TicketPanel(discord.ui.View):
    def __init__(self, parent_cog: "SuggestionsCog"):
        super().__init__(timeout=None)  # persistent view
        self.parent_cog = parent_cog

    @discord.ui.button(
        label="Submit a Ticket", style=discord.ButtonStyle.primary, custom_id="lowlife:suggestions:submit"
    )
    async def submit_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SuggestionModal(self.parent_cog))

# ---------- Cog ----------
class SuggestionsCog(commands.Cog):
    """Suggestions / Requests / Bug Reports module (fully standalone)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        dal.ensure_schema()
        self.bot.add_view(TicketPanel(self))
        self._cooldowns: dict[int, float] = {}  # (3) per-user cooldown map

    async def cog_load(self):
        """
        Previously this cog always synced app commands here, which can collide with other cogs.
        Now it only syncs if SYNC_FROM_SUGGESTIONS=1 and no other cog has synced yet.
        Prefer using src/admin/sync.py to own syncing.
        """
        if not SYNC_FROM_SUGGESTIONS:
            log.info("SuggestionsCog: skipping slash sync (SYNC_FROM_SUGGESTIONS=0).")
            return
        if getattr(self.bot, "_synced_once", False):
            log.info("SuggestionsCog: sync skipped (already synced elsewhere).")
            return
        try:
            if PRIMARY_GUILD_ID:
                guild_obj = discord.Object(id=int(PRIMARY_GUILD_ID))
                self.bot.tree.copy_global_to(guild=guild_obj)
                synced = await self.bot.tree.sync(guild=guild_obj)
                log.info("SuggestionsCog: synced %d commands to guild %s", len(synced), PRIMARY_GUILD_ID)
            else:
                synced = await self.bot.tree.sync()
                log.info("SuggestionsCog: globally synced %d commands", len(synced))
        except Exception as e:
            log.exception("SuggestionsCog: app command sync failed: %r", e)
        finally:
            self.bot._synced_once = True  # mark so other cogs skip

    # ====== USER-FACING ======
    @app_commands.command(name="tickets_panel", description="Post the Suggestions panel (Submit a Ticket button).")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def tickets_panel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Suggestions / Requests / Bug Reports",
            description=(
                "Have an idea or issue? Press the button below to open a submission form.\n\n"
                "• Be specific (what/why/impact)\n"
                "• Include context or examples\n"
                "• One idea per ticket helps reviewers\n"
                "• If your Type is **Consumables**, fill the subcategory (Food / Drink / Medical / Other)"
            ),
            color=discord.Color.yellow(),
        )
        await interaction.response.send_message(embed=embed, view=TicketPanel(self))

    # (1) User self-service: show own tickets
    @app_commands.command(name="myticket", description="Show your recent tickets and statuses.")
    async def myticket(self, interaction: discord.Interaction):
        rows = dal.list_tickets_by_user(interaction.guild_id or 0, interaction.user.id, limit=10, offset=0)
        if not rows:
            await interaction.response.send_message("You don’t have any tickets yet.", ephemeral=True)
            return
        lines = [
            f"**#{t.id}** [{t.status}] — {(t.content[:120] + '…') if len(t.content) > 120 else t.content}"
            for t in rows
        ]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    # ====== ADMIN: REVIEW & MANAGEMENT ======
    tickets = app_commands.Group(name="tickets", description="Admin tools for suggestion tickets")

    @tickets.command(name="list", description="List recent tickets (optionally by status).")
    @app_commands.describe(status="Filter by status", limit="How many to show (max 50)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def list_cmd(
        self,
        interaction: discord.Interaction,
        status: Optional[TicketStatus] = None,
        limit: app_commands.Range[int, 1, 50] = 15,
    ):
        rows = dal.list_tickets(interaction.guild_id or 0, status.value if status else None, limit=limit, offset=0)
        if not rows:
            await interaction.response.send_message("No tickets found.", ephemeral=True)
            return
        lines = []
        for t in rows:
            snippet = (t.content[:140] + "…") if len(t.content) > 140 else t.content
            lines.append(f"**#{t.id}** [{t.status}] by <@{t.user_id}> – {snippet}")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @tickets.command(name="view", description="View a ticket's full text.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def view_cmd(self, interaction: discord.Interaction, ticket_id: int):
        t = dal.get_ticket(ticket_id)
        if not t:
            await interaction.response.send_message(f"Ticket #{ticket_id} not found.", ephemeral=True)
            return
        embed = discord.Embed(title=f"Ticket #{t.id} [{t.status}]", description=t.content, color=discord.Color.blurple())
        embed.add_field(name="Author", value=f"<@{t.user_id}>", inline=True)

        # (6) duplicate hint on demand
        dup_id, dup_ratio = _duplicate_hint(interaction.guild_id or 0, t.content)
        if dup_id and dup_ratio >= DUP_SIM_THRESHOLD and dup_id != t.id:
            embed.add_field(
                name="Possible Duplicate", value=f"Looks like **#{dup_id}** ({dup_ratio*100:.0f}%)", inline=False
            )

        if t.decision_reason:
            embed.add_field(name="Decision Note", value=t.decision_reason, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @tickets.command(name="set_status", description="Update status and notify the submitter (if applicable).")
    @app_commands.describe(
        ticket_id="ID number of the ticket",
        status="New status to set",
        reason="Optional moderator note for the submitter / record",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_status_cmd(
        self,
        interaction: discord.Interaction,
        ticket_id: int,
        status: TicketStatus,
        reason: Optional[str] = None,
    ):
        t = dal.get_ticket(ticket_id)
        if not t:
            await interaction.response.send_message(f"Ticket #{ticket_id} not found.", ephemeral=True)
            return

        ok = dal.set_status(ticket_id, interaction.user.id, status.value, reason)
        if not ok:
            await interaction.response.send_message("Failed to update status.", ephemeral=True)
            return

        # DM/Log mirrors the ReviewView logic
        dm_text: Optional[str] = None
        if status == TicketStatus.DENIED:
            dm_text = (
                f"Hey! Your Lowlife ticket **#{ticket_id}** wasn’t accepted this time.\n"
                f"Moderator note: {reason or '(none)'}"
            )
        elif status == TicketStatus.HESITANT:
            dm_text = (
                f"Thanks for your ticket **#{ticket_id}**. We need a bit more info.\n"
                f"Note: {reason or '(none)'}"
            )
        elif status == TicketStatus.ACCEPTED:
            dm_text = (
                f"Good news! Your Lowlife ticket **#{ticket_id}** was **accepted**.\n"
                f"Note: {reason or '(none)'}"
            )
        elif status == TicketStatus.DENIED_SILENT:
            dal.append_silent_log(ticket_id, t.user_id, t.content, interaction.user.id, reason)

        if dm_text:
            try:
                user = await self.bot.fetch_user(t.user_id)
                await user.send(dm_text)
            except Exception:
                pass

        await interaction.response.send_message(f"Ticket #{ticket_id} → **{status.value}**", ephemeral=True)

    # NEW: /tickets search
    @tickets.command(name="search", description="Search tickets by text (admin).")
    @app_commands.describe(query="Text to search for", limit="How many to show (max 50)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def tickets_search(
        self,
        interaction: discord.Interaction,
        query: app_commands.Range[str, 2, 100],
        limit: app_commands.Range[int, 1, 50] = 15,
    ):
        rows = dal.search_tickets(interaction.guild_id or 0, query, limit=limit)
        if not rows:
            await interaction.response.send_message("No matches.", ephemeral=True)
            return
        out = []
        for t in rows:
            snippet = (t.content[:140] + "…") if len(t.content) > 140 else t.content
            out.append(f"**#{t.id}** [{t.status}] by <@{t.user_id}> — {snippet}")
        await interaction.response.send_message("\n".join(out), ephemeral=True)

    # NEW: /tickets note
    @tickets.command(name="note", description="Append a moderator note to a ticket.")
    @app_commands.describe(ticket_id="Ticket ID", note="Note to add")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def tickets_note(
        self,
        interaction: discord.Interaction,
        ticket_id: int,
        note: app_commands.Range[str, 3, 1000],
    ):
        ok = dal.add_note(ticket_id, interaction.user.id, note)
        if not ok:
            await interaction.response.send_message("Ticket not found.", ephemeral=True)
            return
        await interaction.response.send_message(f"Added note to **#{ticket_id}**.", ephemeral=True)

    @tickets.command(name="export", description="Export tickets to CSV (optionally filter by status).")
    @app_commands.describe(status="Filter by status")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def export_cmd(self, interaction: discord.Interaction, status: Optional[TicketStatus] = None):
        rows = list(dal.export_rows(interaction.guild_id or 0, status.value if status else None))
        if not rows:
            await interaction.response.send_message("No tickets to export.", ephemeral=True)
            return
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "id",
                "guild_id",
                "user_id",
                "channel_id",
                "message_id",
                "content",
                "status",
                "created_at",
                "updated_at",
                "decided_by",
                "decision_reason",
            ]
        )
        for r in rows:
            writer.writerow(
                [
                    r["id"],
                    r["guild_id"],
                    r["user_id"],
                    r["channel_id"],
                    r["message_id"],
                    r["content"],
                    r["status"],
                    r["created_at"],
                    r["updated_at"],
                    r["decided_by"],
                    r["decision_reason"],
                ]
            )
        data = io.BytesIO(buf.getvalue().encode("utf-8"))
        filename = f"suggestions_export_{(status.value if status else 'ALL').lower()}.csv"
        await interaction.response.send_message(file=discord.File(data, filename=filename), ephemeral=True)

    @tickets.command(name="stats", description="Show ticket counts by status.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def stats_cmd(self, interaction: discord.Interaction):
        stats = dal.stats_by_status(interaction.guild_id or 0)
        if not stats:
            await interaction.response.send_message("No tickets yet.", ephemeral=True)
            return
        lines = [f"**{k}**: {v}" for k, v in sorted(stats.items())]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(SuggestionsCog(bot))
