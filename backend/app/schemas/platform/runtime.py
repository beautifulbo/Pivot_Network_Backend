from __future__ import annotations

from pydantic import BaseModel, Field


class CodexProviderResponse(BaseModel):
    name: str
    base_url: str
    wire_api: str
    requires_openai_auth: bool


class CodexRuntimeAuthResponse(BaseModel):
    OPENAI_API_KEY: str


class CodexRuntimeBootstrapResponse(BaseModel):
    model_provider: str
    model: str
    review_model: str
    model_reasoning_effort: str
    disable_response_storage: bool
    network_access: str
    windows_wsl_setup_acknowledged: bool
    model_context_window: int
    model_auto_compact_token_limit: int
    provider: CodexProviderResponse
    auth: CodexRuntimeAuthResponse
    auth_source: str


class WireGuardBootstrapRequest(BaseModel):
    node_id: str
    client_public_key: str = Field(min_length=16)


class WireGuardBootstrapResponse(BaseModel):
    node_id: str
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
    activation_mode: str
    server_peer_apply_required: bool
    server_peer_apply_status: str | None = None
    server_peer_apply_error: str | None = None


class SwarmWorkerJoinTokenResponse(BaseModel):
    join_token: str
    manager_host: str
    manager_port: int


class SwarmRemoteStateResponse(BaseModel):
    state: str | None
    node_id: str | None
    node_addr: str | None
    control_available: bool
    nodes: int | None = None
    managers: int | None = None
    cluster_id: str | None = None


class SwarmRemoteOverviewResponse(BaseModel):
    manager_host: str
    manager_port: int
    swarm: SwarmRemoteStateResponse
    node_list: str
    service_list: str
