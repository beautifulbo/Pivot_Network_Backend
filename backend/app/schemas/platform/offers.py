from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ImageOfferCreateRequest(BaseModel):
    image_artifact_id: int


class ImageOfferProbeRequest(BaseModel):
    timeout_seconds: int = Field(default=180, ge=30, le=600)


class ImageOfferResponse(BaseModel):
    id: int
    seller_user_id: int
    node_id: int
    image_artifact_id: int
    repository: str
    tag: str
    digest: str | None
    runtime_image_ref: str
    offer_status: str
    probe_status: str
    probe_measured_capabilities: dict[str, Any]
    pricing_error: str | None
    current_reference_price_cny_per_hour: float | None
    current_billable_price_cny_per_hour: float | None
    current_price_snapshot_id: int | None
    last_probed_at: datetime | None
    last_priced_at: datetime | None
    pricing_stale_at: datetime | None
    created_at: datetime
    updated_at: datetime
