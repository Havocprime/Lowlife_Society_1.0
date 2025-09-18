# GAME/src/tags/registry.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional


@dataclass(frozen=True)
class TagMeta:
    name: str
    kind: Optional[str] = None
    polarity: Optional[str] = None
    config_json: Optional[str] = None


class TagRegistry:
    """
    Lightweight, file-optional registry used by the tag system.
    Older code expects .load_all(); newer code may call .load().
    Both are supported here.

    Note: The authoritative catalog lives in the DB (systems.tags.tags).
    This registry is best-effort and safe to be empty.
    """

    def __init__(self, tags_dir: Optional[str] = None):
        self.tags_dir = Path(tags_dir) if tags_dir else None
        self._by_name: Dict[str, TagMeta] = {}

    # ---- Compat surface expected by systems.tags.dal ----
    def load_all(self) -> None:
        """Populate from YAML files if a directory is provided; otherwise no-op."""
        self._by_name.clear()
        if not self.tags_dir:
            return

        for p in self.tags_dir.glob("*.y*ml"):
            try:
                import yaml  # optional
                data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
                name = str(data.get("name") or p.stem)
                kind = data.get("kind")
                polarity = data.get("polarity")
                cfg = data.get("config_json")
                self._by_name[name] = TagMeta(name=name, kind=kind, polarity=polarity, config_json=cfg)
            except Exception:
                # Skip malformed files silently; DB catalog is still authoritative.
                continue

    def load(self) -> None:
        """Alias used by newer code paths."""
        self.load_all()

    # ---- Lookups (best-effort) ----
    def get(self, name: str) -> Optional[TagMeta]:
        return self._by_name.get(name)

    def names(self) -> Iterable[str]:
        return list(self._by_name.keys())
