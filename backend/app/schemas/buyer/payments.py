from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class BuyerPaymentCreateRequest(BaseModel):
    amount_cny: float = Field(gt=0)
    channel: str = "manual"
    subject: str = "Wallet top-up"
    description: str | None = None
    expires_minutes: int = Field(default=30, ge=1, le=1440)


class BuyerPaymentConfirmRequest(BaseModel):
    status: str = "succeeded"
    third_party_txn_id: str | None = None


class BuyerWalletTopupLedgerResponse(BaseModel):
    id: int
    payment_order_id: int | None
    entry_type: str
    amount_delta_cny: float
    balance_after: float
    detail: dict[str, Any]
    created_at: datetime


class BuyerPaymentListItem(BaseModel):
    id: int
    payment_no: str
    payment_type: str
    amount_cny: float
    currency: str
    status: str
    channel: str
    subject: str
    description: str | None
    third_party_txn_id: str | None
    paid_at: datetime | None
    expired_at: datetime | None
    created_at: datetime
    updated_at: datetime


class BuyerPaymentResponse(BuyerPaymentListItem):
    latest_ledger_entry: BuyerWalletTopupLedgerResponse | None = None
