from __future__ import annotations
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import logging
import sqlite3

from src.models.item import Item
from src.db.users_dal import ensure_user

log = logging.getLogger(__name__)

# Anchor to .../GAME/var/db/lowlife.sqlite regardless of cwd
BASE_DIR = Path(__file__).resolve().parents[2]  # .../GAME
DB_PATH = BASE_DIR / "var" / "db" / "lowlife.sqlite"

def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    cx = sqlite3.connect(DB_PATH)
    cx.execute("PRAGMA foreign_keys = ON")
    return cx

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def grant_item(user_id: int, item: Item, qty: int = 1, equipped: bool = False) -> int:
    """user_id is a Discord ID; map to internal users.id first."""
    internal_id = ensure_user(user_id)

    data = asdict(item).copy()
    data.update(
        {
            "item_class": getattr(item.item_class, "value", str(item.item_class)),
            "created_at": item.created_at.isoformat(),
            "bind_on_pickup": 1 if item.bind_on_pickup else 0,
        }
    )

    with _connect() as cx:
        cur = cx.cursor()
        try:
            # upsert item catalog entry
            cur.execute("SELECT 1 FROM items WHERE id = ?", (item.id,))
            if cur.fetchone() is None:
                cur.execute(
                    """
                    INSERT INTO items (
                        id, name, item_class, created_at, bind_on_pickup, durability,
                        pitch_value, rune_value, scrap_value, hidden_trait, mint_index
                    )
                    VALUES (
                        :id, :name, :item_class, :created_at, :bind_on_pickup, :durability,
                        :pitch_value, :rune_value, :scrap_value, :hidden_trait, :mint_index
                    )
                    """,
                    data,
                )

            # inventory row
            cur.execute(
                """
                INSERT INTO inventory (user_id, item_id, qty, equipped, acquired_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (internal_id, item.id, qty, 1 if equipped else 0, _now_iso()),
            )
            inv_id = int(cur.lastrowid)
            cx.commit()
            log.info("grant_item OK user_internal=%s item=%s inv_id=%s", internal_id, item.id, inv_id)
            return inv_id

        except sqlite3.Error as e:
            cx.rollback()
            log.exception("grant_item failed (user_internal=%s, item=%s): %s", internal_id, item.id, e)
            raise

def set_equipped(inv_entry_id: int, equipped: bool) -> None:
    with _connect() as cx:
        cx.execute("UPDATE inventory SET equipped = ? WHERE id = ?", (1 if equipped else 0, inv_entry_id))
        cx.commit()

def inventory_for_user(user_id: int) -> list[dict]:
    internal_id = ensure_user(user_id)
    with _connect() as cx:
        cx.row_factory = sqlite3.Row
        cur = cx.cursor()
        cur.execute(
            """
            SELECT
                i.id AS inv_id,
                i.qty,
                i.equipped,
                it.name,
                it.item_class,
                it.durability,
                it.pitch_value,
                it.rune_value,
                it.scrap_value
            FROM inventory i
            JOIN items it ON it.id = i.item_id
            WHERE i.user_id = ?
            ORDER BY i.id DESC
            """,
            (internal_id,),
        )
        return [dict(r) for r in cur.fetchall()]
