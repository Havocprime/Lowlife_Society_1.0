from __future__ import annotations
import asyncio, json, logging
from typing import Optional, Dict, Any
from . import dal
from .registry import REGISTRY

log = logging.getLogger("tags.engine")

def _eval_state_machine(sm_json: str | None, row: Any) -> str | None:
    if not sm_json: return None
    try:
        sm = json.loads(sm_json)
    except Exception:
        return None
    # minimal placeholder: honor 'terminal' states, otherwise keep state
    cur = (row["state"] or sm.get("initial"))
    if not cur: return None
    # future: evaluate transitions with conditions from ctx
    return cur

class TagEngine:
    def __init__(self): self._task: Optional[asyncio.Task] = None
    async def start(self):
        if self._task: return
        self._task = asyncio.create_task(self._ticker(), name="tags-ticker")
        log.info("TagEngine started")
    async def stop(self):
        if self._task: self._task.cancel(); self._task = None

    async def _ticker(self):
        while True:
            try:
                for row in dal.due_ticks():
                    ctx = {
                        "instance_id": row["id"],
                        "owner_kind": row["owner_kind"],
                        "owner_id": row["owner_id"],
                        "anchor_path": row["anchor_path"],
                        "stacks": row["stacks"],
                        "intensity": row["intensity"],
                        "polarity": row["polarity"],
                        "metadata": json.loads(row["metadata_json"] or "{}"),
                        "state": row["state"],
                        "script_key": row["script_key"],
                    }
                    # state machine (placeholder)
                    _eval_state_machine(row["state_machine_json"], row)
                    # handler
                    key = row["script_key"]
                    if key and key in REGISTRY and REGISTRY[key].get("on_tick"):
                        REGISTRY[key]["on_tick"](ctx)
                    dal.mark_ticked(row["id"])
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.exception("Tag ticker error: %s", e)
            await asyncio.sleep(1.0)
