# GAME/src/tags/service_runtime.py
from __future__ import annotations
from typing import Optional
from .registry import TagRegistry

class TagRuntime:
    """
    Thin runtime wrapper used by /tags_admin.
    Older code awaits .start(), so we provide async start/stop even though
    the current implementation is synchronous and lightweight.
    """

    def __init__(self, tags_dir: Optional[str] = None, rules_path: Optional[str] = None):
        self.tags_dir = tags_dir
        self.rules_path = rules_path
        self.registry = TagRegistry(tags_dir)

    async def start(self) -> None:
        try:
            self.registry.load_all()
        except Exception:
            # Non-fatal; DB catalog remains authoritative.
            pass

    async def stop(self) -> None:
        return

    def reload(self) -> None:
        self.registry.load_all()
