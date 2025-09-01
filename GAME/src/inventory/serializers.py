from __future__ import annotations
from typing import Iterable


def as_embed_lines(rows: Iterable[dict]) -> list[str]:
lines: list[str] = []
for r in rows:
eq = "[E] " if r.get("equipped") else ""
cls = r.get("item_class", "?")
name = r.get("name", "?")
qty = r.get("qty", 1)
lines.append(f"{eq}{name} · {cls} ×{qty}")
return lines