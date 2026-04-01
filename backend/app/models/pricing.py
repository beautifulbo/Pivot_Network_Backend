from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text

from app.models.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PriceFeedSnapshot(Base):
    __tablename__ = "price_feed_snapshots"

    id = Column(Integer, primary_key=True)
    provider = Column(String(50), index=True, nullable=False)
    reference_region = Column(String(100), nullable=False)
    status = Column(String(50), default="success", nullable=False)
    source_url = Column(String(1000), nullable=False)
    raw_payload = Column(JSON, default=dict, nullable=False)
    error_message = Column(Text, nullable=True)
    fetched_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class ResourceRateCard(Base):
    __tablename__ = "resource_rate_cards"

    id = Column(Integer, primary_key=True)
    status = Column(String(50), default="active", nullable=False)
    effective_hour = Column(DateTime(timezone=True), index=True, nullable=False)
    usd_cny_rate = Column(Float, nullable=False)
    cpu_price_usd_per_hour = Column(Float, nullable=False)
    ram_price_usd_per_gib_hour = Column(Float, nullable=False)
    gpu_price_usd_per_hour = Column(JSON, default=dict, nullable=False)
    source_summary = Column(JSON, default=dict, nullable=False)
    stale_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class ImageOfferPriceSnapshot(Base):
    __tablename__ = "image_offer_price_snapshots"

    id = Column(Integer, primary_key=True)
    offer_id = Column(Integer, ForeignKey("image_offers.id"), index=True, nullable=False)
    resource_rate_card_id = Column(Integer, ForeignKey("resource_rate_cards.id"), index=True, nullable=False)
    effective_hour = Column(DateTime(timezone=True), index=True, nullable=False)
    reference_price_cny_per_hour = Column(Float, nullable=False)
    billable_price_cny_per_hour = Column(Float, nullable=False)
    price_components = Column(JSON, default=dict, nullable=False)
    probe_measured_capabilities = Column(JSON, default=dict, nullable=False)
    stale_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
