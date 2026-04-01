from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class BuyerCatalogOfferResponse(BaseModel):
    offer_id: int
    seller_node_key: str
    repository: str
    tag: str
    runtime_image_ref: str
    offer_status: str
    probe_status: str
    current_billable_price_cny_per_hour: float | None
    pricing_stale_at: datetime | None
    probe_measured_capabilities: dict[str, Any]
