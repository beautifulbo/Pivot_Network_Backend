from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text

from app.models.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PaymentOrder(Base):
    __tablename__ = "payment_orders"

    id = Column(Integer, primary_key=True)
    buyer_user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    payment_no = Column(String(64), unique=True, index=True, nullable=False)
    payment_type = Column(String(50), default="wallet_topup", nullable=False)
    amount_cny = Column(Float, nullable=False)
    currency = Column(String(16), default="CNY", nullable=False)
    status = Column(String(50), default="pending", nullable=False)
    channel = Column(String(50), default="manual", nullable=False)
    subject = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    third_party_txn_id = Column(String(255), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    expired_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class PaymentTransaction(Base):
    __tablename__ = "payment_transactions"

    id = Column(Integer, primary_key=True)
    payment_order_id = Column(Integer, ForeignKey("payment_orders.id"), index=True, nullable=False)
    buyer_user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    transaction_type = Column(String(50), nullable=False)
    amount_cny = Column(Float, nullable=False)
    status = Column(String(50), nullable=False)
    channel = Column(String(50), nullable=False)
    reference_no = Column(String(255), nullable=False)
    detail = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
