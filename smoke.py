from src.db.dal import (
    append_event,
    create_character,
    ensure_wallet,
    get_balance,
    tx_credit,
    upsert_player,
)

pid = upsert_player("1234567890", "TestUser")
cid = create_character(pid, "Kane", "Blackline")
ensure_wallet("character", cid)
tx_credit("character", cid, 100, reason="seed")
append_event("seed/ready", "1234567890", f"character:{cid}", {"hello": "world"})
print("balance=", get_balance("character", cid))
print("ok")
