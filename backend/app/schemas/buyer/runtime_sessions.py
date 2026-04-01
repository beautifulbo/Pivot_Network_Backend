from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class BuyerRuntimeSessionCreateRequest(BaseModel):
    seller_node_key: str | None = None
    offer_id: int | None = None
    session_mode: str = "code_run"
    source_type: str = "inline_code"
    runtime_image: str = "python:3.12-alpine"
    code_filename: str = "main.py"
    code_content: str = Field(default="", max_length=200_000)
    archive_filename: str | None = None
    archive_content_base64: str = ""
    source_ref: str | None = None
    working_dir: str | None = None
    run_command: list[str] | None = None
    entry_command: list[str] | None = None
    requested_duration_minutes: int = Field(default=30, ge=1, le=720)


class BuyerRuntimeSessionCreateResponse(BaseModel):
    session_id: int
    offer_id: int | None = None
    connect_code: str
    expires_at: datetime
    seller_node_key: str
    runtime_image: str
    session_mode: str
    source_type: str
    network_mode: str
    gateway_protocol: str | None = None
    gateway_port: int | None = None


class BuyerRuntimeSessionRedeemRequest(BaseModel):
    connect_code: str


class BuyerRuntimeSessionRedeemResponse(BaseModel):
    session_id: int
    session_token: str
    access_mode: str
    network_mode: str
    relay_endpoint: str
    runtime_image: str
    status: str
    gateway_required: bool
    gateway_protocol: str | None = None
    gateway_port: int | None = None
    supported_features: list[str] = Field(default_factory=list)


class BuyerRuntimeSessionStatusResponse(BaseModel):
    session_id: int
    offer_id: int | None = None
    seller_node_key: str
    runtime_image: str
    source_type: str
    code_filename: str
    session_mode: str
    network_mode: str
    buyer_wireguard_client_address: str | None = None
    seller_wireguard_target: str | None = None
    status: str
    service_name: str
    gateway_service_name: str | None = None
    gateway_protocol: str | None = None
    gateway_port: int | None = None
    gateway_status: str | None = None
    gateway_last_seen_at: datetime | None = None
    supported_features: list[str] = Field(default_factory=list)
    connect_source: str | None = None
    relay_endpoint: str
    current_hourly_price_cny: float | None = None
    accrued_usage_cny: float = 0.0
    logs: str
    created_at: datetime
    started_at: datetime | None
    expires_at: datetime | None
    ended_at: datetime | None


class BuyerRuntimeSessionStopResponse(BaseModel):
    session_id: int
    status: str


class BuyerRuntimeSessionRenewRequest(BaseModel):
    additional_minutes: int = Field(default=30, ge=1, le=720)


class BuyerRuntimeSessionRenewResponse(BaseModel):
    session_id: int
    status: str
    expires_at: datetime | None


class BuyerRuntimeSessionWireGuardBootstrapRequest(BaseModel):
    client_public_key: str = Field(min_length=16)


class BuyerRuntimeSessionWireGuardBootstrapResponse(BaseModel):
    session_id: int
    interface_name: str
    client_public_key: str
    client_address: str
    server_endpoint_host: str
    server_endpoint_port: int
    server_public_key: str
    allowed_ips: str
    dns: str | None = None
    persistent_keepalive: int
    network_cidr: str
    seller_wireguard_target: str | None = None
    expires_at: datetime | None = None


class BuyerRuntimeSessionGatewayHandshakeRequest(BaseModel):
    session_token: str = Field(min_length=16)


class BuyerRuntimeSessionGatewayHandshakeResponse(BaseModel):
    session_id: int
    gateway_service_name: str
    gateway_protocol: str
    gateway_host: str
    gateway_port: int
    handshake_mode: str
    supported_features: list[str] = Field(default_factory=list)
    seller_wireguard_target: str | None = None
    expires_at: datetime | None = None


class BuyerRuntimeSessionReportRequest(BaseModel):
    session_token: str
    status: str
    logs: str = ""
    exit_code: int | None = None
