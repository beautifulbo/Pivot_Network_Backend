from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import relationship

from app.models.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BuyerWallet(Base):
    __tablename__ = "buyer_wallets"

    id = Column(Integer, primary_key=True)
    buyer_user_id = Column(Integer, ForeignKey("users.id"), unique=True, index=True, nullable=False)
    balance_cny_credits = Column(Float, default=0.0, nullable=False)
    status = Column(String(50), default="active", nullable=False)
    frozen_amount_cny = Column(Float, default=0.0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    buyer = relationship("User", back_populates="buyer_wallet")


class WalletLedger(Base):
    __tablename__ = "wallet_ledgers"

    id = Column(Integer, primary_key=True)
    buyer_user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    session_id = Column(Integer, ForeignKey("runtime_access_sessions.id"), nullable=True, index=True)
    usage_charge_id = Column(Integer, ForeignKey("usage_charges.id"), nullable=True, index=True)
    payment_order_id = Column(Integer, ForeignKey("payment_orders.id"), nullable=True, index=True)
    entry_type = Column(String(50), nullable=False)
    amount_delta_cny = Column(Float, nullable=False)
    balance_after = Column(Float, nullable=False)
    detail = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class BuyerOrder(Base):
    __tablename__ = "buyer_orders"

    id = Column(Integer, primary_key=True)
    buyer_user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    offer_id = Column(Integer, ForeignKey("image_offers.id"), index=True, nullable=False)
    order_no = Column(String(64), unique=True, index=True, nullable=True)
    requested_duration_minutes = Column(Integer, nullable=False)
    issued_hourly_price_cny = Column(Float, nullable=False)
    payment_status = Column(String(50), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    order_status = Column(String(50), default="issued", nullable=False)
    license_token = Column(String(255), unique=True, index=True, nullable=False)
    license_redeemed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
