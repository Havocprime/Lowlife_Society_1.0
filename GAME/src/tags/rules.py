from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from pathlib import Path

import yaml


@dataclass
class Rule:
    """A single rule loaded from YAML."""
    event: str                   # e.g., "damage", "enter_zone", or "*" wildcard
    when: Dict[str, Any]         # condition block
    actions: List[Dict[str, Any]]  # list of action dicts


class TagRuleEngine:
    """
    Tiny rule engine that reacts to gameplay 'events' and applies/removes tags
    through TagEngine. Keep it deliberately simple & predictable.
    """
    def __init__(self, engine: "TagEngine", rules_path: str):
        self.engine = engine
        self.rules_path = Path(rules_path) if rules_path else None
        self.rules: List[Rule] = []

    # --------------------------------------------------------------------- #
    # Loading
    # --------------------------------------------------------------------- #
    def load(self) -> None:
        """(Re)load rules from YAML. Missing file is OK."""
        self.rules = []
        if not self.rules_path or not self.rules_path.exists():
            return

        data = yaml.safe_load(self.rules_path.read_text(encoding="utf-8")) or {}
        for raw in data.get("rules", []):
            self.rules.append(
                Rule(
                    event=(raw.get("on") or raw.get("event") or "*"),
                    when=(raw.get("when") or {}),
                    actions=(raw.get("do") or raw.get("actions") or []),
                )
            )

    # --------------------------------------------------------------------- #
    # Runtime
    # --------------------------------------------------------------------- #
    def handle_event(self, entity_id: str, event: Dict[str, Any]) -> None:
        """
        Dispatch an event to matching rules.
        Example event: {"type": "damage", "amount": 12, "source": "knife"}
        """
        etype = (event.get("type") or event.get("event") or "").lower()

        for rule in self.rules:
            if rule.event != "*" and rule.event.lower() != etype:
                continue
            if not self._passes_when(entity_id, event, rule.when):
                continue
            self._execute_actions(entity_id, event, rule.actions)

    # --------------------------------------------------------------------- #
    # Helpers: conditions
    # --------------------------------------------------------------------- #
    def _passes_when(self, entity_id: str, event: Dict[str, Any], when: Dict[str, Any]) -> bool:
        """
        Supported condition keys (all optional):
          - has: "tag.key" or ["tag.a","tag.b"]       -> entity must have all
          - has_any: ["tag.a","tag.b"]                -> entity must have any
          - not: {...}                                -> negate a nested when
          - event: {"field": value, ...}              -> exact matches on event payload
        All top-level keys are ANDed.
        """
        if not when:
            return True

        # has: str | list[str]
        if "has" in when:
            required = when["has"]
            if isinstance(required, str):
                if not self.engine.has(entity_id, required):
                    return False
            else:
                for key in required:
                    if not self.engine.has(entity_id, key):
                        return False

        # has_any: list[str]
        if "has_any" in when:
            options = when["has_any"] or []
            if not any(self.engine.has(entity_id, key) for key in options):
                return False

        # event field equality checks
        if "event" in when:
            fields = when["event"] or {}
            for k, v in fields.items():
                if event.get(k) != v:
                    return False

        # not: nested when
        if "not" in when:
            if self._passes_when(entity_id, event, when["not"] or {}):
                return False

        return True

    # --------------------------------------------------------------------- #
    # Helpers: actions
    # --------------------------------------------------------------------- #
    def _execute_actions(self, entity_id: str, event: Dict[str, Any], actions: List[Dict[str, Any]]) -> None:
        """
        Supported actions:
          - {"apply": {"tag": "phys.bleeding", "props": {...}}}
          - {"remove": {"tag": "phys.bleeding"}}
          - {"apply_many": [{"tag": "...", "props": {...}}, ...]}
          - {"remove_many": ["tag.a", "tag.b"]}
          - {"emit": {"type": "another_event", "...": "..."}}
        Unknown actions are ignored (no crash).
        """
        for act in actions or []:
            if "apply" in act:
                spec = act["apply"] or {}
                key = spec.get("tag")
                props = spec.get("props") or {}
                if key:
                    self.engine.apply(entity_id, key, **props)

            elif "remove" in act:
                spec = act["remove"] or {}
                key = spec.get("tag")
                if key:
                    self.engine.remove(entity_id, key)

            elif "apply_many" in act:
                for spec in act["apply_many"] or []:
                    key = spec.get("tag")
                    props = spec.get("props") or {}
                    if key:
                        self.engine.apply(entity_id, key, **props)

            elif "remove_many" in act:
                for key in act["remove_many"] or []:
                    if key:
                        self.engine.remove(entity_id, key)

            elif "emit" in act:
                # Let TagEngine (or your game loop) decide how to route this.
                # If your TagEngine doesn't implement event emission, ignore.
                spec = act["emit"] or {}
                try:
                    emit = getattr(self.engine, "emit_event", None)
                    if callable(emit):
                        emit(entity_id, spec)
                except Exception:
                    pass


__all__ = ["TagRuleEngine", "Rule"]
