from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class BuyerWalletResponse(BaseModel):
    buyer_user_id: int
    balance_cny_credits: float
    created_at: datetime
    updated_at: datetime


class WalletLedgerResponse(BaseModel):
    id: int
    buyer_user_id: int
    session_id: int | None
    usage_charge_id: int | None
    entry_type: str
    amount_delta_cny: float
    balance_after: float
    detail: dict[str, Any]
    created_at: datetime
