from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import SessionLocal
from app.models.platform import (
    BuyerWallet,
    ImageOffer,
    RuntimeAccessSession,
    UsageCharge,
    WalletLedger,
)
from app.services.runtime_sessions import TERMINAL_SESSION_STATES
from app.services.swarm_manager import SwarmManagerError, remove_runtime_session_bundle
from app.services.wireguard_server import remove_server_peer


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_wallet(db: Session, buyer_user_id: int) -> BuyerWallet:
    wallet = db.scalar(select(BuyerWallet).where(BuyerWallet.buyer_user_id == buyer_user_id))
    if wallet is None:
        wallet = BuyerWallet(
            buyer_user_id=buyer_user_id,
            balance_cny_credits=settings.DEFAULT_TEST_BALANCE_CNY_CREDITS,
        )
        db.add(wallet)
        db.flush()
    return wallet


def _terminate_session_for_billing(db: Session, session: RuntimeAccessSession, reason: str) -> RuntimeAccessSession:
    try:
        remove_runtime_session_bundle(
            settings,
            runtime_service_name=session.service_name,
            config_name=session.config_name,
            gateway_service_name=session.gateway_service_name,
        )
    except SwarmManagerError:
        pass
    if session.buyer_wireguard_public_key:
        try:
            remove_server_peer(settings, public_key=session.buyer_wireguard_public_key)
        except Exception:
            pass
    session.status = "stopped"
    session.gateway_status = "stopped"
    session.ended_at = utcnow()
    existing_logs = session.last_logs or ""
    session.last_logs = f"{existing_logs}\n[billing] {reason}".strip()
    db.commit()
    return session


def _next_billing_window(session: RuntimeAccessSession) -> tuple[datetime, datetime] | None:
    if session.started_at is None:
        return None
    start = session.billed_through or session.started_at
    end = start + timedelta(hours=1)
    return start, end


def charge_due_session_hour(db: Session, session: RuntimeAccessSession, now: datetime | None = None) -> UsageCharge | None:
    now = now or utcnow()
    if session.image_offer_id is None:
        return None
    if session.status in TERMINAL_SESSION_STATES:
        return None

    window = _next_billing_window(session)
    if window is None:
        return None
    billing_start, billing_end = window
    if now < billing_end:
        return None

    offer = db.get(ImageOffer, session.image_offer_id)
    if offer is None or offer.current_billable_price_cny_per_hour is None:
        _terminate_session_for_billing(db, session, "offer pricing unavailable")
        return None

    wallet = _ensure_wallet(db, session.buyer_user_id)
    hourly_price = float(offer.current_billable_price_cny_per_hour)
    projected_balance = float(wallet.balance_cny_credits) - hourly_price
    allowed_floor = -hourly_price * float(settings.SESSION_ALLOWED_DEBT_MULTIPLIER)
    if projected_balance < allowed_floor:
        _terminate_session_for_billing(db, session, "insufficient balance for next billing hour")
        return None

    charge = UsageCharge(
        buyer_user_id=session.buyer_user_id,
        session_id=session.id,
        offer_id=offer.id,
        price_snapshot_id=offer.current_price_snapshot_id,
        billing_hour_start=billing_start,
        billing_hour_end=billing_end,
        hourly_price_cny=hourly_price,
    )
    db.add(charge)
    db.flush()

    wallet.balance_cny_credits = projected_balance
    ledger = WalletLedger(
        buyer_user_id=session.buyer_user_id,
        session_id=session.id,
        usage_charge_id=charge.id,
        entry_type="hourly_debit",
        amount_delta_cny=-hourly_price,
        balance_after=projected_balance,
        detail={
            "offer_id": offer.id,
            "billing_hour_start": billing_start.isoformat(),
            "billing_hour_end": billing_end.isoformat(),
        },
    )
    db.add(ledger)
    db.flush()

    charge.ledger_id = ledger.id
    session.billed_through = billing_end
    session.accrued_usage_cny = float(session.accrued_usage_cny or 0.0) + hourly_price
    session.last_hourly_price_cny = hourly_price
    db.commit()
    db.refresh(charge)
    return charge


def process_due_usage_charges(now: datetime | None = None) -> int:
    now = now or utcnow()
    db = SessionLocal()
    try:
        sessions = db.scalars(
            select(RuntimeAccessSession).where(
                RuntimeAccessSession.image_offer_id.is_not(None),
                RuntimeAccessSession.started_at.is_not(None),
                RuntimeAccessSession.status.not_in(TERMINAL_SESSION_STATES),
            )
        ).all()
        count = 0
        for session in sessions:
            if charge_due_session_hour(db, session, now=now) is not None:
                count += 1
        return count
    finally:
        db.close()
