from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_node_token, get_current_user
from app.api.routes.platform.common import serialize_node, serialize_node_token
from app.core.db import get_db
from app.models.identity import NodeRegistrationToken, User
from app.schemas.platform.nodes import (
    IssueNodeTokenRequest,
    NodeHeartbeatRequest,
    NodeRegisterRequest,
    NodeResponse,
    NodeTokenListResponse,
    NodeTokenResponse,
)
from app.services.activity import log_activity
from app.services.auth import issue_node_registration_token
from app.services.platform_nodes import (
    apply_node_heartbeat,
    create_or_update_registered_node,
    get_seller_node,
    list_seller_nodes,
)

router = APIRouter()


@router.post("/node-registration-token", response_model=NodeTokenResponse)
def create_node_registration_token(
    payload: IssueNodeTokenRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NodeTokenResponse:
    token = issue_node_registration_token(db, current_user, payload.label, payload.expires_hours)
    log_activity(
        db,
        seller_user_id=current_user.id,
        event_type="node_token_issued",
        summary="Issued node registration token",
        detail=payload.label,
        metadata={"label": payload.label, "expires_hours": payload.expires_hours},
    )
    db.commit()
    return NodeTokenResponse(
        node_registration_token=token.token,
        expires_at=token.expires_at,
        label=token.label,
    )


@router.post("/nodes/register", response_model=NodeResponse)
def register_node(
    payload: NodeRegisterRequest,
    node_token: NodeRegistrationToken = Depends(get_current_node_token),
    db: Session = Depends(get_db),
) -> NodeResponse:
    if node_token.used_node_key and node_token.used_node_key != payload.node_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Node registration token is already bound to another node.",
        )

    node = create_or_update_registered_node(db, node_token=node_token, payload=payload)
    node_token.used_node_key = payload.node_id
    node_token.last_used_at = node.last_heartbeat_at
    db.flush()
    log_activity(
        db,
        seller_user_id=node_token.user_id,
        node_id=node.id,
        event_type="node_registered",
        summary=f"Registered node {payload.hostname}",
        detail=payload.seller_intent,
        metadata={"node_key": payload.node_id, "node_class": payload.node_class},
    )
    db.commit()
    db.refresh(node)
    return serialize_node(node)


@router.post("/nodes/heartbeat", response_model=NodeResponse)
def heartbeat_node(
    payload: NodeHeartbeatRequest,
    node_token: NodeRegistrationToken = Depends(get_current_node_token),
    db: Session = Depends(get_db),
) -> NodeResponse:
    node = apply_node_heartbeat(db, node_token=node_token, payload=payload)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node is not registered.")

    node_token.last_used_at = node.last_heartbeat_at
    log_activity(
        db,
        seller_user_id=node_token.user_id,
        node_id=node.id,
        event_type="node_heartbeat",
        summary=f"Heartbeat from {node.hostname}",
        metadata={"status": payload.status},
    )
    db.commit()
    db.refresh(node)
    return serialize_node(node)


@router.get("/nodes", response_model=list[NodeResponse])
def list_seller_nodes_route(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[NodeResponse]:
    return [serialize_node(node) for node in list_seller_nodes(db, current_user.id)]


@router.get("/nodes/{node_id}", response_model=NodeResponse)
def get_seller_node_route(
    node_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NodeResponse:
    node = get_seller_node(db, seller_user_id=current_user.id, node_id=node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found.")
    return serialize_node(node)


@router.get("/node-registration-tokens", response_model=list[NodeTokenListResponse])
def list_node_registration_tokens(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[NodeTokenListResponse]:
    tokens = db.scalars(
        select(NodeRegistrationToken)
        .where(NodeRegistrationToken.user_id == current_user.id)
        .order_by(NodeRegistrationToken.id.desc())
    ).all()
    return [serialize_node_token(token) for token in tokens]
