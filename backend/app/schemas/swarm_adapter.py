from __future__ import annotations

from pydantic import BaseModel


class SwarmValidateRuntimeImageRequest(BaseModel):
    service_name: str
    placement_constraint: str
    runtime_image: str
    timeout_seconds: int = 120


class SwarmProbeNodeCapabilitiesRequest(BaseModel):
    service_name: str
    placement_constraint: str
    probe_image: str
    timeout_seconds: int = 180


class SwarmInspectServiceRequest(BaseModel):
    service_name: str


class SwarmRemoveRuntimeSessionBundleRequest(BaseModel):
    runtime_service_name: str
    config_name: str
    gateway_service_name: str | None = None


class SwarmCreateRuntimeSessionBundleRequest(BaseModel):
    session_id: int
    buyer_user_id: int
    seller_node_id: int
    runtime_service_name: str
    config_name: str
    gateway_service_name: str
    gateway_port: int
    placement_constraint: str
    runtime_image: str
    session_mode: str
    entry_command: list[str]
    report_url: str
    session_token: str
    code_filename: str = "main.py"
    code_content: str = ""
    source_type: str = "inline_code"
    archive_filename: str | None = None
    archive_content_base64: str = ""
    working_dir: str | None = None
    run_command: list[str] | None = None


class SwarmInspectRuntimeSessionBundleRequest(BaseModel):
    runtime_service_name: str
    gateway_service_name: str | None = None


class WireGuardApplyPeerRequest(BaseModel):
    public_key: str
    client_address: str
    persistent_keepalive: int


class WireGuardRemovePeerRequest(BaseModel):
    public_key: str
