# GAME/src/systems/tags/seed.py
from __future__ import annotations
import argparse
import sqlite3
from typing import Iterable

from . import dal
from .schema import ensure_tags_schema

def _exec(con: sqlite3.Connection, sql: str, args: Iterable):
    con.execute(sql, tuple(args))

def upsert_tag(name: str, **kw) -> None:
    """
    Idempotent insert/update. Also sets a normalized script_key so lookups
    by `bleeding` or `Bleeding` both work.
    """
    script_key = dal.normalize_key(name)
    with sqlite3.connect(dal.DB_PATH) as con:
        con.row_factory = sqlite3.Row
        _exec(
            con,
            """
            INSERT INTO tags (
                name, script_key, kind, polarity, tick_ms, base_intensity,
                max_stacks, stack_policy, exclusivity_key, refresh_policy, duration_ms
            )
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(name) DO UPDATE SET
                script_key       = excluded.script_key,
                kind             = COALESCE(NULLIF(excluded.kind,''), tags.kind),
                polarity         = COALESCE(excluded.polarity, tags.polarity),
                tick_ms          = COALESCE(excluded.tick_ms, tags.tick_ms),
                base_intensity   = COALESCE(excluded.base_intensity, tags.base_intensity),
                max_stacks       = COALESCE(excluded.max_stacks, tags.max_stacks),
                stack_policy     = COALESCE(excluded.stack_policy, tags.stack_policy),
                exclusivity_key  = COALESCE(excluded.exclusivity_key, tags.exclusivity_key),
                refresh_policy   = COALESCE(excluded.refresh_policy, tags.refresh_policy),
                duration_ms      = COALESCE(excluded.duration_ms, tags.duration_ms)
            """,
            (
                name, script_key,
                kw.get("kind", "dynamic"),
                kw.get("polarity"),
                kw.get("tick_ms", 1500),
                kw.get("base_intensity", 1.0),
                kw.get("max_stacks", 5),
                kw.get("stack_policy", "add"),
                kw.get("exclusivity_key", ""),
                kw.get("refresh_policy", "full"),
                kw.get("duration_ms", 0),
            ),
        )
        con.commit()

def seed_defaults(*, force: bool = False) -> int:
    """
    Seeds baseline tags. If `force=False` and catalog already has rows, we skip.
    Returns number of tags upserted.
    """
    ensure_tags_schema()
    with sqlite3.connect(dal.DB_PATH) as con:
        n_existing = con.execute("SELECT COUNT(*) FROM tags").fetchone()[0]

    if n_existing and not force:
        return 0

    upsert_tag(
        "Bleeding",
        kind="dynamic",
        polarity="negative",
        tick_ms=1500,
        base_intensity=1.0,
        max_stacks=5,
        stack_policy="add",
        refresh_policy="partial",
        duration_ms=0,
    )
    upsert_tag(
        "Gunshot Wound",
        kind="event",
        polarity="negative",
        tick_ms=0,
        duration_ms=20_000,
    )
    return 2

# CLI: python -m src.systems.tags.seed [--force]
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Seed even if catalog is non-empty")
    args = parser.parse_args()
    ensure_tags_schema()
    n = seed_defaults(force=args.force)
    print(f"Seeded {n} tag(s) into: {dal.DB_PATH}")

if __name__ == "__main__":
    main()
