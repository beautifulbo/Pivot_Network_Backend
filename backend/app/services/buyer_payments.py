from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.buyer import WalletLedger
from app.models.payment import PaymentOrder, PaymentTransaction
from app.services.buyer_wallets import ensure_buyer_wallet

FINAL_PAYMENT_STATUSES = {"succeeded", "failed", "cancelled"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def generate_payment_no() -> str:
    return f"PAY-{int(utcnow().timestamp())}-{secrets.token_hex(4)}"


def create_payment_order(
    db: Session,
    *,
    buyer_user_id: int,
    amount_cny: float,
    channel: str,
    subject: str,
    description: str | None,
    expires_minutes: int,
) -> PaymentOrder:
    order = PaymentOrder(
        buyer_user_id=buyer_user_id,
        payment_no=generate_payment_no(),
        payment_type="wallet_topup",
        amount_cny=amount_cny,
        currency="CNY",
        status="pending",
        channel=channel,
        subject=subject,
        description=description,
        expired_at=utcnow() + timedelta(minutes=expires_minutes),
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def list_buyer_payments(db: Session, buyer_user_id: int) -> list[PaymentOrder]:
    return db.scalars(
        select(PaymentOrder).where(PaymentOrder.buyer_user_id == buyer_user_id).order_by(PaymentOrder.id.desc())
    ).all()


def get_buyer_payment(db: Session, *, buyer_user_id: int, payment_id: int) -> PaymentOrder | None:
    return db.scalar(
        select(PaymentOrder).where(PaymentOrder.id == payment_id, PaymentOrder.buyer_user_id == buyer_user_id)
    )


def get_payment_topup_ledger(db: Session, payment_order_id: int) -> WalletLedger | None:
    return db.scalar(
        select(WalletLedger).where(WalletLedger.payment_order_id == payment_order_id).order_by(WalletLedger.id.desc())
    )


def get_payment_transaction(db: Session, payment_order_id: int) -> PaymentTransaction | None:
    return db.scalar(
        select(PaymentTransaction)
        .where(PaymentTransaction.payment_order_id == payment_order_id)
        .order_by(PaymentTransaction.id.desc())
    )


def confirm_payment_order(
    db: Session,
    *,
    payment_order: PaymentOrder,
    status: str,
    third_party_txn_id: str | None = None,
) -> tuple[PaymentOrder, WalletLedger | None]:
    if status not in FINAL_PAYMENT_STATUSES:
        raise ValueError("unsupported_payment_status")

    if payment_order.status in FINAL_PAYMENT_STATUSES:
        return payment_order, get_payment_topup_ledger(db, payment_order.id)

    if third_party_txn_id:
        payment_order.third_party_txn_id = third_party_txn_id

    if status != "succeeded":
        payment_order.status = status
        db.commit()
        db.refresh(payment_order)
        return payment_order, None

    now = utcnow()
    wallet = ensure_buyer_wallet(db, payment_order.buyer_user_id)
    wallet.balance_cny_credits = float(wallet.balance_cny_credits) + float(payment_order.amount_cny)

    payment_order.status = "succeeded"
    payment_order.paid_at = now

    transaction = PaymentTransaction(
        payment_order_id=payment_order.id,
        buyer_user_id=payment_order.buyer_user_id,
        transaction_type="topup",
        amount_cny=payment_order.amount_cny,
        status="succeeded",
        channel=payment_order.channel,
        reference_no=payment_order.third_party_txn_id or payment_order.payment_no,
        detail={
            "payment_no": payment_order.payment_no,
            "payment_type": payment_order.payment_type,
        },
    )
    db.add(transaction)
    db.flush()

    ledger = WalletLedger(
        buyer_user_id=payment_order.buyer_user_id,
        payment_order_id=payment_order.id,
        entry_type="topup_credit",
        amount_delta_cny=payment_order.amount_cny,
        balance_after=wallet.balance_cny_credits,
        detail={
            "payment_no": payment_order.payment_no,
            "channel": payment_order.channel,
            "transaction_id": transaction.id,
        },
    )
    db.add(ledger)
    db.commit()
    db.refresh(payment_order)
    db.refresh(ledger)
    return payment_order, ledger
