from __future__ import annotations
from src.db import dal

def credit_character(character_id: int, amount: int, *, reason: str, idem: str, meta: dict|None=None) -> int|None:
    return dal.tx_credit("character", character_id, amount, reason=reason, idem=idem, meta=meta)

def debit_character(character_id: int, amount: int, *, reason: str, idem: str, meta: dict|None=None, allow_overdraft: bool=False) -> int|None:
    return dal.tx_debit("character", character_id, amount, reason=reason, idem=idem, meta=meta, allow_overdraft=allow_overdraft)

def balance_character(character_id: int) -> int:
    return dal.get_balance("character", character_id)
