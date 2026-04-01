from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.buyer import BuyerWallet, WalletLedger


def ensure_buyer_wallet(db: Session, buyer_user_id: int) -> BuyerWallet:
    wallet = db.scalar(select(BuyerWallet).where(BuyerWallet.buyer_user_id == buyer_user_id))
    if wallet is None:
        wallet = BuyerWallet(
            buyer_user_id=buyer_user_id,
            balance_cny_credits=settings.DEFAULT_TEST_BALANCE_CNY_CREDITS,
            status="active",
            frozen_amount_cny=0.0,
        )
        db.add(wallet)
        db.flush()
    return wallet


def get_buyer_wallet(db: Session, buyer_user_id: int) -> BuyerWallet:
    return ensure_buyer_wallet(db, buyer_user_id)


def list_wallet_ledger_entries(db: Session, buyer_user_id: int, *, limit: int = 200) -> list[WalletLedger]:
    return db.scalars(
        select(WalletLedger).where(WalletLedger.buyer_user_id == buyer_user_id).order_by(WalletLedger.id.desc()).limit(limit)
    ).all()
