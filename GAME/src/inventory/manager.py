# GAME/src/inventory/manager.py
from __future__ import annotations
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Iterable, Optional

from src.models.item import Item
from src.db.users_dal import ensure_user  # (kept for future use / consistency)

DB_PATH = Path("var/db/lowlife.sqlite")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------- Catalog queries ----------

def list_item_names(prefix: str | None = None, limit: int = 25) -> list[str]:
    """Return up to `limit` names for autocomplete (case-insensitive, prefix match)."""
    sql = "SELECT name FROM items ORDER BY name LIMIT ?"
    params: Iterable[object] = (limit,)
    if prefix:
        sql = "SELECT name FROM items WHERE name LIKE ? ESCAPE '\\' COLLATE NOCASE ORDER BY name LIMIT ?"
        # Escape % and _ in prefix
        p = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        params = (p, limit)
    with sqlite3.connect(DB_PATH) as cx:
        cx.row_factory = sqlite3.Row
        return [r["name"] for r in cx.execute(sql, params).fetchall()]


def get_item_by_name(name: str) -> Optional[Item]:
    """Fetch an Item by name (case-insensitive)."""
    with sqlite3.connect(DB_PATH) as cx:
        cx.row_factory = sqlite3.Row
        r = cx.execute(
            "SELECT * FROM items WHERE name = ? COLLATE NOCASE LIMIT 1",
            (name,),
        ).fetchone()
        if not r:
            return None
        # Build Item dataclass from row
        return Item(
            id=int(r["id"]),
            name=str(r["name"]),
            item_class=r["item_class"],
            created_at=datetime.fromisoformat(r["created_at"]) if r["created_at"] else datetime.now(timezone.utc),
            bind_on_pickup=bool(r["bind_on_pickup"]),
            durability=int(r["durability"]),
            pitch_value=int(r["pitch_value"]),
            rune_value=int(r["rune_value"]),
            scrap_value=int(r["scrap_value"]),
            hidden_trait=str(r["hidden_trait"]) if r["hidden_trait"] is not None else "",
            mint_index=int(r["mint_index"]),
        )


def _next_item_id(cx: sqlite3.Connection) -> int:
    r = cx.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM items").fetchone()
    return int(r[0]) if r and r[0] is not None else 1


def create_item(item: Item) -> int:
    """Insert a new catalog item. If item.id is falsy, we allocate one. Returns item id."""
    with sqlite3.connect(DB_PATH) as cx:
        cx.row_factory = sqlite3.Row
        # Ensure name is not already taken (case-insensitive)
        dup = cx.execute("SELECT 1 FROM items WHERE name = ? COLLATE NOCASE", (item.name,)).fetchone()
        if dup:
            raise ValueError(f"Item with name '{item.name}' already exists.")
        iid = int(item.id) if getattr(item, "id", None) else _next_item_id(cx)
        cx.execute(
            """
            INSERT INTO items
                (id, name, item_class, created_at, bind_on_pickup, durability,
                 pitch_value, rune_value, scrap_value, hidden_trait, mint_index)
            VALUES
                (:id, :name, :item_class, :created_at, :bind_on_pickup, :durability,
                 :pitch_value, :rune_value, :scrap_value, :hidden_trait, :mint_index)
            """,
            {
                **asdict(item),
                "id": iid,
                "item_class": item.item_class.value if hasattr(item.item_class, "value") else item.item_class,
                "created_at": item.created_at.isoformat(),
                "bind_on_pickup": 1 if item.bind_on_pickup else 0,
            },
        )
        cx.commit()
        return iid


def update_item(item: Item) -> None:
    """Update an existing catalog item by id."""
    with sqlite3.connect(DB_PATH) as cx:
        cx.execute(
            """
            UPDATE items
            SET name=:name,
                item_class=:item_class,
                bind_on_pickup=:bind_on_pickup,
                durability=:durability,
                pitch_value=:pitch_value,
                rune_value=:rune_value,
                scrap_value=:scrap_value,
                hidden_trait=:hidden_trait,
                mint_index=:mint_index
            WHERE id=:id
            """,
            {
                **asdict(item),
                "item_class": item.item_class.value if hasattr(item.item_class, "value") else item.item_class,
                "bind_on_pickup": 1 if item.bind_on_pickup else 0,
            },
        )
        cx.commit()


# ---------- Inventory ops ----------

def grant_item(user_id: int, item: Item, qty: int = 1, equipped: bool = False) -> int:
    """
    Grant an existing catalog item to a user.
    Will NOT create new catalog entries. If item.id doesn't exist, raises LookupError.
    """
    with sqlite3.connect(DB_PATH) as cx:
        cur = cx.cursor()

        # verify catalog id exists
        row = cur.execute("SELECT 1 FROM items WHERE id = ?", (item.id,)).fetchone()
        if row is None:
            raise LookupError(f"Catalog item id {item.id} not found. Use /item_add first.")

        cur.execute(
            """
            INSERT INTO inventory (user_id, item_id, qty, equipped, acquired_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, item.id, qty, 1 if equipped else 0, _now_iso()),
        )
        inv_id = cur.lastrowid
        cx.commit()
        return int(inv_id)


def set_equipped(inv_entry_id: int, equipped: bool) -> None:
    with sqlite3.connect(DB_PATH) as cx:
        cx.execute("UPDATE inventory SET equipped = ? WHERE id = ?", (1 if equipped else 0, inv_entry_id))
        cx.commit()


def inventory_for_user(user_id: int) -> list[dict]:
    with sqlite3.connect(DB_PATH) as cx:
        cx.row_factory = sqlite3.Row
        cur = cx.cursor()
        cur.execute(
            """
            SELECT i.id as inv_id, i.qty, i.equipped,
                   it.name, it.item_class, it.durability,
                   it.pitch_value, it.rune_value, it.scrap_value
            FROM inventory i
            JOIN items it ON it.id = i.item_id
            WHERE i.user_id = ?
            ORDER BY i.id DESC
            """,
            (user_id,),
        )
        return [dict(r) for r in cur.fetchall()]
