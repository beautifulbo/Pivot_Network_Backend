from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.identity import NodeRegistrationToken
from app.models.seller import Node
from app.schemas.platform.nodes import NodeHeartbeatRequest, NodeRegisterRequest


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def extract_node_wireguard_target(node: Node) -> str | None:
    capabilities = node.capabilities or {}
    interfaces = capabilities.get("interfaces") or {}
    for interface_name, entries in interfaces.items():
        if interface_name != "wg-seller":
            continue
        for entry in entries:
            if str(entry.get("family")) == "2" and entry.get("address"):
                return str(entry["address"])
    return None


def get_node_for_token(db: Session, node_token: NodeRegistrationToken, node_key: str) -> Node | None:
    statement = select(Node).where(Node.node_key == node_key, Node.seller_user_id == node_token.user_id)
    return db.scalar(statement)


def create_or_update_registered_node(
    db: Session,
    *,
    node_token: NodeRegistrationToken,
    payload: NodeRegisterRequest,
) -> Node:
    node = get_node_for_token(db, node_token, payload.node_id)
    if node is None:
        node = Node(
            seller_user_id=node_token.user_id,
            node_key=payload.node_id,
            device_fingerprint=payload.device_fingerprint,
            hostname=payload.hostname,
            system=payload.system,
            machine=payload.machine,
            status="available",
            shared_percent_preference=payload.shared_percent_preference,
            node_class=payload.node_class,
            capabilities=payload.capabilities,
            seller_intent=payload.seller_intent,
            docker_status=payload.docker_status,
            swarm_state=payload.swarm_state,
            last_heartbeat_at=utcnow(),
        )
        db.add(node)
    else:
        node.device_fingerprint = payload.device_fingerprint
        node.hostname = payload.hostname
        node.system = payload.system
        node.machine = payload.machine
        node.shared_percent_preference = payload.shared_percent_preference
        node.node_class = payload.node_class
        node.capabilities = payload.capabilities
        node.seller_intent = payload.seller_intent
        node.docker_status = payload.docker_status
        node.swarm_state = payload.swarm_state
        node.status = "available"
        node.last_heartbeat_at = utcnow()
    return node


def apply_node_heartbeat(
    db: Session,
    *,
    node_token: NodeRegistrationToken,
    payload: NodeHeartbeatRequest,
) -> Node | None:
    node = get_node_for_token(db, node_token, payload.node_id)
    if node is None:
        return None
    node.status = payload.status
    node.docker_status = payload.docker_status
    node.swarm_state = payload.swarm_state
    if payload.capabilities is not None:
        node.capabilities = payload.capabilities
    node.last_heartbeat_at = utcnow()
    return node


def list_seller_nodes(db: Session, seller_user_id: int) -> list[Node]:
    return db.scalars(select(Node).where(Node.seller_user_id == seller_user_id).order_by(Node.id)).all()


def get_seller_node(db: Session, *, seller_user_id: int, node_id: int) -> Node | None:
    return db.scalar(select(Node).where(Node.id == node_id, Node.seller_user_id == seller_user_id))
