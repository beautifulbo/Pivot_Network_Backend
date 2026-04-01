from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_node_token, get_current_user
from app.api.routes import platform as platform_api
from app.core.db import get_db
from app.models.identity import NodeRegistrationToken, User
from app.schemas.platform.runtime import (
    CodexRuntimeBootstrapResponse,
    WireGuardBootstrapRequest,
    WireGuardBootstrapResponse,
)
from app.services.activity import log_activity
from app.services.platform_nodes import get_node_for_token
from app.services.runtime_bootstrap import (
    RuntimeBootstrapError,
    build_codex_runtime_bootstrap,
    build_wireguard_bootstrap,
)
from app.services.wireguard_server import WireGuardServerError

router = APIRouter()


@router.get("/runtime/codex", response_model=CodexRuntimeBootstrapResponse)
def get_codex_runtime_bootstrap(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CodexRuntimeBootstrapResponse:
    try:
        bootstrap = build_codex_runtime_bootstrap(platform_api.settings)
    except RuntimeBootstrapError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    log_activity(
        db,
        seller_user_id=current_user.id,
        event_type="codex_runtime_issued",
        summary="Issued CodeX runtime bootstrap",
        metadata={"auth_source": bootstrap["auth_source"], "model": bootstrap["model"]},
    )
    db.commit()
    return CodexRuntimeBootstrapResponse(**bootstrap)


@router.post("/nodes/wireguard/bootstrap", response_model=WireGuardBootstrapResponse)
def create_wireguard_bootstrap(
    payload: WireGuardBootstrapRequest,
    node_token: NodeRegistrationToken = Depends(get_current_node_token),
    db: Session = Depends(get_db),
) -> WireGuardBootstrapResponse:
    node = get_node_for_token(db, node_token, payload.node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node is not registered.")

    try:
        bootstrap = build_wireguard_bootstrap(platform_api.settings, node, payload.client_public_key)
    except RuntimeBootstrapError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    if platform_api.settings.WIREGUARD_SERVER_SSH_ENABLED:
        try:
            apply_result = platform_api.apply_server_peer(
                platform_api.settings,
                public_key=payload.client_public_key,
                client_address=bootstrap["client_address"],
                persistent_keepalive=bootstrap["persistent_keepalive"],
            )
        except WireGuardServerError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
        bootstrap["server_peer_apply_required"] = False
        bootstrap["server_peer_apply_status"] = "applied"
        bootstrap["server_peer_apply_error"] = None
        bootstrap["activation_mode"] = "server_peer_applied"
    else:
        apply_result = None
        bootstrap["server_peer_apply_status"] = "pending_manual_apply"
        bootstrap["server_peer_apply_error"] = None

    log_activity(
        db,
        seller_user_id=node_token.user_id,
        node_id=node.id,
        event_type="wireguard_profile_issued",
        summary=f"Issued WireGuard profile for {node.hostname}",
        metadata={
            "node_key": node.node_key,
            "client_public_key": payload.client_public_key,
            "client_address": bootstrap["client_address"],
            "server_peer_apply_status": bootstrap["server_peer_apply_status"],
            "server_peer_applied": not bootstrap["server_peer_apply_required"],
            "server_peer_apply_runtime_ok": apply_result["ok"] if apply_result is not None else False,
        },
    )
    db.commit()
    return WireGuardBootstrapResponse(**bootstrap)
