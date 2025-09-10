# src/cogs/tags/catalog.py
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class TagKey:
    name: str                   # unique, dot.notation
    family: str                 # e.g., "wound", "fracture", "bruise", "laceration", "scratch"
    kind: str = "dynamic"       # "dynamic" or "event"
    max_stacks: int = 10
    negative: bool = True
    # Duration (seconds). None = persistent until cleared. If set and negative, stack timers refresh per add.
    duration_s: int | None = None
    fatal_on_expire: bool = False   # for things like "Bleeding" if you want expiry to kill
    tick_s: int = 60                # engine tick period for decay/expiry bookkeeping

# Core injuries you surfaced in the screenshots:
SEED_KEYS: tuple[TagKey, ...] = (
    TagKey("broken_bone.arm", family="fracture"),
    TagKey("bruise.minor", family="bruise"),
    TagKey("fractured_bone.arm", family="fracture"),
    TagKey("laceration.minor", family="laceration"),
    TagKey("scratch.minor", family="scratch"),
    TagKey("wound.critical", family="wound"),
    TagKey("wound.heavy", family="wound"),
    TagKey("wound.light", family="wound"),
    TagKey("wound.medium", family="wound"),
)

# Live status tags that appear in /tag_list (what you saw: Bleeding, Gunshot Wound)
# Keep them in the same file so `tag_seed` can ensure both tables.
LIVE_PRESETS: tuple[TagKey, ...] = (
    # Bleeding expires => fatal (your logs show a DEATH on tag_expired:Bleeding)
    TagKey("Bleeding", family="wound", kind="dynamic", max_stacks=10, negative=True,
           duration_s=60, fatal_on_expire=True, tick_s=60),
    TagKey("Gunshot Wound", family="event", kind="event", max_stacks=1, negative=True,
           duration_s=None, fatal_on_expire=False, tick_s=60),
)
