from __future__ import annotations
import uuid
from typing import Optional
from src.db import dal

class EconError(Exception): ...

def _idem(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"

def balance(cid: int) -> int:
    return int(dal.get_balance("character", cid))

def ensure_wallet(cid: int) -> None:
    dal.ensure_wallet("character", cid)

def purchase(cid: int, amount: int, *, reason: str = "purchase", idem: Optional[str] = None) -> int:
    if amount <= 0:
        raise EconError("amount must be positive")
    ensure_wallet(cid)
    if balance(cid) < amount:
        raise EconError("insufficient funds")
    dal.tx_debit("character", cid, amount, reason=reason, idem=idem or _idem("buy"))
    dal.append_event("econ/purchase", None, f"character:{cid}", {"amount": amount, "reason": reason})
    return balance(cid)

def refund(cid: int, amount: int, *, reason: str = "refund", idem: Optional[str] = None) -> int:
    if amount <= 0:
        raise EconError("amount must be positive")
    ensure_wallet(cid)
    dal.tx_credit("character", cid, amount, reason=reason, idem=idem or _idem("refund"))
    dal.append_event("econ/refund", None, f"character:{cid}", {"amount": amount, "reason": reason})
    return balance(cid)

def transfer(from_cid: int, to_cid: int, amount: int, *, reason: str = "transfer",
             idem: Optional[str] = None) -> tuple[int, int]:
    if amount <= 0:
        raise EconError("amount must be positive")
    ensure_wallet(from_cid); ensure_wallet(to_cid)
    if balance(from_cid) < amount:
        raise EconError("insufficient funds")
    idem = idem or _idem("xfer")
    dal.tx_debit("character", from_cid, amount, reason=reason, idem=idem + ":debit")
    dal.tx_credit("character", to_cid,   amount, reason=reason, idem=idem + ":credit")
    dal.append_event("econ/transfer", None, f"character:{from_cid}->{to_cid}", {"amount": amount, "reason": reason})
    return balance(from_cid), balance(to_cid)
