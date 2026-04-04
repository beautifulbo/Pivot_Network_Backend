from __future__ import annotations

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, status

from app.core.config import Settings, settings
from app.schemas.swarm_adapter import (
    SwarmCreateRuntimeSessionBundleRequest,
    SwarmInspectRuntimeSessionBundleRequest,
    SwarmInspectServiceRequest,
    SwarmProbeNodeCapabilitiesRequest,
    SwarmRemoveRuntimeSessionBundleRequest,
    SwarmValidateRuntimeImageRequest,
    WireGuardApplyPeerRequest,
    WireGuardRemovePeerRequest,
)
from app.services import swarm_adapter
from app.services.swarm_manager import (
    SwarmManagerError,
    create_runtime_session_bundle,
    get_manager_overview,
    get_worker_join_token,
    inspect_runtime_session_bundle,
    inspect_swarm_service,
    probe_node_capabilities_on_node,
    remove_runtime_session_bundle,
    validate_runtime_image_on_node,
)
from app.services.wireguard_server import WireGuardServerError, apply_server_peer, remove_server_peer


app = FastAPI(title="Pivot Docker Swarm Adapter", version="0.1.0")
router = APIRouter()
protected_router = APIRouter()


def require_adapter_token(
    x_pivot_adapter_token: str | None = Header(default=None),
) -> None:
    expected = settings.SWARM_ADAPTER_TOKEN.strip()
    if expected and x_pivot_adapter_token != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="adapter_auth_failed")


def _local_settings() -> Settings:
    return settings.model_copy(
        update={
            "SWARM_ADAPTER_BASE_URL": "",
            "SWARM_MANAGER_LOCAL_MODE": True,
            "WIREGUARD_SERVER_LOCAL_MODE": True,
            "WIREGUARD_SERVER_SSH_ENABLED": False,
        }
    )


@router.get("/health")
def read_health() -> dict[str, object]:
    try:
        payload = swarm_adapter.get_swarm_health()
    except swarm_adapter.SwarmAdapterUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    payload["adapter"] = "docker-swarm-api"
    return payload


@protected_router.get("/swarm/overview", dependencies=[Depends(require_adapter_token)])
def read_swarm_overview() -> dict[str, object]:
    try:
        return get_manager_overview(_local_settings())
    except SwarmManagerError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@protected_router.get("/swarm/worker-join-token", dependencies=[Depends(require_adapter_token)])
def read_worker_join_token() -> dict[str, object]:
    try:
        return get_worker_join_token(_local_settings())
    except SwarmManagerError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@protected_router.post("/swarm/runtime-images/validate", dependencies=[Depends(require_adapter_token)])
def validate_runtime_image(payload: SwarmValidateRuntimeImageRequest) -> dict[str, object]:
    try:
        return validate_runtime_image_on_node(_local_settings(), **payload.model_dump())
    except SwarmManagerError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@protected_router.post("/swarm/nodes/probe", dependencies=[Depends(require_adapter_token)])
def probe_node_capabilities(payload: SwarmProbeNodeCapabilitiesRequest) -> dict[str, object]:
    try:
        return probe_node_capabilities_on_node(_local_settings(), **payload.model_dump())
    except SwarmManagerError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@protected_router.post("/swarm/services/inspect", dependencies=[Depends(require_adapter_token)])
def inspect_service(payload: SwarmInspectServiceRequest) -> dict[str, object]:
    try:
        return inspect_swarm_service(_local_settings(), **payload.model_dump())
    except SwarmManagerError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@protected_router.post("/swarm/runtime-session-bundles/create", dependencies=[Depends(require_adapter_token)])
def create_bundle(payload: SwarmCreateRuntimeSessionBundleRequest) -> dict[str, object]:
    try:
        return create_runtime_session_bundle(_local_settings(), **payload.model_dump())
    except SwarmManagerError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@protected_router.post("/swarm/runtime-session-bundles/inspect", dependencies=[Depends(require_adapter_token)])
def inspect_bundle(payload: SwarmInspectRuntimeSessionBundleRequest) -> dict[str, object]:
    try:
        return inspect_runtime_session_bundle(_local_settings(), **payload.model_dump())
    except SwarmManagerError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@protected_router.post("/swarm/runtime-session-bundles/remove", dependencies=[Depends(require_adapter_token)])
def remove_bundle(payload: SwarmRemoveRuntimeSessionBundleRequest) -> dict[str, object]:
    try:
        return remove_runtime_session_bundle(_local_settings(), **payload.model_dump())
    except SwarmManagerError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@protected_router.post("/wireguard/peers/apply", dependencies=[Depends(require_adapter_token)])
def apply_peer(payload: WireGuardApplyPeerRequest) -> dict[str, object]:
    try:
        return apply_server_peer(_local_settings(), **payload.model_dump())
    except WireGuardServerError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@protected_router.post("/wireguard/peers/remove", dependencies=[Depends(require_adapter_token)])
def remove_peer(payload: WireGuardRemovePeerRequest) -> dict[str, object]:
    try:
        return remove_server_peer(_local_settings(), **payload.model_dump())
    except WireGuardServerError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


app.include_router(router)
app.include_router(protected_router)
