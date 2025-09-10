# GAME/src/admin/custodian_cog.py
from __future__ import annotations

import os
import io
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

# Custodian ledger (verify_chain, etc.)
from src.core.custodian import ledger

ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID", "0") or "0")
GUILD_ID_ENV = int(os.getenv("GUILD_ID", "0") or "0")  # used for fast guild sync in setup()


def _is_admin_member(member: discord.Member) -> bool:
    if ADMIN_ROLE_ID and any(r.id == ADMIN_ROLE_ID for r in member.roles):
        return True
    return bool(member.guild_permissions.administrator)


def admin_check():
    async def predicate(inter: discord.Interaction) -> bool:
        user = inter.user
        if isinstance(user, discord.Member) and _is_admin_member(user):
            return True
        await inter.response.send_message("Nope.", ephemeral=True)
        return False
    return app_commands.check(predicate)


def _db_path() -> Path:
    # Prefer the path exposed by ledger if present; otherwise fall back.
    try:
        p = getattr(ledger, "DB_PATH", None)
        if p:
            return Path(p)
    except Exception:
        pass
    return Path(__file__).parents[2] / "db" / "audit.sqlite"


class CustodianCog(commands.Cog):
    """Admin tools for the Custodian (audit & security)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- Chain tools ----------
    @app_commands.command(name="audit_verify", description="Verify Custodian chain integrity (last N rows).")
    @app_commands.describe(limit="Rows to check (default 5000).")
    @admin_check()
    async def audit_verify(self, interaction: discord.Interaction, limit: int = 5000):
        await interaction.response.defer(ephemeral=True)
        try:
            result = ledger.verify_chain(limit=limit)
            broken = result.get("broken_ids", [])
            msg = f"Checked **{result.get('checked', 0)}** rows. Broken: **{len(broken)}**."
            if broken:
                msg += f"\nFirst few broken ids: {broken[:10]}"
            await interaction.followup.send(msg, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Verify failed: `{type(e).__name__}: {e}`", ephemeral=True)

    @app_commands.command(name="audit_export", description="Export recent audit rows as JSON.")
    @app_commands.describe(limit="Rows to export (default 1000).")
    @admin_check()
    async def audit_export(self, interaction: discord.Interaction, limit: int = 1000):
        await interaction.response.defer(ephemeral=True)
        dbp = _db_path()
        try:
            with sqlite3.connect(dbp) as conn:
                cols = [r[1] for r in conn.execute("PRAGMA table_info(audit_log)")]
                rows = conn.execute(
                    "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?",
                    (limit,)
                ).fetchall()
            data = [dict(zip(cols, r)) for r in rows]
            buf = io.BytesIO(json.dumps(data, indent=2).encode("utf-8"))
            await interaction.followup.send(file=discord.File(buf, filename="audit_export.json"), ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Export failed: `{type(e).__name__}: {e}` (DB: `{dbp}`)", ephemeral=True)

    # ---------- Freeze controls ----------
    def _ensure_freeze_table(self) -> None:
        dbp = _db_path()
        dbp.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(dbp) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS account_freeze(
                    user_id TEXT PRIMARY KEY,
                    ts_utc  TEXT NOT NULL,
                    reason  TEXT NOT NULL,
                    by_admin TEXT NOT NULL
                )
            """)
            conn.commit()

    @app_commands.command(name="freeze_user", description="Freeze a user (blocks all slash commands).")
    @app_commands.describe(user="User to freeze", reason="Why are you freezing them?")
    @admin_check()
    async def freeze_user(self, interaction: discord.Interaction, user: discord.Member, reason: str):
        await interaction.response.defer(ephemeral=True)
        try:
            self._ensure_freeze_table()
            dbp = _db_path()
            with sqlite3.connect(dbp) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO account_freeze(user_id, ts_utc, reason, by_admin) VALUES (?,?,?,?)",
                    (str(user.id), datetime.now(timezone.utc).isoformat(timespec="seconds"), reason, str(interaction.user.id))
                )
                conn.commit()
            await interaction.followup.send(f"âœ… Frozen <@{user.id}> â€” **{reason}**", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"âŒ Freeze failed: `{type(e).__name__}: {e}`", ephemeral=True)

    @app_commands.command(name="unfreeze_user", description="Remove a freeze from a user.")
    @app_commands.describe(user="User to unfreeze")
    @admin_check()
    async def unfreeze_user(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.response.defer(ephemeral=True)
        try:
            self._ensure_freeze_table()
            dbp = _db_path()
            with sqlite3.connect(dbp) as conn:
                conn.execute("DELETE FROM account_freeze WHERE user_id=?", (str(user.id),))
                conn.commit()
            await interaction.followup.send(f"âœ… Unfrozen <@{user.id}>", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"âŒ Unfreeze failed: `{type(e).__name__}: {e}`", ephemeral=True)

    @app_commands.command(name="freeze_status", description="Show if a user is frozen and why.")
    @app_commands.describe(user="User to check (defaults to you)")
    @admin_check()
    async def freeze_status(self, interaction: discord.Interaction, user: discord.Member | None = None):
        await interaction.response.defer(ephemeral=True)
        target = user or interaction.user  # type: ignore
        try:
            self._ensure_freeze_table()
            dbp = _db_path()
            with sqlite3.connect(dbp) as conn:
                row = conn.execute(
                    "SELECT ts_utc, reason, by_admin FROM account_freeze WHERE user_id=?",
                    (str(target.id),)
                ).fetchone()
            if row:
                ts, reason, by_admin = row
                await interaction.followup.send(
                    f"ðŸš« <@{target.id}> is **FROZEN** since `{ts}` â€” **{reason}** (by <@{by_admin}>).",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(f"âœ… <@{target.id}> is **not frozen**.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"âŒ Status check failed: `{type(e).__name__}: {e}`", ephemeral=True)

    # ---------- Evidence helpers ----------
    @app_commands.command(name="evidence_text", description="Store a text note as audit evidence.")
    @app_commands.describe(
        note="The note to store as evidence",
        context="Optional context/label (e.g. onboarding check, incident #, etc.)",
    )
    @admin_check()
    async def evidence_text(self, interaction: discord.Interaction, note: str, context: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        try:
            # Back-compat: still store a single text blob in the same place
            from src.core.custodian import evidence
            text = note if not context else f'note:"{note}" context:"{context}"'
            ref = evidence.save_text(text)
            await interaction.followup.send(
                f"ðŸ§¾ Evidence saved: id `{ref.id}` sha `{ref.sha256[:12]}â€¦`",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"âŒ Save failed: `{type(e).__name__}: {e}`", ephemeral=True)

    @app_commands.command(name="evidence_json", description="Store JSON key/value as audit evidence.")
    @app_commands.describe(json_payload='Example: {"case":"narwhal","status":"open"}')
    @admin_check()
    async def evidence_json(self, interaction: discord.Interaction, json_payload: str):
        await interaction.response.defer(ephemeral=True)
        try:
            import json as _json
            from src.core.custodian import evidence
            obj = _json.loads(json_payload)
            ref = evidence.save_json(obj)
            await interaction.followup.send(f"ðŸ§¾ Evidence saved: id `{ref.id}` sha `{ref.sha256[:12]}â€¦`", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"âŒ Save failed: `{type(e).__name__}: {e}`", ephemeral=True)

    @app_commands.command(
        name="evidence_message",
        description="Snapshot a message as evidence (optionally include first attachment)."
    )
    @app_commands.describe(
        channel="Channel of the message",
        message_id="The Discord message ID",
        include_attachment="Save first attachment bytes (<=8MB)"
    )
    @admin_check()
    async def evidence_message(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        message_id: str,
        include_attachment: bool = True,
    ):
        await interaction.response.defer(ephemeral=True)
        try:
            from src.core.custodian import evidence
            mid = int(message_id)
            msg = await channel.fetch_message(mid)

            snapshot = {
                "id": str(msg.id),
                "author_id": str(getattr(msg.author, "id", "")),
                "author": str(msg.author),
                "content": msg.content,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
                "edited_at": msg.edited_at.isoformat() if msg.edited_at else None,
                "channel_id": str(channel.id),
                "attachments": [a.to_dict() for a in msg.attachments] if msg.attachments else [],
                "jump_url": msg.jump_url,
            }
            ref = evidence.save_json(snapshot)

            # optionally stash first attachment bytes (<= 8MB)
            att_ref = None
            if include_attachment and msg.attachments:
                a0 = msg.attachments[0]
                if a0.size <= 8 * 1024 * 1024:
                    b = await a0.read()
                    att_ref = evidence.save_bytes(kind="bin", mime=a0.content_type, data=b)

            # Also log an audit row linking evidence (best-effort)
            try:
                from src.core.custodian import ledger as _ledger
                _ledger.log(
                    actor_id=str(interaction.user.id),
                    actor_type="admin",
                    action="admin.evidence_message",
                    context_json={"channel_id": str(channel.id), "message_id": str(mid)},
                    guild_id=str(interaction.guild_id) if interaction.guild_id else None,
                    channel_id=str(channel.id),
                    target_id=str(getattr(msg.author, "id", "")),
                    evidence_id=att_ref.id if att_ref else ref.id,
                    evidence_sha256=(att_ref.sha256 if att_ref else ref.sha256),
                )
            except Exception:
                pass

            text = f"ðŸ§¾ Message snapshot saved: id `{ref.id}` sha `{ref.sha256[:12]}â€¦`"
            if att_ref:
                text += f"\nðŸ“Ž Attachment saved: id `{att_ref.id}` sha `{att_ref.sha256[:12]}â€¦`"
            await interaction.followup.send(text, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"âŒ Snapshot failed: `{type(e).__name__}: {e}`", ephemeral=True)

    @app_commands.command(name="evidence_get", description="Download an evidence blob by id.")
    @app_commands.describe(evidence_id="ID returned by /evidence_*")
    @admin_check()
    async def evidence_get(self, interaction: discord.Interaction, evidence_id: int):
        await interaction.response.defer(ephemeral=True)
        dbp = _db_path()
        try:
            with sqlite3.connect(dbp) as conn:
                row = conn.execute(
                    "SELECT kind, mime, bytes, sha256 FROM audit_evidence WHERE id=?",
                    (evidence_id,)
                ).fetchone()

            if not row:
                await interaction.followup.send(f"Not found: evidence `{evidence_id}`", ephemeral=True)
                return

            kind, mime, data, sha = row
            ext = {
                "application/json": "json",
                "text/plain; charset=utf-8": "txt",
                "image/png": "png",
                "image/jpeg": "jpg",
            }.get(mime or "", "bin")
            filename = f"evidence_{evidence_id}_{(sha or '')[:8]}.{ext}"
            await interaction.followup.send(
                file=discord.File(io.BytesIO(data), filename=filename),
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"Download failed: `{type(e).__name__}: {e}`", ephemeral=True)

    # ---------- Flags inbox ----------
    def _ensure_flags_table(self) -> None:
        dbp = _db_path()
        dbp.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(dbp) as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS admin_flags(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ts_utc TEXT NOT NULL,
              subject_id TEXT NOT NULL,
              reason TEXT NOT NULL,
              severity INTEGER NOT NULL,
              opened_by TEXT NOT NULL,
              closed_ts_utc TEXT,
              closed_by TEXT
            );
            """)
            conn.commit()

    @app_commands.command(name="flags_list", description="List recent flags (open by default).")
    @app_commands.describe(
        user="Filter by user",
        include_closed="Include closed flags",
        limit="How many to list (max 50)"
    )
    @admin_check()
    async def flags_list(
        self,
        interaction: discord.Interaction,
        user: discord.Member | None = None,
        include_closed: bool = False,
        limit: app_commands.Range[int, 1, 50] = 20,
    ):
        await interaction.response.defer(ephemeral=True)
        self._ensure_flags_table()
        dbp = _db_path()
        try:
            q = "SELECT id, ts_utc, subject_id, reason, severity, opened_by, closed_ts_utc FROM admin_flags"
            where = []
            args: list[object] = []
            if user:
                where.append("subject_id = ?")
                args.append(str(user.id))
            if not include_closed:
                where.append("closed_ts_utc IS NULL")
            if where:
                q += " WHERE " + " AND ".join(where)
            q += " ORDER BY id DESC LIMIT ?"
            args.append(int(limit))
            with sqlite3.connect(dbp) as conn:
                rows = conn.execute(q, tuple(args)).fetchall()

            if not rows:
                await interaction.followup.send("_No flags._", ephemeral=True)
                return

            lines = []
            for rid, ts, sid, reason, sev, opened_by, closed_ts in rows:
                status = "OPEN" if not closed_ts else f"closed {closed_ts}"
                lines.append(
                    f"`#{rid}` â€¢ `{ts}` â€¢ <@{sid}> â€¢ sev {sev} â€¢ {status}\n{reason}"
                )
            desc = "\n\n".join(lines)[:4096]
            emb = discord.Embed(title="Admin Flags", description=desc, colour=discord.Color.orange())
            await interaction.followup.send(embed=emb, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"List failed: `{type(e).__name__}: {e}`", ephemeral=True)

    @app_commands.command(name="flag_close", description="Close a flag by id.")
    @app_commands.describe(flag_id="ID from /flags_list", note="Optional note appended to reason")
    @admin_check()
    async def flag_close(self, interaction: discord.Interaction, flag_id: int, note: str | None = None):
        await interaction.response.defer(ephemeral=True)
        self._ensure_flags_table()
        dbp = _db_path()
        try:
            with sqlite3.connect(dbp) as conn:
                if note:
                    # append a closure note to the reason for traceability
                    conn.execute(
                        "UPDATE admin_flags SET reason = reason || ' | closed-note: ' || ?, "
                        "closed_ts_utc=?, closed_by=? WHERE id=? AND closed_ts_utc IS NULL",
                        (note, datetime.now(timezone.utc).isoformat(timespec="seconds"), str(interaction.user.id), flag_id)
                    )
                else:
                    conn.execute(
                        "UPDATE admin_flags SET closed_ts_utc=?, closed_by=? WHERE id=? AND closed_ts_utc IS NULL",
                        (datetime.now(timezone.utc).isoformat(timespec="seconds"), str(interaction.user.id), flag_id)
                    )
                conn.commit()
                changed = conn.total_changes
            if changed:
                await interaction.followup.send(f"âœ… Closed flag `#{flag_id}`", ephemeral=True)
            else:
                await interaction.followup.send(f"Nothing changed (flag may not exist or is already closed).", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Close failed: `{type(e).__name__}: {e}`", ephemeral=True)


# ---------- Module-level command to avoid cog parser hiccups ----------
@app_commands.command(
    name="audit_verify_full",
    description="Verify the entire audit chain in streaming batches."
)
@app_commands.describe(batch_size="Rows per batch (default 20000)")
@admin_check()
async def audit_verify_full(interaction: discord.Interaction, batch_size: int = 20000):
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        from src.core.custodian import ledger as _ledger
        res = _ledger.verify_chain_full(batch_size=batch_size)
        broken = res.get("broken_ids", [])
        msg = f"Scanned **{res.get('checked', 0)}** rows â€¢ Broken: **{len(broken)}**"
        if broken:
            msg += f"\nFirst few broken ids: {broken[:10]}"
        await interaction.followup.send(msg, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(
            f"Verify full failed: `{type(e).__name__}: {e}`",
            ephemeral=True
        )


# ---- REQUIRED extension entry point ----
async def setup(bot: commands.Bot):
    await bot.add_cog(CustodianCog(bot))

    # also register the module-level slash command
    try:
        bot.tree.add_command(audit_verify_full)
    except Exception as e:
        if "already registered" not in str(e).lower():
            raise

    # FAST guild sync so new commands show up immediately in your server
    if GUILD_ID_ENV:
        try:
            gobj = discord.Object(id=GUILD_ID_ENV)
            # make sure module-level command is guild-registered too
            try:
                bot.tree.add_command(audit_verify_full, guild=gobj)
            except Exception:
                pass
            # copy all globals (from every cog) into the guild, then sync
            bot.tree.copy_global_to(guild=gobj)
            await bot.tree.sync(guild=gobj)
        except Exception:
            # best effort; you still have /sync command as a fallback
            pass
