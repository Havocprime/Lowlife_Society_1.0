# Shim module to keep older imports working.
# Re-export the new Tag Engine API living under src.tags.*
from src.tags.models import *
from src.tags.registry import TagRegistry
from src.tags.engine import TagEngine
# Back-compat package for old imports (e.g., src.systems.tags.*)
# Intentionally empty; modules re-export concrete implementations from src.tags.*
