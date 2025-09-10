FILE srclootroller.py
import json, random, pathlib
from typing import Dict, Any, List, Tuple

ROOT = pathlib.Path(__file__).resolve().parents[1]
CATALOG = ROOT  src  data  starter_catalog.json
POOLS   = ROOT  src  data  starter_loot_pools.json

def _wchoice(entries List[Dict[str, Any]]) - Dict[str, Any]
    weights = [e[weight] for e in entries]
    return random.choices(entries, weights=weights, k=1)[0]

def roll_pool(pool_name str, rolls int  None = None) - List[Tuple[str, int]]
    pools = json.loads(POOLS.read_text())[pools]
    pool = pools[pool_name]
    rmin, rmax = pool[rolls][min], pool[rolls][max]
    n = rolls if rolls is not None else random.randint(rmin, rmax)
    out Dict[str, int] = {}
    for _ in range(n)
        e = _wchoice(pool[entries])
        q = random.randint(e[qty][min], e[qty][max])
        out[e[name]] = out.get(e[name], 0) + q
    return sorted(out.items(), key=lambda kv kv[0].lower())

if __name__ == __main__
    for test_pool in [street_cache,apartment,hardware_store,clinic,gang_hideout]
        items = roll_pool(test_pool)
        print(fn[{test_pool}])
        for name, qty in items
            print(f - {name} x{qty})
