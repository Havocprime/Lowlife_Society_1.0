# GAME/src/services/tags_iter.py
from __future__ import annotations
import json, logging
from collections import defaultdict
from typing import Dict, Iterable, Iterator, List, Tuple

from src.systems.tags import dal as tag_dal
from src.db import dal as core_dal

log = logging.getLogger("services.tags_iter")

# Map display names (catalog) -> registry keys (HP drain families).
# Intensity defaults to instance.stacks unless state overrides it.
NAME_TO_KEYS: Dict[str, List[str]] = {
    "Bleeding": ["wound.medium"],          # mild continuous loss
    "Gunshot Wound": ["wound.heavy", "laceration.minor"],  # composite
    # Extend here as you add more catalog names...
}

def _resolve_player_id(owner_kind: str, owner_id: int) -> int | None:
    if owner_kind == "player":
        return int(owner_id)
    if owner_kind == "discord":
        # Try common DALs to canonicalize to a player id
        for fn_name in ("ensure_player", "get_or_create_player", "player_get_or_create", "get_or_create_account"):
            fn = getattr(core_dal, fn_name, None)
            if callable(fn):
                try:
                    try:
                        pid = fn(discord_id=int(owner_id))
                    except TypeError:
                        pid = fn(int(owner_id))
                    return int(pid)
                except Exception:
                    continue
    return None

def _row_to_tags(row) -> List[Dict]:
    """
    Convert one tag instance row -> one or more registry tag dicts:
    {"key": str, "intensity": int, "meta": dict}
    Priority:
      1) If row['state'] JSON contains {"key": "...", "intensity": ...}, use that.
      2) Else map by NAME_TO_KEYS and use stacks as intensity (1..10 clamped).
    """
    name = row["name"]
    stacks = max(1, min(int(row.get("stacks", 1)), 10))
    # Try state override
    state = row.get("state")
    if state:
        try:
            st = json.loads(state)
            if isinstance(st, dict) and "key" in st:
                inten = int(st.get("intensity", stacks))
                return [{"key": str(st["key"]), "intensity": max(1, min(inten, 10)), "meta": st}]
        except Exception:
            pass

    keys = NAME_TO_KEYS.get(name, [])
    return [{"key": k, "intensity": stacks, "meta": {"source_name": name}} for k in keys]

def collect_players_with_damage_tags() -> Iterator[Tuple[int, List[Dict]]]:
    """
    Synchronous collector. Reads active instances, groups by player_id,
    yields (player_id, [tag_dict,...]) for tick processing.
    """
    con = tag_dal._conn()

    # Try likely table names
    rows = []
    for tbl in ("tag_instances", "tags_instances"):
        try:
            rows = list(con.execute(
                f"""SELECT owner_kind, owner_id, name, stacks, state, anchor_path
                    FROM {tbl}
                    WHERE stacks > 0
                """
            ).fetchall())
            if rows:
                break
        except Exception:
            continue

    if not rows:
        return iter(())  # empty iterator

    bucket: Dict[int, List[Dict]] = defaultdict(list)
    for r in rows:
        okind, oid = r["owner_kind"], int(r["owner_id"])
        pid = _resolve_player_id(okind, oid)
        if pid is None:
            continue
        bucket[pid].extend(_row_to_tags(r))

    return ((pid, tags) for pid, tags in bucket.items())
