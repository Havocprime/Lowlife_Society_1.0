# GAME/src/tags/engine.py
from __future__ import annotations
import time
from typing import Dict, List, Optional
from .models import TagInstance, StackMode

class TagEngine:
    def __init__(self, registry):
        self.registry = registry
        # active[entity_id][tag_key] = TagInstance
        self.active: Dict[str, Dict[str, TagInstance]] = {}

    def _now(self) -> float:
        return time.time()

    def apply(
        self,
        entity_id: str,
        key: str,
        *,
        severity: Optional[int] = None,
        duration_s: Optional[int] = None,
        source: Optional[str] = None,
        data: Optional[dict] = None,
    ) -> TagInstance:
        spec = self.registry.get(key)
        if not spec:
            raise KeyError(f"Unknown tag '{key}'")

        ent = self.active.setdefault(entity_id, {})
        existing = ent.get(key)

        # severity
        sev = (
            severity
            if severity is not None
            else (existing.severity if existing else spec.default_severity)
        )
        sev = max(1, min(sev, spec.max_severity))

        # expiry
        now = self._now()
        dur = duration_s if duration_s is not None else spec.base_duration_s
        expires = (now + dur) if (dur and dur > 0) else None

        if existing:
            if spec.stack_mode == StackMode.NONE:
                # refresh in place
                existing.severity = sev
                existing.expires_at_ts = expires
                existing.source = source or existing.source
                if data:
                    existing.data.update(data)
                inst = existing
            elif spec.stack_mode == StackMode.COUNT:
                existing.stacks += 1
                existing.severity = sev
                existing.expires_at_ts = expires or existing.expires_at_ts
                if data:
                    existing.data.update(data)
                inst = existing
            elif spec.stack_mode == StackMode.SEVERITY:
                existing.severity = max(existing.severity, sev)
                existing.severity = min(existing.severity, spec.max_severity)
                existing.expires_at_ts = expires or existing.expires_at_ts
                if data:
                    existing.data.update(data)
                inst = existing
            elif spec.stack_mode == StackMode.DURATION_REFRESH:
                existing.severity = sev
                existing.expires_at_ts = expires
                if data:
                    existing.data.update(data)
                inst = existing
            else:
                inst = existing
        else:
            inst = TagInstance(
                key=key,
                source=source,
                severity=sev,
                stacks=1,
                applied_at_ts=now,
                expires_at_ts=expires,
                data=data or {},
            )
            ent[key] = inst

        # Conflicts: remove any tags this spec conflicts with
        for k in list(ent.keys()):
            if k == key:
                continue
            if k in spec.conflicts:
                self.remove(entity_id, k, reason=f"conflict:{key}")

        # Removes on apply
        for k in spec.removes_on_apply:
            if k != key and k in ent:
                self.remove(entity_id, k, reason=f"remove_on_apply:{key}")

        # Grants on apply (one-step, to avoid infinite loops)
        for k in spec.grants_on_apply:
            if k == key or k in ent:
                continue
            try:
                self.apply(entity_id, k, source=f"grant:{key}")
            except KeyError:
                pass

        return inst

    def remove(self, entity_id: str, key: str, *, reason: Optional[str] = None) -> bool:
        ent = self.active.get(entity_id)
        if not ent or key not in ent:
            return False
        del ent[key]
        if not ent:
            del self.active[entity_id]
        return True

    def has(self, entity_id: str, key: str) -> bool:
        ent = self.active.get(entity_id)
        return bool(ent and key in ent)

    def list(self, entity_id: str) -> List[TagInstance]:
        return list(self.active.get(entity_id, {}).values())

    def tick(self, dt_real: float, dt_game: float, dt_turn: float | bool) -> None:
        # expire timed tags
        now = self._now()
        to_del: List[tuple[str, str]] = []
        for entity_id, tags in self.active.items():
            for key, inst in list(tags.items()):
                if inst.expires_at_ts and inst.expires_at_ts <= now:
                    to_del.append((entity_id, key))
        for entity_id, key in to_del:
            self.remove(entity_id, key, reason="expired")
