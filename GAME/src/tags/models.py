# GAME/src/tags/models.py
from __future__ import annotations
from enum import Enum
from typing import Any, Dict, Optional, TypedDict, List
from pydantic import BaseModel, Field

class TagNamespace(str, Enum):
    phys = "phys"   # physical
    ment = "ment"   # mental
    soc  = "soc"    # social
    env  = "env"    # environmental
    fx   = "fx"     # temporary effects (drugs/chems)
    sys  = "sys"    # system flags
    meta = "meta"   # debug / GM

class TagKind(str, Enum):
    STATE = "STATE"
    BUFF = "BUFF"
    DEBUFF = "DEBUFF"
    FLAG = "FLAG"
    CONTEXT = "CONTEXT"

class StackMode(str, Enum):
    NONE = "NONE"                   # reject/refresh; no stacks
    COUNT = "COUNT"                 # increment stack count
    SEVERITY = "SEVERITY"           # bump severity up to max
    DURATION_REFRESH = "DURATION_REFRESH"  # refresh timer on reapply

class DurationMode(str, Enum):
    REAL = "REAL"
    GAME = "GAME"
    TURN = "TURN"

class Visibility(str, Enum):
    PUBLIC = "PUBLIC"
    HIDDEN = "HIDDEN"
    GM_ONLY = "GM_ONLY"

class TagEffect(BaseModel):
    id: str
    type: str                        # e.g. ATTR_ADD, DOT, GATE, ...
    params: Dict[str, Any] = Field(default_factory=dict)

class TagSpec(BaseModel):
    # Author-time
    key: str
    name: str
    ns: TagNamespace = TagNamespace.sys
    kind: TagKind = TagKind.STATE
    category: str = "general"
    icon: Optional[str] = None
    default_severity: int = 1
    max_severity: int = 10
    stack_mode: StackMode = StackMode.SEVERITY
    conflicts: List[str] = Field(default_factory=list)
    excludes_group: Optional[str] = None
    grants_on_apply: List[str] = Field(default_factory=list)
    removes_on_apply: List[str] = Field(default_factory=list)
    resist_key: Optional[str] = None
    effects: List[TagEffect] = Field(default_factory=list)

    # Runtime defaults
    base_duration_s: Optional[int] = None
    duration_mode: DurationMode = DurationMode.REAL
    visible: Visibility = Visibility.PUBLIC

class TagInstance(BaseModel):
    key: str
    source: Optional[str] = None
    severity: int = 1
    stacks: int = 1
    applied_at_ts: float
    expires_at_ts: Optional[float] = None
    data: Dict[str, Any] = Field(default_factory=dict)

class FoldedModifiers(TypedDict, total=False):
    # aggregate read-model consumed by systems
    ATTR_ADD: Dict[str, float]
    ATTR_MULT: Dict[str, float]
    STAT_REGEN: Dict[str, float]
    ROLL_MOD: Dict[str, float]
    ECON_MULT: Dict[str, float]
    VISION_MOD: Dict[str, float]
    PERCEPTION_MOD: Dict[str, float]
    TIMESCALE_MOD: Dict[str, float]  # {"local_game_timescale": 0.9}
