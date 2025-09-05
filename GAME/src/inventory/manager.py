from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Optional, Any, List, Dict

from src.models.item import Item, ItemClass

try:
    from src.db.db_path import DB_PATH
except Exception:
    DB_PATH = Path("var/db/lowlife.sqlite")


# ---------- helpers

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _norm(s: str) -> str:
    return " ".join(str(s or "").split()).strip()

def _col_exists(cx: sqlite3.Connection, table: str, col: str) -> bool:
    cur = cx.execute(f"PRAGMA table_info({table})")
    return any(r[1] == col for r in cur.fetchall())

def _items_has_deleted(cx: sqlite3.Connection) -> bool:
    return _col_exists(cx, "items", "deleted_at")

def _row_has(row: sqlite3.Row, key: str) -> bool:
    try:
        return key in row.keys()
    except Exception:
        return False

def _row_or(row: sqlite3.Row, key: str, default: Any) -> Any:
    return row[key] if _row_has(row, key) and row[key] is not None else default

def _ensure_unique_name(cx: sqlite3.Connection, name: str, exclude_id: Optional[int] = None) -> None:
    """Raise if an *active* item already uses this name (ignores soft-deleted rows)."""
    where = ["LOWER(name)=LOWER(?)"]
    params: list[Any] = [name]
    if _items_has_deleted(cx):
        where.append("deleted_at IS NULL")
    if exclude_id is not None:
        where.append("id <> ?")
        params.append(int(exclude_id))
    sql = f"SELECT 1 FROM items WHERE {' AND '.join(where)} LIMIT 1"
    cur = cx.execute(sql, tuple(params))
    if cur.fetchone():
        raise ValueError(f"Item with name '{name}' already exists")


# ---------- lookups / autocomplete ----------

def list_item_names(prefix: str, limit: int = 25, include_deleted: bool = False) -> List[str]:
    """
    Return up to `limit` item names matching `prefix` (case-insensitive).
    When `include_deleted` is False (default), soft-deleted rows are filtered out
    if the items.deleted_at column exists.
    """
    prefix = _norm(prefix).lower()
    like = f"%{prefix}%"

    with sqlite3.connect(DB_PATH) as cx:
        cx.row_factory = sqlite3.Row
        has_deleted = _items_has_deleted(cx)

        where_parts: list[str] = []
        params: list[Any] = []

        if prefix:
            where_parts.append("LOWER(name) LIKE ?")
            params.append(like)

        if has_deleted and not include_deleted:
            where_parts.append("deleted_at IS NULL")

        where = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
        sql = f"SELECT name FROM items{where} ORDER BY name ASC LIMIT ?"
        params.append(int(limit))
        rows = cx.execute(sql, tuple(params)).fetchall()
        return [r["name"] for r in rows]

def list_item_name_status(prefix: str, limit: int = 25) -> List[Dict[str, Any]]:
    """
    Like list_item_names, but always includes soft-deleted rows and returns
    [{'name': 'Bandage Roll', 'deleted': True}, ...] when items.deleted_at exists.
    """
    prefix = _norm(prefix).lower()
    like = f"%{prefix}%"

    with sqlite3.connect(DB_PATH) as cx:
        cx.row_factory = sqlite3.Row
        has_deleted = _items_has_deleted(cx)

        where = "WHERE LOWER(name) LIKE ?" if prefix else ""
        params: list[Any] = [like] if prefix else []
        select = "name, (deleted_at IS NOT NULL) AS deleted" if has_deleted else "name, 0 AS deleted"
        sql = f"SELECT {select} FROM items {where} ORDER BY name ASC LIMIT ?"
        params.append(int(limit))
        rows = cx.execute(sql, tuple(params)).fetchall()
        return [{"name": r["name"], "deleted": bool(r["deleted"])} for r in rows]


# ---------- soft delete / restore / purge ----------

def soft_delete_item_by_name(name: str) -> bool:
    """Soft-delete an item by name if the items.deleted_at column exists. Returns True if a row was updated."""
    with sqlite3.connect(DB_PATH) as cx:
        if not _items_has_deleted(cx):
            return False  # keep behavior: no soft-delete column -> do nothing

        cur = cx.execute(
            "UPDATE items SET deleted_at = ? "
            "WHERE LOWER(name)=LOWER(?) AND deleted_at IS NULL",
            (_now_iso(), _norm(name)),
        )
        cx.commit()
        return cur.rowcount > 0

def restore_item_by_name(name: str) -> bool:
    """If soft-deleted, set deleted_at = NULL. Returns True if restored."""
    with sqlite3.connect(DB_PATH) as cx:
        if not _items_has_deleted(cx):
            return False
        cur = cx.execute(
            "UPDATE items SET deleted_at = NULL WHERE LOWER(name)=LOWER(?) AND deleted_at IS NOT NULL",
            (_norm(name),),
        )
        cx.commit()
        return cur.rowcount > 0

def purge_item_by_name(name: str) -> int:
    """Hard delete by (case-insensitive) name. Returns number of rows deleted."""
    with sqlite3.connect(DB_PATH) as cx:
        cur = cx.execute("DELETE FROM items WHERE LOWER(name)=LOWER(?)", (_norm(name),))
        cx.commit()
        return int(cur.rowcount)


# ---------- catalog CRUD ----------

def create_item(item: Item) -> int:
    """
    Insert a new catalog item. If a *soft-deleted* row with the same name exists,
    we **resurrect** it (clear deleted_at and update fields) instead of inserting.
    Returns the id of the active row.
    """
    name = _norm(item.name)

    with sqlite3.connect(DB_PATH) as cx:
        cx.row_factory = sqlite3.Row
        has_deleted = _items_has_deleted(cx)

        # Check for *any* row with this name
        row_any = cx.execute(
            "SELECT * FROM items WHERE LOWER(name)=LOWER(?) LIMIT 1",
            (name,),
        ).fetchone()

        # prefer explicit cash_value if non-zero, else fall back to scrap_value
        cv = getattr(item, "cash_value", None)
        if not cv:  # None or 0 -> fall back
            cv = getattr(item, "scrap_value", 0)

        data = {
            **asdict(item),
            "name": name,
            "item_class": getattr(item.item_class, "value", str(item.item_class)),
            "created_at": getattr(item, "created_at", datetime.now(timezone.utc)).isoformat(),
            "bind_on_pickup": 1 if getattr(item, "bind_on_pickup", False) else 0,
            "durability": int(getattr(item, "durability", 0) or 0),
            "pitch_value": int(getattr(item, "pitch_value", 0) or 0),
            "rune_value": int(getattr(item, "rune_value", 0) or 0),
            "scrap_value": int(getattr(item, "scrap_value", 0) or 0),
            "hidden_trait": getattr(item, "hidden_trait", "") or "",
            "mint_index": int(getattr(item, "mint_index", 0) or 0),
            "rarity": (getattr(item, "rarity", "common") or "common").lower(),
            "stack_max": int(getattr(item, "stack_max", 1) or 1),
            "equippable": 1 if getattr(item, "equippable", True) else 0,
            "cash_value": int(cv or 0),
            "subcategory": getattr(item, "subcategory", None),
        }

        has_cash       = _col_exists(cx, "items", "cash_value")
        has_equippable = _col_exists(cx, "items", "equippable")
        has_rarity     = _col_exists(cx, "items", "rarity")
        has_stack      = _col_exists(cx, "items", "stack_max")
        has_subcat     = _col_exists(cx, "items", "subcategory")

        if row_any:
            # If row exists and is soft-deleted -> RESURRECT
            if has_deleted and _row_has(row_any, "deleted_at") and row_any["deleted_at"]:
                sets = [
                    "item_class = ?",
                    "bind_on_pickup = ?",
                    "durability = ?",
                    "pitch_value = ?",
                    "rune_value = ?",
                    "scrap_value = ?",
                    "hidden_trait = ?",
                    "mint_index = ?",
                    "deleted_at = NULL",
                ]
                args: list[Any] = [
                    data["item_class"],
                    data["bind_on_pickup"],
                    data["durability"],
                    data["pitch_value"],
                    data["rune_value"],
                    data["scrap_value"],
                    data["hidden_trait"],
                    data["mint_index"],
                ]
                if has_rarity:
                    sets.append("rarity = ?");       args.append(data["rarity"])
                if has_stack:
                    sets.append("stack_max = ?");    args.append(data["stack_max"])
                if has_equippable:
                    sets.append("equippable = ?");   args.append(data["equippable"])
                if has_cash:
                    sets.append("cash_value = ?");   args.append(data["cash_value"])
                if has_subcat:
                    sets.append("subcategory = ?");  args.append(data["subcategory"])

                sql_upd = f"UPDATE items SET {', '.join(sets)} WHERE id = ?"
                args.append(int(row_any["id"]))
                cx.execute(sql_upd, tuple(args))
                cx.commit()
                return int(row_any["id"])

            # Otherwise the *active* name is taken
            raise ValueError(f"Item with name '{name}' already exists")

        # Fresh INSERT
        cols = [
            "name", "item_class", "created_at", "bind_on_pickup", "durability",
            "pitch_value", "rune_value", "scrap_value", "hidden_trait", "mint_index",
        ]
        if has_rarity:     cols.append("rarity")
        if has_stack:      cols.append("stack_max")
        if has_equippable: cols.append("equippable")
        if has_cash:       cols.append("cash_value")
        if has_subcat:     cols.append("subcategory")

        sql = f"INSERT INTO items ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})"
        cx.execute(sql, tuple(data[c] for c in cols))
        new_id = int(cx.execute("SELECT last_insert_rowid()").fetchone()[0])
        cx.commit()
        return new_id


def update_item(item: Item) -> None:
    with sqlite3.connect(DB_PATH) as cx:
        cx.row_factory = sqlite3.Row

        has_cash       = _col_exists(cx, "items", "cash_value")
        has_equippable = _col_exists(cx, "items", "equippable")
        has_rarity     = _col_exists(cx, "items", "rarity")
        has_stack      = _col_exists(cx, "items", "stack_max")
        has_subcat     = _col_exists(cx, "items", "subcategory")

        sets = [
            "name = ?",
            "item_class = ?",
            "bind_on_pickup = ?",
            "durability = ?",
            "pitch_value = ?",
            "rune_value = ?",
            "scrap_value = ?",
            "hidden_trait = ?",
            "mint_index = ?",
        ]
        args: list[Any] = [
            _norm(item.name),
            getattr(item.item_class, "value", str(item.item_class)),
            1 if getattr(item, "bind_on_pickup", False) else 0,
            int(getattr(item, "durability", 0) or 0),
            int(getattr(item, "pitch_value", 0) or 0),
            int(getattr(item, "rune_value", 0) or 0),
            int(getattr(item, "scrap_value", 0) or 0),
            getattr(item, "hidden_trait", "") or "",
            int(getattr(item, "mint_index", 0) or 0),
        ]

        if has_rarity:
            sets.append("rarity = ?")
            args.append((getattr(item, "rarity", "common") or "common").lower())
        if has_stack:
            sets.append("stack_max = ?")
            args.append(int(getattr(item, "stack_max", 1) or 1))
        if has_equippable:
            sets.append("equippable = ?")
            args.append(1 if getattr(item, "equippable", True) else 0)
        if has_cash:
            # prefer explicit cash_value if non-zero, else use scrap_value
            cv = getattr(item, "cash_value", None)
            if not cv:
                cv = getattr(item, "scrap_value", 0)
            sets.append("cash_value = ?")
            args.append(int(cv or 0))
        if has_subcat:
            sets.append("subcategory = ?")
            args.append(getattr(item, "subcategory", None))

        sql = f"UPDATE items SET {', '.join(sets)} WHERE id = ?"
        args.append(int(getattr(item, "id", 0)))
        cx.execute(sql, tuple(args))
        cx.commit()


def get_item_by_name(name: str, include_deleted: bool = False) -> Optional[Item]:
    name = _norm(name)
    with sqlite3.connect(DB_PATH) as cx:
        cx.row_factory = sqlite3.Row
        has_deleted = _items_has_deleted(cx)
        where = "WHERE LOWER(name)=LOWER(?)"
        if has_deleted and not include_deleted:
            where += " AND deleted_at IS NULL"
        row = cx.execute(f"SELECT * FROM items {where} LIMIT 1", (name,)).fetchone()
        if not row:
            return None

        item = Item(
            id=int(row["id"]),
            name=row["name"],
            item_class=ItemClass(row["item_class"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            bind_on_pickup=bool(row["bind_on_pickup"]),
            durability=int(_row_or(row, "durability", 0)),
            scrap_value=int(_row_or(row, "scrap_value", 0)),
            hidden_trait=_row_or(row, "hidden_trait", ""),
            mint_index=int(_row_or(row, "mint_index", 0)),
        )
        setattr(item, "rarity", _row_or(row, "rarity", "common"))
        setattr(item, "stack_max", int(_row_or(row, "stack_max", 1)))
        setattr(item, "equippable", bool(_row_or(row, "equippable", 1)))
        setattr(item, "cash_value", int(_row_or(row, "cash_value", _row_or(row, "scrap_value", 0))))
        if _row_has(row, "pitch_value"):
            setattr(item, "pitch_value", int(_row_or(row, "pitch_value", 0)))
        if _row_has(row, "rune_value"):
            setattr(item, "rune_value", int(_row_or(row, "rune_value", 0)))
        if _row_has(row, "subcategory"):
            setattr(item, "subcategory", _row_or(row, "subcategory", None))
        return item


def catalog_items(
    q: str = "",
    rarity: Optional[str] = None,
    item_class: Optional[str] = None,
    equippable: Optional[bool] = None,
    page: int = 1,
    page_size: int = 20,
) -> list[dict]:
    """Return rows for catalog display, including durability, cash_value, stack_max and subcategory."""
    q = (q or "").strip()
    offs = max(0, (int(page) - 1) * int(page_size))

    with sqlite3.connect(DB_PATH) as cx:
        cx.row_factory = sqlite3.Row
        has_deleted = _items_has_deleted(cx)
        has_cash = _col_exists(cx, "items", "cash_value")
        has_equippable = _col_exists(cx, "items", "equippable")
        has_subcat = _col_exists(cx, "items", "subcategory")

        where_parts: list[str] = []
        params: list[Any] = []

        if q:
            where_parts.append("LOWER(name) LIKE ?")
            params.append(f"%{q.lower()}%")
        if rarity and _col_exists(cx, "items", "rarity"):
            where_parts.append("LOWER(rarity)=LOWER(?)")
            params.append(rarity)
        if item_class:
            where_parts.append("LOWER(item_class)=LOWER(?)")
            params.append(item_class)
        if equippable is not None and has_equippable:
            where_parts.append("equippable = ?")
            params.append(1 if equippable else 0)
        if has_deleted:
            where_parts.append("deleted_at IS NULL")

        where = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""

        cash_select = "cash_value" if has_cash else "scrap_value"
        sub_select = "subcategory" if has_subcat else "NULL as subcategory"

        sql = f"""
            SELECT
                id,
                name,
                item_class,
                {sub_select},
                COALESCE(durability, 0) AS durability,
                COALESCE({cash_select}, scrap_value, 0) AS cash_value,
                COALESCE(stack_max, 1) AS stack_max
            FROM items
            {where}
            ORDER BY id ASC
            LIMIT ? OFFSET ?
        """
        params.extend([int(page_size), int(offs)])
        rows = cx.execute(sql, tuple(params)).fetchall()
        return [dict(r) for r in rows]


# ---------- inventory + grants (unchanged) ----------

def grant_item(user_id: int, item: Item, qty: int = 1, equipped: bool = False) -> int:
    with sqlite3.connect(DB_PATH) as cx:
        cur = cx.cursor()
        cur.execute("SELECT id FROM items WHERE id = ?", (int(getattr(item, "id", 0)),))
        if cur.fetchone() is None:
            cur.execute(
                """
                INSERT INTO items (
                    id, name, item_class, created_at, bind_on_pickup, durability,
                    pitch_value, rune_value, scrap_value, hidden_trait, mint_index
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(getattr(item, "id", 0)),
                    _norm(item.name),
                    getattr(item.item_class, "value", str(item.item_class)),
                    getattr(item, "created_at", datetime.now(timezone.utc)).isoformat(),
                    1 if getattr(item, "bind_on_pickup", False) else 0,
                    int(getattr(item, "durability", 0) or 0),
                    int(getattr(item, "pitch_value", 0) or 0),
                    int(getattr(item, "rune_value", 0) or 0),
                    int(getattr(item, "scrap_value", 0) or 0),
                    getattr(item, "hidden_trait", "") or "",
                    int(getattr(item, "mint_index", 0) or 0),
                ),
            )
        cur.execute(
            """
            INSERT INTO inventory (user_id, item_id, qty, equipped, acquired_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (int(user_id), int(getattr(item, "id", 0)), int(qty or 1), 1 if equipped else 0, _now_iso()),
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
