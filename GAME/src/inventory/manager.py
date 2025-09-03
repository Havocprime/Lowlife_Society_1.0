# GAME/src/inventory/manager.py
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Optional, Iterable

from src.models.item import Item, ItemClass
try:
    from src.db.db_path import DB_PATH  # shared path helper
except Exception:
    DB_PATH = Path("var/db/lowlife.sqlite")

# --------- helpers

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _col_exists(cx: sqlite3.Connection, table: str, col: str) -> bool:
    cur = cx.execute(f"PRAGMA table_info({table})")
    return any(r[1] == col for r in cur.fetchall())

def _items_has_deleted(cx: sqlite3.Connection) -> bool:
    return _col_exists(cx, "items", "deleted_at")

# --------- catalog CRUD

def create_item(item: Item) -> int:
    """Insert a new catalog item. Returns new id."""
    with sqlite3.connect(DB_PATH) as cx:
        cx.row_factory = sqlite3.Row
        # unique-by-name, prevent dupes
        cur = cx.execute("SELECT id FROM items WHERE LOWER(name)=LOWER(?)", (item.name,))
        if cur.fetchone():
            raise ValueError(f"Item with name '{item.name}' already exists")

        data = {
            **asdict(item),
            "item_class": item.item_class.value,  # enum -> string
            "created_at": item.created_at.isoformat(),
            # optional/catalog fields with safe defaults if missing in dataclass
            "category": getattr(item, "category", "misc"),
            "subcategory": getattr(item, "subcategory", ""),
            "stack_max": int(getattr(item, "stack_max", 1) or 1),
            "rarity": getattr(item, "rarity", "common"),
            "quality_float": float(getattr(item, "quality_float", 100.0) or 100.0),
            "bind_on_pickup": 1 if item.bind_on_pickup else 0,
        }

        cx.execute(
            """
            INSERT INTO items (
                id, name, item_class, created_at, bind_on_pickup, durability,
                pitch_value, rune_value, scrap_value, hidden_trait, mint_index,
                category, subcategory, stack_max, rarity, quality_float
            ) VALUES (
                :id, :name, :item_class, :created_at, :bind_on_pickup, :durability,
                :pitch_value, :rune_value, :scrap_value, :hidden_trait, :mint_index,
                :category, :subcategory, :stack_max, :rarity, :quality_float
            )
            """,
            data,
        )
        new_id = int(cx.execute("SELECT last_insert_rowid()").fetchone()[0])
        cx.commit()
        return new_id

def update_item(item: Item) -> None:
    with sqlite3.connect(DB_PATH) as cx:
        cx.execute(
            """
            UPDATE items
               SET name = ?,
                   item_class = ?,
                   bind_on_pickup = ?,
                   durability = ?,
                   pitch_value = ?,
                   rune_value = ?,
                   scrap_value = ?,
                   hidden_trait = ?,
                   mint_index = ?
             WHERE id = ?
            """,
            (
                item.name,
                item.item_class.value,
                1 if item.bind_on_pickup else 0,
                int(item.durability or 0),
                int(item.pitch_value or 0),
                int(item.rune_value or 0),
                int(item.scrap_value or 0),
                item.hidden_trait or "",
                int(item.mint_index or 0),
                int(item.id),
            ),
        )
        cx.commit()

def get_item_by_name(name: str) -> Optional[Item]:
    with sqlite3.connect(DB_PATH) as cx:
        cx.row_factory = sqlite3.Row
        has_deleted = _items_has_deleted(cx)
        where = "WHERE LOWER(name)=LOWER(?)"
        if has_deleted:
            where += " AND deleted_at IS NULL"
        row = cx.execute(f"SELECT * FROM items {where} LIMIT 1", (name,)).fetchone()
        if not row:
            return None
        # build minimal Item for grant (fields the dataclass expects)
        return Item(
            id=int(row["id"]),
            name=row["name"],
            item_class=ItemClass(row["item_class"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            bind_on_pickup=bool(row["bind_on_pickup"]),
            durability=int(row["durability"] or 0),
            pitch_value=int(row["pitch_value"] or 0),
            rune_value=int(row["rune_value"] or 0),
            scrap_value=int(row["scrap_value"] or 0),
            hidden_trait=row["hidden_trait"] or "",
            mint_index=int(row["mint_index"] or 0),
        )

def soft_delete_item_by_name(name: str) -> bool:
    with sqlite3.connect(DB_PATH) as cx:
        if not _items_has_deleted(cx):
            # column doesn't exist (older DB) – nothing to do
            return False
        cur = cx.execute(
            "UPDATE items SET deleted_at = ? WHERE LOWER(name)=LOWER(?) AND deleted_at IS NULL",
            (_now_iso(), name),
        )
        cx.commit()
        return cur.rowcount > 0

def list_item_names(prefix: str, limit: int = 25) -> list[str]:
    prefix = (prefix or "").lower()
    like = f"%{prefix}%"
    with sqlite3.connect(DB_PATH) as cx:
        cx.row_factory = sqlite3.Row
        has_deleted = _items_has_deleted(cx)
        sql = "SELECT DISTINCT name FROM items"
        where = " WHERE LOWER(name) LIKE ?"
        if has_deleted:
            where += " AND deleted_at IS NULL"
        sql += where + " ORDER BY name LIMIT ?"
        rows = cx.execute(sql, (like, limit)).fetchall()
        return [r["name"] for r in rows]

def catalog_items(
    q: str = "",
    rarity: Optional[str] = None,
    item_class: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> list[dict]:
    q = (q or "").strip().lower()
    like = f"%{q}%"
    offs = max(0, (int(page) - 1) * int(page_size))
    with sqlite3.connect(DB_PATH) as cx:
        cx.row_factory = sqlite3.Row
        has_deleted = _items_has_deleted(cx)
        where_parts: list[str] = []
        params: list = []

        if q:
            where_parts.append("LOWER(name) LIKE ?")
            params.append(like)
        if rarity:
            # tolerate DBs without rarity column
            if _col_exists(cx, "items", "rarity"):
                where_parts.append("LOWER(rarity)=LOWER(?)")
                params.append(rarity)
        if item_class:
            where_parts.append("LOWER(item_class)=LOWER(?)")
            params.append(item_class)
        if has_deleted:
            where_parts.append("deleted_at IS NULL")

        where = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
        sql = f"""
            SELECT id, name, item_class, rarity, stack_max
              FROM items
              {where}
             ORDER BY name
             LIMIT ? OFFSET ?
        """
        params.extend([int(page_size), int(offs)])
        rows = cx.execute(sql, tuple(params)).fetchall()
        return [dict(r) for r in rows]

# --------- inventory + grants

def grant_item(user_id: int, item: Item, qty: int = 1, equipped: bool = False) -> int:
    """Create catalog row if missing (by id), then add inventory entry."""
    with sqlite3.connect(DB_PATH) as cx:
        cur = cx.cursor()
        # Upsert catalog by id (if the caller built a new Item)
        cur.execute("SELECT id FROM items WHERE id = ?", (item.id,))
        if cur.fetchone() is None:
            cur.execute(
                """
                INSERT INTO items (
                    id, name, item_class, created_at, bind_on_pickup, durability,
                    pitch_value, rune_value, scrap_value, hidden_trait, mint_index
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.id,
                    item.name,
                    item.item_class.value,
                    item.created_at.isoformat(),
                    1 if item.bind_on_pickup else 0,
                    int(item.durability or 0),
                    int(item.pitch_value or 0),
                    int(item.rune_value or 0),
                    int(item.scrap_value or 0),
                    item.hidden_trait or "",
                    int(item.mint_index or 0),
                ),
            )
        # Inventory row
        cur.execute(
            """
            INSERT INTO inventory (user_id, item_id, qty, equipped, acquired_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (int(user_id), int(item.id), int(qty or 1), 1 if equipped else 0, _now_iso()),
        )
        inv_id = int(cur.lastrowid)
        cx.commit()
        return inv_id

def set_equipped(inv_entry_id: int, equipped: bool) -> None:
    with sqlite3.connect(DB_PATH) as cx:
        cx.execute(
            "UPDATE inventory SET equipped = ? WHERE id = ?",
            (1 if equipped else 0, int(inv_entry_id)),
        )
        cx.commit()

def inventory_for_user(user_id: int) -> list[dict]:
    with sqlite3.connect(DB_PATH) as cx:
        cx.row_factory = sqlite3.Row
        cur = cx.cursor()
        # Join onto items to expose class/rarity/stack_max for formatting
        cur.execute(
            """
            SELECT i.id AS inv_id, i.qty, i.equipped,
                   it.name, it.item_class,
                   COALESCE(it.stack_max, 1) AS stack_max,
                   COALESCE(it.rarity, 'common') AS rarity,
                   COALESCE(it.quality_float, 100.0) AS quality_float
              FROM inventory i
              JOIN items it ON it.id = i.item_id
             WHERE i.user_id = ?
             ORDER BY i.id DESC
            """,
            (int(user_id),),
        )
        return [dict(r) for r in cur.fetchall()]


def create_item(item: Item) -> int:
    with sqlite3.connect(DB_PATH) as cx:
        cur = cx.execute(
            """
            INSERT INTO items
              (name, item_class, created_at, bind_on_pickup, durability,
               pitch_value, rune_value, scrap_value, hidden_trait, mint_index,
               rarity, stack_max, equippable)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.name, item.item_class, item.created_at.isoformat(),
                int(item.bind_on_pickup), item.durability,
                item.pitch_value, item.rune_value, item.scrap_value,
                item.hidden_trait, item.mint_index,
                item.rarity, item.stack_max, int(item.equippable),
            ),
        )
        return cur.lastrowid

def update_item(item: Item) -> None:
    with sqlite3.connect(DB_PATH) as cx:
        cx.execute(
            """
            UPDATE items SET
              name=?,
              item_class=?,
              bind_on_pickup=?,
              durability=?,
              pitch_value=?,
              rune_value=?,
              scrap_value=?,
              hidden_trait=?,
              mint_index=?,
              rarity=?,
              stack_max=?,
              equippable=?         -- NEW
            WHERE id=?
            """,
            (
                item.name, item.item_class,
                int(item.bind_on_pickup), item.durability,
                item.pitch_value, item.rune_value, item.scrap_value,
                item.hidden_trait, item.mint_index,
                item.rarity, item.stack_max, int(item.equippable),  # NEW
                item.id,
            ),
        )

def catalog_items(q: str = "", rarity: Optional[str] = None,
                  item_class: Optional[str] = None,
                  equippable: Optional[bool] = None,
                  page: int = 1, page_size: int = 20):
    where = ["1=1"]
    args: list[Any] = []

    if q:
        where.append("name LIKE ?")
        args.append(f"%{q}%")
    if rarity:
        where.append("rarity = ?")
        args.append(rarity.lower())
    if item_class:
        where.append("item_class = ?")
        args.append(item_class.lower())
    if equippable is not None:
        where.append("equippable = ?")
        args.append(1 if equippable else 0)

    sql = f"""
      SELECT id, name, item_class, rarity, stack_max, equippable
      FROM items
      WHERE {" AND ".join(where)}
      ORDER BY id ASC            -- masterlist by creation/id
      LIMIT ? OFFSET ?
    """
    args.extend([page_size, (max(page,1)-1)*page_size])

    with sqlite3.connect(DB_PATH) as cx:
        cx.row_factory = sqlite3.Row
        return [dict(r) for r in cx.execute(sql, args)]

def set_equipped(inv_id: int, on: bool) -> None:
    with sqlite3.connect(DB_PATH) as cx:
        cx.row_factory = sqlite3.Row
        row = cx.execute(
            """SELECT i.equippable
               FROM inventory inv JOIN items i ON i.id = inv.item_id
               WHERE inv.id=?""",
            (inv_id,)
        ).fetchone()
        if not row:
            raise ValueError("Unknown inventory id")
        if on and int(row["equippable"]) == 0:
            raise ValueError("This item cannot be equipped.")
        cx.execute("UPDATE inventory SET equipped=? WHERE id=?", (1 if on else 0, inv_id))
