from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class BuyerOrderCreateRequest(BaseModel):
    offer_id: int
    requested_duration_minutes: int = Field(default=60, ge=1, le=720)


class BuyerOrderRedeemRequest(BaseModel):
    license_token: str


class BuyerOrderResponse(BaseModel):
    id: int
    offer_id: int
    seller_node_key: str
    repository: str
    tag: str
    runtime_image_ref: str
    requested_duration_minutes: int
    issued_hourly_price_cny: float
    order_status: str
    license_token: str
    license_redeemed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class BuyerOrderRedeemResponse(BaseModel):
    order_id: int
    offer_id: int
    seller_node_key: str
    runtime_image_ref: str
    requested_duration_minutes: int
    issued_hourly_price_cny: float
    order_status: str
    license_token: str


class BuyerOrderStartSessionResponse(BaseModel):
    session_id: int
    order_id: int
    offer_id: int
    connect_code: str
    expires_at: datetime
    seller_node_key: str
    runtime_image: str
    network_mode: str
    gateway_protocol: str | None = None
    gateway_port: int | None = None
