# GAME/src/tags/__init__.py
from .registry import TagRegistry
from .service_runtime import TagRuntime

__all__ = ["TagRegistry", "TagRuntime"]

# GAME/src/tags/__init__.py
from .service_runtime import TagRuntime  # re-export for cogs.tags_admin
