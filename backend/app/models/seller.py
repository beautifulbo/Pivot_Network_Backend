from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.models.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Node(Base):
    __tablename__ = "nodes"

    id = Column(Integer, primary_key=True)
    seller_user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    node_key = Column(String(255), unique=True, index=True, nullable=False)
    device_fingerprint = Column(String(255), index=True, nullable=False)
    hostname = Column(String(255), nullable=False)
    system = Column(String(100), nullable=False)
    machine = Column(String(100), nullable=False)
    status = Column(String(50), default="available", nullable=False)
    shared_percent_preference = Column(Integer, default=10, nullable=False)
    node_class = Column(String(100), nullable=True)
    capabilities = Column(JSON, default=dict, nullable=False)
    seller_intent = Column(Text, nullable=True)
    docker_status = Column(Text, nullable=True)
    swarm_state = Column(Text, nullable=True)
    last_heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    images = relationship(
        "ImageArtifact",
        back_populates="node",
        cascade="all, delete-orphan",
    )


class ImageArtifact(Base):
    __tablename__ = "image_artifacts"

    id = Column(Integer, primary_key=True)
    seller_user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    node_id = Column(Integer, ForeignKey("nodes.id"), nullable=True, index=True)
    repository = Column(String(255), nullable=False)
    tag = Column(String(255), nullable=False)
    digest = Column(String(255), nullable=True)
    registry = Column(String(255), nullable=False)
    source_image = Column(String(255), nullable=True)
    status = Column(String(50), default="uploaded", nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    node = relationship("Node", back_populates="images")


class ImageOffer(Base):
    __tablename__ = "image_offers"

    id = Column(Integer, primary_key=True)
    seller_user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    node_id = Column(Integer, ForeignKey("nodes.id"), index=True, nullable=False)
    image_artifact_id = Column(Integer, ForeignKey("image_artifacts.id"), index=True, nullable=False)
    repository = Column(String(255), nullable=False)
    tag = Column(String(255), nullable=False)
    digest = Column(String(255), nullable=True)
    runtime_image_ref = Column(String(500), nullable=False)
    offer_status = Column(String(50), default="draft", nullable=False)
    probe_status = Column(String(50), default="pending", nullable=False)
    probe_measured_capabilities = Column(JSON, default=dict, nullable=False)
    pricing_error = Column(Text, nullable=True)
    current_reference_price_cny_per_hour = Column(Float, nullable=True)
    current_billable_price_cny_per_hour = Column(Float, nullable=True)
    current_price_snapshot_id = Column(Integer, nullable=True, index=True)
    last_probed_at = Column(DateTime(timezone=True), nullable=True)
    last_priced_at = Column(DateTime(timezone=True), nullable=True)
    pricing_stale_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
