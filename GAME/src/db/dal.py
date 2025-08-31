# GAME/src/db/dal.py
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path
from typing import Optional

from src.core.settings import SETTINGS
from src.core.ops import econ_frozen


# --- Resolve DB path and make sure its folder exists before opening ---
_DB_PATH = Path(str(SETTINGS.db_path)).expanduser().resolve()

def _ensure_dir() -> None:
    # If GAME/data (or whatever parent) doesn't exist yet, create it.
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def _conn() -> sqlite3.Connection:
    """
    Centralized connection helper:
      - Ensures parent directory exists (prevents 'unable to open database file')
      - Sets row_factory for dict-like access
      - Enables foreign keys
      - Puts SQLite in WAL mode with NORMAL sync (good for bots)
    """
    _ensure_dir()
    conn = sqlite3.connect(str(_DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON;")
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
    except Exception:
        # Pragmas are best-effort; ignore if unavailable
        pass
    return conn


# ---------------------------
# Players & Characters
# ---------------------------
def upsert_player(discord_id: str, username: str | None, joined_ts: str | None = None) -> int:
    now = dt.datetime.utcnow().isoformat() + "Z"
    with _conn() as c:
        r = c.execute("SELECT id FROM players WHERE discord_id=?", (discord_id,)).fetchone()
        if r:
            c.execute(
                "UPDATE players SET username=?, last_seen_at=? WHERE id=?",
                (username, now, r["id"]),
            )
            return int(r["id"])
        cur = c.execute(
            "INSERT INTO players(discord_id, username, joined_at, last_seen_at) VALUES(?,?,?,?)",
            (discord_id, username, joined_ts or now, now),
        )
        return int(cur.lastrowid)


def create_character(player_id: int, codename: str, faction: str | None = None) -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO characters(player_id, codename, faction, created_at) VALUES(?,?,?,?)",
            (player_id, codename, faction, dt.datetime.utcnow().isoformat() + "Z"),
        )
        cid = int(cur.lastrowid)
        c.execute("INSERT INTO profiles(character_id) VALUES(?)", (cid,))
        return cid


def get_player_by_discord(discord_id: str) -> Optional[sqlite3.Row]:
    with _conn() as c:
        return c.execute("SELECT * FROM players WHERE discord_id=?", (discord_id,)).fetchone()


def get_characters(player_id: int) -> list[sqlite3.Row]:
    with _conn() as c:
        return c.execute("SELECT * FROM characters WHERE player_id=?", (player_id,)).fetchall()


# ---------------------------
# Item Defs
# ---------------------------
def get_itemdef_by_name(name: str):
    with _conn() as c:
        return c.execute("SELECT * FROM item_defs WHERE name=?", (name,)).fetchone()


def ensure_itemdef(
    name: str,
    *,
    rarity: str = "Common",
    klass: str = "Test",
    tags: str | None = None,
    meta: dict | None = None,
) -> int:
    with _conn() as c:
        r = c.execute("SELECT id FROM item_defs WHERE name=?", (name,)).fetchone()
        if r:
            return int(r["id"])
        cur = c.execute(
            "INSERT INTO item_defs(name, rarity, class, tags, meta_json) VALUES(?,?,?,?,?)",
            (name, rarity, klass, tags or "", json.dumps(meta or {})),
        )
        return int(cur.lastrowid)


# ---------------------------
# Wallet & Transactions
# ---------------------------
def ensure_wallet(owner_type: str, owner_id: int) -> None:
    with _conn() as c:
        r = c.execute(
            "SELECT id FROM wallets WHERE owner_type=? AND owner_id=?", (owner_type, owner_id)
        ).fetchone()
        if not r:
            c.execute(
                "INSERT INTO wallets(owner_type, owner_id, balance) VALUES(?,?,0)",
                (owner_type, owner_id),
            )


def get_balance(owner_type: str, owner_id: int) -> int:
    with _conn() as c:
        r = c.execute(
            "SELECT balance FROM wallets WHERE owner_type=? AND owner_id=?", (owner_type, owner_id)
        ).fetchone()
        return int(r["balance"]) if r else 0


def tx_credit(
    owner_type: str,
    owner_id: int,
    amount: int,
    *,
    reason: str = "",
    idem: str,  # required for safety
    meta: dict | None = None,
    allow_overdraft: bool = True,
) -> int | None:
    assert amount >= 0, "amount must be >= 0"
    return _txn(
        owner_type,
        owner_id,
        +amount,
        reason=reason,
        idem=idem,
        meta=meta,
        allow_overdraft=allow_overdraft,
    )


def tx_debit(
    owner_type: str,
    owner_id: int,
    amount: int,
    *,
    reason: str = "",
    idem: str,  # required for safety
    meta: dict | None = None,
    allow_overdraft: bool = False,
) -> int | None:
    assert amount >= 0, "amount must be >= 0"
    return _txn(
        owner_type,
        owner_id,
        -amount,
        reason=reason,
        idem=idem,
        meta=meta,
        allow_overdraft=allow_overdraft,
    )


def _txn(
    owner_type: str,
    owner_id: int,
    delta: int,
    *,
    reason: str,
    idem: str | None,
    meta: dict | None,
    allow_overdraft: bool,
) -> int | None:
    # Panic switch: block all econ writes when frozen
    if econ_frozen():
        raise RuntimeError("economy is temporarily frozen")

    if not idem or not str(idem).strip():
        raise ValueError("idempotency key (idem) is required")

    now = dt.datetime.utcnow().isoformat() + "Z"
    with _conn() as c:
        # Fast idempotency check
        r = c.execute("SELECT id FROM transactions WHERE idempotency_key=?", (idem,)).fetchone()
        if r:
            return None  # already applied

        # Ensure wallet exists (inline to keep atomicity on this connection)
        wr = c.execute(
            "SELECT balance FROM wallets WHERE owner_type=? AND owner_id=?", (owner_type, owner_id)
        ).fetchone()
        if not wr:
            c.execute(
                "INSERT INTO wallets(owner_type, owner_id, balance) VALUES(?,?,0)",
                (owner_type, owner_id),
            )
            current_balance = 0
        else:
            current_balance = int(wr["balance"])

        # Overdraft guard
        if delta < 0 and not allow_overdraft and (current_balance + delta) < 0:
            raise ValueError("insufficient funds")

        # Apply balance change
        c.execute(
            "UPDATE wallets SET balance = balance + ? WHERE owner_type=? AND owner_id=?",
            (delta, owner_type, owner_id),
        )

        # Record transaction
        cur = c.execute(
            """
            INSERT INTO transactions(owner_type, owner_id, amount, reason, idempotency_key, meta_json, created_at)
            VALUES(?,?,?,?,?,?,?)
            """,
            (owner_type, owner_id, delta, reason, idem, json.dumps(meta or {}), now),
        )
        return int(cur.lastrowid)


# ---------------------------
# Inventory
# ---------------------------
def grant_item(character_id: int, item_def_id: int, qty: int = 1, meta: dict | None = None) -> None:
    with _conn() as c:
        r = c.execute(
            """SELECT id, qty FROM inventory
               WHERE character_id=? AND item_def_id=? AND IFNULL(meta_json,'{}')=?""",
            (character_id, item_def_id, json.dumps(meta or {})),
        ).fetchone()
        if r:
            c.execute("UPDATE inventory SET qty = qty + ? WHERE id=?", (qty, r["id"]))
        else:
            c.execute(
                "INSERT INTO inventory(character_id, item_def_id, qty, meta_json) VALUES(?,?,?,?)",
                (character_id, item_def_id, qty, json.dumps(meta or {})),
            )


def list_inventory(character_id: int) -> list[sqlite3.Row]:
    with _conn() as c:
        return c.execute(
            """SELECT inv.id, inv.qty, d.name, d.rarity, d.class, d.tags
               FROM inventory inv
               JOIN item_defs d ON d.id = inv.item_def_id
               WHERE inv.character_id=?""",
            (character_id,),
        ).fetchall()


# ---------------------------
# Events
# ---------------------------
def append_event(
    ev_type: str, actor_discord_id: str | None, subject: str | None, payload: dict | None
) -> None:
    with _conn() as c:
        c.execute(
            """INSERT INTO events(type, actor_discord_id, subject, payload_json, created_at)
               VALUES(?,?,?,?,?)""",
            (
                ev_type,
                actor_discord_id,
                subject,
                json.dumps(payload or {}),
                dt.datetime.utcnow().isoformat() + "Z",
            ),
        )


# --- NPC intros log ---------------------------------------------------------

def ensure_npc_intro_table() -> None:
    with _conn() as c:
        c.execute("""
        CREATE TABLE IF NOT EXISTS npc_intros (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_utc        TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),

            guild_id      INTEGER,
            channel_id    INTEGER,
            message_id    INTEGER,
            member_id     INTEGER,

            npc_fullname  TEXT    NOT NULL,
            npc_gender    TEXT    NOT NULL,
            image_filename TEXT   NOT NULL,

            handoff_type  TEXT    NOT NULL,
            handoff_value TEXT    NOT NULL,   -- phone/code/locker/etc
            intro_text    TEXT    NOT NULL,
            extra_json    TEXT    NOT NULL DEFAULT '{}'
        );
        """)

async def log_npc_intro(
    *,
    guild_id: int | None,
    channel_id: int | None,
    message_id: int | None,
    member_id: int | None,
    npc_fullname: str,
    npc_gender: str,
    image_filename: str,
    handoff_type: str,
    handoff_value: str,
    intro_text: str,
    extra_json: dict | None = None,
) -> int:
    import json as _json
    with _conn() as c:
        cur = c.execute("""
            INSERT INTO npc_intros (
                guild_id, channel_id, message_id, member_id,
                npc_fullname, npc_gender, image_filename,
                handoff_type, handoff_value, intro_text, extra_json
            )
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            guild_id, channel_id, message_id, member_id,
            npc_fullname, npc_gender, image_filename,
            handoff_type, handoff_value, intro_text, _json.dumps(extra_json or {})
        ))
        return int(cur.lastrowid)


# --- NPC intros log ---------------------------------------------------------
# Lightweight table so we can recall what NPC greeted whom, with what hand-off.

def ensure_npc_intro_table() -> None:
    with _conn() as c:
        c.execute("""
        CREATE TABLE IF NOT EXISTS npc_intros (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_utc          TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
            guild_id        INTEGER,
            channel_id      INTEGER,
            message_id      INTEGER,
            member_id       INTEGER,

            npc_fullname    TEXT    NOT NULL,
            npc_gender      TEXT    NOT NULL,
            image_filename  TEXT    NOT NULL,

            handoff_type    TEXT    NOT NULL,
            handoff_value   TEXT    NOT NULL,   -- phone/code/locker/etc
            intro_text      TEXT    NOT NULL,
            extra_json      TEXT    NOT NULL DEFAULT '{}'
        );
        """)

async def log_npc_intro(
    *,
    guild_id: int | None,
    channel_id: int | None,
    message_id: int | None,
    member_id: int | None,
    npc_fullname: str,
    npc_gender: str,
    image_filename: str,
    handoff_type: str,
    handoff_value: str,
    intro_text: str,
    extra_json: dict | None = None,
) -> int:
    import json as _json
    with _conn() as c:
        cur = c.execute("""
            INSERT INTO npc_intros (
                guild_id, channel_id, message_id, member_id,
                npc_fullname, npc_gender, image_filename,
                handoff_type, handoff_value, intro_text, extra_json
            )
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            guild_id, channel_id, message_id, member_id,
            npc_fullname, npc_gender, image_filename,
            handoff_type, handoff_value, intro_text,
            _json.dumps(extra_json or {})
        ))
        return int(cur.lastrowid)
