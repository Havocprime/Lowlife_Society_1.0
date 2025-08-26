from __future__ import annotations
import sqlite3, datetime as dt, json
from typing import Optional
from pathlib import Path
from src.core.settings import SETTINGS

def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(SETTINGS.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

# --- Players & Characters ---
def upsert_player(discord_id: str, username: str | None, joined_ts: str | None=None) -> int:
    with _conn() as c:
        r = c.execute("SELECT id FROM players WHERE discord_id=?", (discord_id,)).fetchone()
        if r:
            c.execute("UPDATE players SET username=?, last_seen_at=? WHERE id=?",
                      (username, dt.datetime.utcnow().isoformat()+"Z", r["id"]))
            return r["id"]
        cur = c.execute("INSERT INTO players(discord_id, username, joined_at, last_seen_at) VALUES(?,?,?,?)",
                        (discord_id, username, joined_ts or dt.datetime.utcnow().isoformat()+"Z",
                         dt.datetime.utcnow().isoformat()+"Z"))
        return cur.lastrowid

def create_character(player_id: int, codename: str, faction: str | None=None) -> int:
    with _conn() as c:
        cur = c.execute("INSERT INTO characters(player_id, codename, faction, created_at) VALUES(?,?,?,?)",
                        (player_id, codename, faction, dt.datetime.utcnow().isoformat()+"Z"))
        cid = cur.lastrowid
        c.execute("INSERT INTO profiles(character_id) VALUES(?)", (cid,))
        return cid

def get_player_by_discord(discord_id: str) -> Optional[sqlite3.Row]:
    with _conn() as c:
        return c.execute("SELECT * FROM players WHERE discord_id=?", (discord_id,)).fetchone()

def get_characters(player_id: int) -> list[sqlite3.Row]:
    with _conn() as c:
        return c.execute("SELECT * FROM characters WHERE player_id=?", (player_id,)).fetchall()

# --- Wallet & Transactions ---
def ensure_wallet(owner_type: str, owner_id: int):
    with _conn() as c:
        r = c.execute("SELECT id FROM wallets WHERE owner_type=? AND owner_id=?",
                      (owner_type, owner_id)).fetchone()
        if not r:
            c.execute("INSERT INTO wallets(owner_type, owner_id, balance) VALUES(?,?,0)",
                      (owner_type, owner_id))

def get_balance(owner_type: str, owner_id: int) -> int:
    with _conn() as c:
        r = c.execute("SELECT balance FROM wallets WHERE owner_type=? AND owner_id=?",
                      (owner_type, owner_id)).fetchone()
        return int(r["balance"]) if r else 0

def tx_credit(owner_type: str, owner_id: int, amount: int, reason: str="", idem: str|None=None, meta: dict|None=None):
    assert amount >= 0
    _txn(owner_type, owner_id, amount, reason, idem, meta)

def tx_debit(owner_type: str, owner_id: int, amount: int, reason: str="", idem: str|None=None, meta: dict|None=None):
    assert amount >= 0
    _txn(owner_type, owner_id, -amount, reason, idem, meta)

def _txn(owner_type: str, owner_id: int, delta: int, reason: str, idem: str|None, meta: dict|None):
    with _conn() as c:
        if idem:
            r = c.execute("SELECT id FROM transactions WHERE idempotency_key=?", (idem,)).fetchone()
            if r: return  # idempotent
        ensure_wallet(owner_type, owner_id)
        c.execute("UPDATE wallets SET balance = balance + ? WHERE owner_type=? AND owner_id=?",
                  (delta, owner_type, owner_id))
        c.execute("""INSERT INTO transactions(owner_type, owner_id, amount, reason, idempotency_key, meta_json, created_at)
                    VALUES(?,?,?,?,?,?,?)""",
                  (owner_type, owner_id, delta, reason, idem, json.dumps(meta or {}),
                   dt.datetime.utcnow().isoformat()+"Z"))

# --- Inventory ---
def grant_item(character_id: int, item_def_id: int, qty: int=1, meta: dict|None=None):
    with _conn() as c:
        r = c.execute("""SELECT id, qty FROM inventory WHERE character_id=? AND item_def_id=? AND IFNULL(meta_json,'{}')=?""",
                      (character_id, item_def_id, json.dumps(meta or {}))).fetchone()
        if r:
            c.execute("UPDATE inventory SET qty = qty + ? WHERE id=?", (qty, r["id"]))
        else:
            c.execute("INSERT INTO inventory(character_id, item_def_id, qty, meta_json) VALUES(?,?,?,?)",
                      (character_id, item_def_id, qty, json.dumps(meta or {})))

def list_inventory(character_id: int) -> list[sqlite3.Row]:
    with _conn() as c:
        return c.execute("""SELECT inv.id, inv.qty, d.name, d.rarity, d.class, d.tags
                            FROM inventory inv JOIN item_defs d ON d.id = inv.item_def_id
                            WHERE inv.character_id=?""", (character_id,)).fetchall()

# --- Events ---
def append_event(ev_type: str, actor_discord_id: str|None, subject: str|None, payload: dict|None):
    with _conn() as c:
        c.execute("""INSERT INTO events(type, actor_discord_id, subject, payload_json, created_at)
                     VALUES(?,?,?,?,?)""",
                  (ev_type, actor_discord_id, subject, json.dumps(payload or {}),
                   dt.datetime.utcnow().isoformat()+"Z"))
