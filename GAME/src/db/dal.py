# GAME/src/db/dal.py
from __future__ import annotations

import json
import sqlite3
import random
import string
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict

from src.models.player import Player
from src.models.character import Character
from src.db.conn import get_conn  # centralized DB connection


# =============================================================================
# Shared audit/events DB plumbing
# =============================================================================

# Reuse Custodian DB if available so everything lives together
try:
    from src.core.custodian import ledger  # type: ignore
    EVENTS_DB: Path = Path(getattr(ledger, "DB_PATH"))  # type: ignore[attr-defined]
except Exception:
    # fall back: GAME/data/audit.sqlite
    EVENTS_DB = Path(__file__).parents[2] / "data" / "audit.sqlite"


def ensure_events_schema() -> None:
    """Create/upgrade the events table and indexes."""
    EVENTS_DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(EVENTS_DB) as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS events(
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_utc      TEXT    NOT NULL,
                guild_id    INTEGER,
                channel_id  INTEGER,
                author_id   INTEGER,
                kind        TEXT    NOT NULL,
                content     TEXT,
                payload     TEXT
            );
            CREATE INDEX IF NOT EXISTS ix_events_guild_ts   ON events(guild_id, ts_utc);
            CREATE INDEX IF NOT EXISTS ix_events_author_ts  ON events(author_id, ts_utc);
            """
        )
        con.commit()


# --- CORE SCHEMA ENSURE (players, characters) -------------------------------
def ensure_core_schema() -> None:
    """Idempotently ensure core game tables exist."""
    with get_conn() as cx:
        cx.executescript(
            """
            CREATE TABLE IF NOT EXISTS players(
              id INTEGER PRIMARY KEY,
              discord_id TEXT NOT NULL UNIQUE,
              username TEXT,
              display_name TEXT,
              alias TEXT,
              onboarding_state TEXT DEFAULT 'NEW',
              created_at TEXT NOT NULL DEFAULT (datetime('now')),
              updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_players_discord_id ON players(discord_id);

            CREATE TABLE IF NOT EXISTS characters(
              id INTEGER PRIMARY KEY,
              user_id INTEGER NOT NULL,
              name TEXT NOT NULL,
              char_id TEXT NOT NULL UNIQUE,
              pronouns TEXT,
              background TEXT,
              starting_district TEXT,
              archetypes TEXT,
              str INTEGER NOT NULL DEFAULT 5,
              vit INTEGER NOT NULL DEFAULT 5,
              end INTEGER NOT NULL DEFAULT 5,
              agi INTEGER NOT NULL DEFAULT 5,
              dex INTEGER NOT NULL DEFAULT 5,
              wis INTEGER NOT NULL DEFAULT 5,
              intel INTEGER NOT NULL DEFAULT 5,
              cha INTEGER NOT NULL DEFAULT 5,
              luck INTEGER NOT NULL DEFAULT 5,
              hp INTEGER NOT NULL DEFAULT 60,
              created_at TEXT NOT NULL DEFAULT (datetime('now')),
              updated_at TEXT NOT NULL DEFAULT (datetime('now')),
              FOREIGN KEY(user_id) REFERENCES players(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_characters_user_id ON characters(user_id);
            """
        )


# =============================================================================
# Players / Characters
# =============================================================================

def _row_to_player(r) -> Player:
    # (id, discord_id, username, display_name, alias, onboarding_state, created_at, updated_at)
    return Player(*r)

def _row_to_character(r) -> Character:
    # (id, user_id, name, char_id, pronouns, background, starting_district, archetypes,
    #  created_at, updated_at, str, vit, end, agi, dex, wis, intel, cha, luck, hp)
    return Character(*r)


# ---------- players ----------
def get_or_create_player(discord_id: str, username: Optional[str], display_name: Optional[str]) -> Player:
    ensure_core_schema()
    with get_conn() as cx:
        cx.execute(
            """
            INSERT INTO players(discord_id, username, display_name)
            VALUES(?, ?, ?)
            ON CONFLICT(discord_id) DO UPDATE SET
                username=COALESCE(excluded.username, players.username),
                display_name=COALESCE(excluded.display_name, players.display_name)
            """,
            (discord_id, username, display_name),
        )
        row = cx.execute(
            "SELECT id, discord_id, username, display_name, alias, onboarding_state, created_at, updated_at "
            "FROM players WHERE discord_id=?",
            (discord_id,),
        ).fetchone()
        return _row_to_player(row)

def set_player_alias(discord_id: str, alias: str) -> None:
    with get_conn() as cx:
        cx.execute("UPDATE players SET alias=?, updated_at=datetime('now') WHERE discord_id=?", (alias, discord_id))

def set_onboarding_state(discord_id: str, state: str) -> None:
    with get_conn() as cx:
        cx.execute("UPDATE players SET onboarding_state=?, updated_at=datetime('now') WHERE discord_id=?", (state, discord_id))

def get_player_by_discord(discord_id: str) -> Optional[Player]:
    with get_conn() as cx:
        row = cx.execute(
            "SELECT id, discord_id, username, display_name, alias, onboarding_state, created_at, updated_at "
            "FROM players WHERE discord_id=?",
            (discord_id,),
        ).fetchone()
        return _row_to_player(row) if row else None


# ---------- characters ----------
def _rand_char_id(prefix: str = "LL-", n: int = 6) -> str:
    alphabet = string.ascii_uppercase + string.digits
    while True:
        code = prefix + "".join(random.choice(alphabet) for _ in range(n))
        with get_conn() as cx:
            exists = cx.execute("SELECT 1 FROM characters WHERE char_id=?", (code,)).fetchone()
        if not exists:
            return code

def _select_character_by_id(cx: sqlite3.Connection, char_id: int) -> Character:
    row = cx.execute(
        """
        SELECT
          id, user_id, name, char_id, pronouns, background, starting_district, archetypes,
          created_at, updated_at,
          str, vit, end, agi, dex, wis, intel, cha, luck, hp
        FROM characters
        WHERE id=?
        """,
        (char_id,),
    ).fetchone()
    return _row_to_character(row)

def create_character_for_user(
    user_id: int,
    name: str,
    pronouns: Optional[str] = None,
    starting_district: Optional[str] = None,
    archetypes_csv: Optional[str] = None,
    background: Optional[str] = None,
    base_stats: Optional[Dict[str, int]] = None,
) -> Character:
    ensure_core_schema()
    char_id = _rand_char_id()

    stats = {
        "str": 5, "vit": 5, "end": 5, "agi": 5, "dex": 5,
        "wis": 5, "intel": 5, "cha": 5, "luck": 5, "hp": 60,
    }
    if base_stats:
        for k, v in base_stats.items():
            if k in stats:
                stats[k] = int(v)

    with get_conn() as cx:
        cx.execute(
            """
            INSERT INTO characters(
                user_id, name, char_id, pronouns, background, starting_district, archetypes,
                str, vit, end, agi, dex, wis, intel, cha, luck, hp
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id, name, char_id, pronouns, background, starting_district, archetypes_csv,
                stats["str"], stats["vit"], stats["end"], stats["agi"], stats["dex"],
                stats["wis"], stats["intel"], stats["cha"], stats["luck"], stats["hp"],
            ),
        )
        row = cx.execute(
            """
            SELECT
                id, user_id, name, char_id, pronouns, background, starting_district, archetypes,
                created_at, updated_at,
                str, vit, end, agi, dex, wis, intel, cha, luck, hp
            FROM characters
            WHERE char_id=?
            """,
            (char_id,),
        ).fetchone()
        return _row_to_character(row)

def upsert_character_for_user(
    user_id: int,
    *,
    name: str,
    pronouns: Optional[str],
    starting_district: Optional[str],
    archetypes_csv: Optional[str],
    background: Optional[str],
    base_stats: Optional[Dict[str, int]] = None,
) -> Character:
    """
    Update existing character for this user if one exists; otherwise create a new one.
    Returns the resulting Character row.
    """
    ensure_core_schema()
    with get_conn() as cx:
        found = cx.execute("SELECT id FROM characters WHERE user_id=? ORDER BY id ASC LIMIT 1", (user_id,)).fetchone()
        if found:
            stats_sql = ""
            params = []
            if base_stats:
                for k in ("str","vit","end","agi","dex","wis","intel","cha","luck","hp"):
                    if k in base_stats:
                        stats_sql += f", {k}=?"
                        params.append(int(base_stats[k]))
            cx.execute(
                f"""
                UPDATE characters
                SET name=?,
                    pronouns=?,
                    background=?,
                    starting_district=?,
                    archetypes=?,
                    updated_at=datetime('now')
                    {stats_sql}
                WHERE id=?
                """,
                [name, pronouns, background, starting_district, archetypes_csv, *params, int(found[0])],
            )
            return _select_character_by_id(cx, int(found[0]))
        else:
            # fall back to create
            return create_character_for_user(
                user_id=user_id,
                name=name,
                pronouns=pronouns,
                starting_district=starting_district,
                archetypes_csv=archetypes_csv,
                background=background,
                base_stats=base_stats,
            )

def get_primary_character_by_discord(discord_id: str) -> Optional[Character]:
    """
    Now returns the *most recently updated/created* character for this Discord user.
    This consolidates profile views when older placeholder rows exist.
    """
    with get_conn() as cx:
        row = cx.execute(
            """
            SELECT
                c.id, c.user_id, c.name, c.char_id, c.pronouns, c.background, c.starting_district, c.archetypes,
                c.created_at, c.updated_at,
                c.str, c.vit, c.end, c.agi, c.dex, c.wis, c.intel, c.cha, c.luck, c.hp
            FROM characters c
            JOIN players p ON p.id = c.user_id
            WHERE p.discord_id=?
            ORDER BY COALESCE(c.updated_at, c.created_at) DESC, c.id DESC
            LIMIT 1
            """,
            (discord_id,),
        ).fetchone()
        return _row_to_character(row) if row else None


# =============================================================================
# Events helpers
# =============================================================================

def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

def append_event(
    kind: str,
    author_id: int | str | None = None,
    channel_id: int | str | None = None,
    payload: dict | str | None = None,
    *,
    guild_id: int | str | None = None,
    content: str | None = None,
) -> None:
    """Insert one row into events."""
    ensure_events_schema()
    if isinstance(payload, dict):
        payload = json.dumps(payload, separators=(",", ":"))
    with sqlite3.connect(EVENTS_DB) as con:
        con.execute(
            """
            INSERT INTO events(ts_utc, guild_id, channel_id, author_id, kind, content, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _utc_iso(),
                int(guild_id) if guild_id is not None else None,
                int(channel_id) if channel_id is not None else None,
                int(author_id) if author_id is not None else None,
                kind,
                content,
                payload,
            ),
        )
        con.commit()


# ---------------- support for welcome cog ----------------
def ensure_npc_intro_table() -> None:
    """Table used by the welcome system to persist NPC intro cards."""
    EVENTS_DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(EVENTS_DB) as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS npc_intro(
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_utc      TEXT    NOT NULL,
                user_id     INTEGER NOT NULL,
                npc_name    TEXT    NOT NULL,
                content     TEXT    NOT NULL,
                image_url   TEXT,
                guild_id    INTEGER,
                channel_id  INTEGER
            );
            CREATE INDEX IF NOT EXISTS ix_npc_intro_user_ts ON npc_intro(user_id, ts_utc);
            """
        )
        con.commit()

def log_npc_intro(
    *,
    user_id: int | str,
    npc_name: str,
    content: str,
    image_url: str | None = None,
    guild_id: int | str | None = None,
    channel_id: int | str | None = None,
) -> None:
    """Record a welcome/intro card emission and mirror a lightweight event."""
    ensure_npc_intro_table()
    ts = _utc_iso()
    with sqlite3.connect(EVENTS_DB) as con:
        con.execute(
            """
            INSERT INTO npc_intro(ts_utc, user_id, npc_name, content, image_url, guild_id, channel_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts,
                int(user_id),
                npc_name,
                content,
                image_url,
                int(guild_id) if guild_id is not None else None,
                int(channel_id) if channel_id is not None else None,
            ),
        )
        con.commit()

    # also mirror into events for the unified timeline
    append_event(
        "welcome.intro",
        author_id=user_id,
        channel_id=channel_id,
        guild_id=guild_id,
        content=content[:400],
        payload={"npc": npc_name, "image_url": image_url},
    )
