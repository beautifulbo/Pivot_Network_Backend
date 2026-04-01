from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text

from app.models.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RuntimeAccessSession(Base):
    __tablename__ = "runtime_access_sessions"

    id = Column(Integer, primary_key=True)
    buyer_user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    seller_node_id = Column(Integer, ForeignKey("nodes.id"), index=True, nullable=False)
    image_artifact_id = Column(Integer, ForeignKey("image_artifacts.id"), nullable=True, index=True)
    image_offer_id = Column(Integer, ForeignKey("image_offers.id"), nullable=True, index=True)
    runtime_image = Column(String(255), nullable=False)
    source_type = Column(String(50), default="inline_code", nullable=False)
    source_ref = Column(String(500), nullable=True)
    working_dir = Column(String(255), nullable=True)
    code_filename = Column(String(255), nullable=False)
    code_sha256 = Column(String(128), nullable=False)
    service_name = Column(String(255), unique=True, index=True, nullable=False)
    config_name = Column(String(255), unique=True, index=True, nullable=False)
    gateway_service_name = Column(String(255), unique=True, index=True, nullable=True)
    gateway_protocol = Column(String(50), default="http", nullable=False)
    gateway_port = Column(Integer, nullable=True)
    gateway_status = Column(String(50), default="pending", nullable=False)
    gateway_last_seen_at = Column(DateTime(timezone=True), nullable=True)
    access_scope = Column(JSON, default=dict, nullable=False)
    connect_source = Column(String(50), default="legacy_runtime_session", nullable=False)
    connect_code = Column(String(255), unique=True, index=True, nullable=False)
    session_token = Column(String(255), unique=True, index=True, nullable=False)
    network_mode = Column(String(50), default="wireguard", nullable=False)
    buyer_wireguard_public_key = Column(String(255), nullable=True)
    buyer_wireguard_client_address = Column(String(100), nullable=True)
    seller_wireguard_target = Column(String(100), nullable=True)
    status = Column(String(50), default="created", nullable=False)
    command = Column(JSON, default=list, nullable=False)
    last_logs = Column(Text, nullable=True)
    billed_through = Column(DateTime(timezone=True), nullable=True)
    accrued_usage_cny = Column(Float, default=0.0, nullable=False)
    last_hourly_price_cny = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)


class UsageCharge(Base):
    __tablename__ = "usage_charges"

    id = Column(Integer, primary_key=True)
    buyer_user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    session_id = Column(Integer, ForeignKey("runtime_access_sessions.id"), index=True, nullable=False)
    offer_id = Column(Integer, ForeignKey("image_offers.id"), index=True, nullable=False)
    price_snapshot_id = Column(Integer, ForeignKey("image_offer_price_snapshots.id"), nullable=True, index=True)
    billing_hour_start = Column(DateTime(timezone=True), nullable=False)
    billing_hour_end = Column(DateTime(timezone=True), nullable=False)
    hourly_price_cny = Column(Float, nullable=False)
    charged_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    ledger_id = Column(Integer, nullable=True, index=True)
