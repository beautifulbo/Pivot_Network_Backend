from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routes.buyer.common import serialize_wallet, serialize_wallet_ledger
from app.core.db import get_db
from app.models.identity import User
from app.schemas.buyer.wallet import BuyerWalletResponse, WalletLedgerResponse
from app.services.buyer_wallets import get_buyer_wallet, list_wallet_ledger_entries

router = APIRouter()


@router.get("/wallet", response_model=BuyerWalletResponse)
def read_buyer_wallet(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BuyerWalletResponse:
    wallet = get_buyer_wallet(db, current_user.id)
    db.commit()
    db.refresh(wallet)
    return serialize_wallet(wallet)


@router.get("/wallet/ledger", response_model=list[WalletLedgerResponse])
def read_buyer_wallet_ledger(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[WalletLedgerResponse]:
    return [serialize_wallet_ledger(entry) for entry in list_wallet_ledger_entries(db, current_user.id)]
