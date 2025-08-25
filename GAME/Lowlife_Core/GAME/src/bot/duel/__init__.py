# FILE: src/bot/duel/__init__.py
from __future__ import annotations

"""
Thin wrapper that exposes the legacy duel command group so bot.py can
`from .duel import register_duel` exactly like before.
"""

from .legacy_port import register_duel  # re-export
__all__ = ["register_duel"]
