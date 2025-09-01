from __future__ import annotations
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Optional




from src.models.item import Item




DB_PATH = Path("var/db/lowlife.sqlite")








def _now_iso() -> str:
return datetime.now(timezone.utc).isoformat()








def grant_item(user_id: int, item: Item, qty: int = 1, equipped: bool = False) -> int:
with sqlite3.connect(DB_PATH) as cx:
cur = cx.cursor()
# upsert item catalog entry
cur.execute("SELECT id FROM items WHERE id = ?", (item.id,))
if cur.fetchone() is None:
cur.execute(
"""
INSERT INTO items (id, name, item_class, created_at, bind_on_pickup, durability,
pitch_value, rune_value, scrap_value, hidden_trait, mint_index)
VALUES (:id, :name, :item_class, :created_at, :bind_on_pickup, :durability,
:pitch_value, :rune_value, :scrap_value, :hidden_trait, :mint_index)
""",
{
**asdict(item),
"item_class": item.item_class.value,
"created_at": item.created_at.isoformat(),
"bind_on_pickup": 1 if item.bind_on_pickup else 0,
},
)
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
cur = cx.cursor()
cur.execute("UPDATE inventory SET equipped = ? WHERE id = ?", (1 if equipped else 0, inv_entry_id))
cx.commit()








def inventory_for_user(user_id: int) -> list[dict]:
with sqlite3.connect(DB_PATH) as cx:
cx.row_factory = sqlite3.Row
cur = cx.cursor()
cur.execute(
"""
SELECT i.id as inv_id, i.qty, i.equipped, it.name, it.item_class, it.durability,
it.pitch_value, it.rune_value, it.scrap_value
FROM inventory i
JOIN items it ON it.id = i.item_id
WHERE i.user_id = ?
ORDER BY i.id DESC
""",
(user_id,),
)
return [dict(r) for r in cur.fetchall()]