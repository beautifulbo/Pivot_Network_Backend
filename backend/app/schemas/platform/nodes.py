from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.platform.images import ImageArtifactResponse


class IssueNodeTokenRequest(BaseModel):
    label: str | None = None
    expires_hours: int = Field(default=72, ge=1, le=720)


class NodeTokenResponse(BaseModel):
    node_registration_token: str
    expires_at: datetime
    label: str | None


class NodeTokenListResponse(BaseModel):
    id: int
    label: str | None
    expires_at: datetime
    revoked: bool
    used_node_key: str | None
    last_used_at: datetime | None
    created_at: datetime


class NodeRegisterRequest(BaseModel):
    node_id: str
    device_fingerprint: str
    hostname: str
    system: str
    machine: str
    shared_percent_preference: int = Field(default=10, ge=1, le=100)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    seller_intent: str | None = None
    docker_status: str | None = None
    swarm_state: str | None = None
    node_class: str | None = None


class NodeHeartbeatRequest(BaseModel):
    node_id: str
    status: str = "available"
    docker_status: str | None = None
    swarm_state: str | None = None
    capabilities: dict[str, Any] | None = None


class NodeResponse(BaseModel):
    id: int
    seller_user_id: int
    node_key: str
    device_fingerprint: str
    hostname: str
    system: str
    machine: str
    status: str
    shared_percent_preference: int
    node_class: str | None
    capabilities: dict[str, Any]
    seller_intent: str | None
    docker_status: str | None
    swarm_state: str | None
    ready_for_registry_push: bool
    wireguard_ready_for_buyer: bool
    wireguard_target: str | None = None
    needs_docker_setup: bool
    needs_wireguard_setup: bool
    needs_codex_setup: bool
    needs_node_token: bool
    last_heartbeat_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PlatformOverviewResponse(BaseModel):
    seller_id: int
    node_count: int
    image_count: int
    nodes: list[NodeResponse]
    images: list[ImageArtifactResponse]
