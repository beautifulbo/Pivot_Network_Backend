from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routes import buyer as buyer_api
from app.core.db import get_db
from app.models.buyer import BuyerOrder
from app.models.identity import User
from app.models.runtime import RuntimeAccessSession
from app.models.seller import ImageOffer, Node
from app.schemas.buyer.orders import BuyerOrderStartSessionResponse
from app.schemas.buyer.runtime_sessions import (
    BuyerRuntimeSessionCreateRequest,
    BuyerRuntimeSessionCreateResponse,
    BuyerRuntimeSessionGatewayHandshakeRequest,
    BuyerRuntimeSessionGatewayHandshakeResponse,
    BuyerRuntimeSessionRedeemRequest,
    BuyerRuntimeSessionRedeemResponse,
    BuyerRuntimeSessionRenewRequest,
    BuyerRuntimeSessionRenewResponse,
    BuyerRuntimeSessionReportRequest,
    BuyerRuntimeSessionStatusResponse,
    BuyerRuntimeSessionStopResponse,
    BuyerRuntimeSessionWireGuardBootstrapRequest,
    BuyerRuntimeSessionWireGuardBootstrapResponse,
)
from app.services.activity import log_activity
from app.services.buyer_orders import get_buyer_order, redeem_order_if_needed
from app.services.platform_nodes import extract_node_wireguard_target
from app.services.runtime_bootstrap import RuntimeBootstrapError, build_buyer_wireguard_bootstrap
from app.services.runtime_sessions import (
    TERMINAL_SESSION_STATES,
    expire_runtime_session,
    renew_runtime_session,
)
from app.services.swarm_manager import SwarmManagerError
from app.services.wireguard_server import WireGuardServerError, remove_server_peer

router = APIRouter()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _runtime_session_status_from_task(task: dict) -> str:
    state = str(task.get("CurrentState") or "").lower()
    desired = str(task.get("DesiredState") or "").lower()
    if "running" in state:
        return "running"
    if "complete" in state or "shutdown" in desired:
        return "completed"
    if "failed" in state or "rejected" in state:
        return "failed"
    return "starting"


def _gateway_status_from_task(task: dict) -> str:
    state = str(task.get("CurrentState") or "").lower()
    desired = str(task.get("DesiredState") or "").lower()
    if "running" in state:
        return "online"
    if "complete" in state or "shutdown" in desired:
        return "stopped"
    if "failed" in state or "rejected" in state:
        return "failed"
    return "starting"


def _session_mode(session: RuntimeAccessSession) -> str:
    return "shell" if session.code_filename == "__shell__" else "code_run"


def _relay_endpoint(session_id: int) -> str:
    return f"relay://buyer-runtime-session/{session_id}"


def _placement_constraint_for_node(node: Node) -> str:
    match = re.search(r"node_id=([a-z0-9]+)", node.swarm_state or "", re.IGNORECASE)
    if match:
        return f"node.id=={match.group(1)}"
    return f"node.hostname=={node.hostname}"


def _runtime_callback_base_url(request: Request) -> str:
    parts = urlsplit(str(request.base_url))
    hostname = parts.hostname or "127.0.0.1"
    if hostname in {"127.0.0.1", "localhost"}:
        host = "host.docker.internal"
        netloc = f"{host}:{parts.port}" if parts.port else host
        return urlunsplit((parts.scheme, netloc, "", "", "")).rstrip("/")
    return str(request.base_url).rstrip("/")


def _get_runtime_session_for_buyer(db: Session, session_id: int, buyer_id: int) -> RuntimeAccessSession | None:
    statement = select(RuntimeAccessSession).where(
        RuntimeAccessSession.id == session_id,
        RuntimeAccessSession.buyer_user_id == buyer_id,
    )
    return db.scalar(statement)


def _require_node_wireguard_ready(node: Node) -> str:
    gateway_target = extract_node_wireguard_target(node)
    if not gateway_target:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="seller_node_wireguard_not_ready",
        )
    return gateway_target


def _default_access_scope() -> dict[str, object]:
    features = [item.strip() for item in buyer_api.settings.SESSION_GATEWAY_SUPPORTED_FEATURES.split(",") if item.strip()]
    return {
        "supported_features": features,
        "handshake_mode": buyer_api.settings.SESSION_GATEWAY_HANDSHAKE_MODE,
    }


def _session_supported_features(session: RuntimeAccessSession) -> list[str]:
    access_scope = session.access_scope or {}
    if not isinstance(access_scope, dict):
        return []
    features = access_scope.get("supported_features")
    if not isinstance(features, list):
        return []
    return [str(item) for item in features]


def _session_handshake_mode(session: RuntimeAccessSession) -> str:
    access_scope = session.access_scope or {}
    if not isinstance(access_scope, dict):
        return buyer_api.settings.SESSION_GATEWAY_HANDSHAKE_MODE
    mode = access_scope.get("handshake_mode")
    return str(mode) if mode else buyer_api.settings.SESSION_GATEWAY_HANDSHAKE_MODE


def _session_gateway_required(session: RuntimeAccessSession) -> bool:
    return bool(session.gateway_service_name and session.gateway_protocol and session.gateway_port)


def _entry_command_for_session(
    *,
    session_mode: str,
    code_filename: str,
    entry_command: list[str] | None,
) -> list[str]:
    if entry_command:
        return entry_command
    if session_mode == "shell":
        return ["sh", "-lc", "while true; do sleep 3600; done"]
    return ["python", f"/workspace/{code_filename}"]


def _serialize_runtime_session_create(
    session: RuntimeAccessSession,
    *,
    seller_node_key: str,
) -> BuyerRuntimeSessionCreateResponse:
    return BuyerRuntimeSessionCreateResponse(
        session_id=session.id,
        offer_id=session.image_offer_id,
        connect_code=session.connect_code,
        expires_at=session.expires_at,
        seller_node_key=seller_node_key,
        runtime_image=session.runtime_image,
        session_mode=_session_mode(session),
        source_type=session.source_type,
        network_mode=session.network_mode,
        gateway_protocol=session.gateway_protocol,
        gateway_port=session.gateway_port,
    )


def _serialize_order_start_session(
    session: RuntimeAccessSession,
    *,
    order: BuyerOrder,
    seller_node_key: str,
) -> BuyerOrderStartSessionResponse:
    return BuyerOrderStartSessionResponse(
        session_id=session.id,
        order_id=order.id,
        offer_id=order.offer_id,
        connect_code=session.connect_code,
        expires_at=session.expires_at,
        seller_node_key=seller_node_key,
        runtime_image=session.runtime_image,
        network_mode=session.network_mode,
        gateway_protocol=session.gateway_protocol,
        gateway_port=session.gateway_port,
    )


def _create_runtime_session_record(
    *,
    db: Session,
    request: Request,
    buyer_user: User,
    node: Node,
    runtime_image: str,
    requested_duration_minutes: int,
    session_mode: str,
    source_type: str,
    source_ref: str | None,
    working_dir: str | None,
    code_filename: str,
    code_sha256: str,
    code_content: str,
    archive_filename: str | None,
    archive_content_base64: str,
    run_command: list[str] | None,
    entry_command: list[str],
    image_artifact_id: int | None,
    image_offer_id: int | None,
    connect_source: str,
) -> RuntimeAccessSession:
    connect_code = secrets.token_urlsafe(10)
    session_token = secrets.token_urlsafe(24)
    expires_at = utcnow() + timedelta(minutes=requested_duration_minutes)
    temp_suffix = secrets.token_hex(6)
    session = RuntimeAccessSession(
        buyer_user_id=buyer_user.id,
        seller_node_id=node.id,
        image_artifact_id=image_artifact_id,
        image_offer_id=image_offer_id,
        runtime_image=runtime_image,
        source_type=source_type,
        source_ref=source_ref,
        working_dir=working_dir,
        code_filename=code_filename,
        code_sha256=code_sha256,
        service_name=f"runtime-pending-{temp_suffix}",
        config_name=f"runtime-config-pending-{temp_suffix}",
        gateway_service_name=f"gateway-pending-{temp_suffix}",
        gateway_protocol=buyer_api.settings.SESSION_GATEWAY_PROTOCOL,
        gateway_port=None,
        gateway_status="pending",
        access_scope=_default_access_scope(),
        connect_source=connect_source,
        connect_code=connect_code,
        session_token=session_token,
        network_mode="wireguard",
        seller_wireguard_target=extract_node_wireguard_target(node),
        status="created",
        command=entry_command,
        expires_at=expires_at,
        accrued_usage_cny=0.0,
    )
    db.add(session)
    db.flush()

    gateway_port = buyer_api.settings.SESSION_GATEWAY_BASE_PORT + session.id
    if gateway_port > 65535:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="session_gateway_port_exhausted")

    session.service_name = f"runtime-{session.id}"
    session.config_name = f"runtime-config-{session.id}"
    session.gateway_service_name = f"gateway-{session.id}"
    session.gateway_port = gateway_port
    session.gateway_status = "creating"

    report_url = f"{_runtime_callback_base_url(request)}/api/v1/buyer/runtime-sessions/{session.id}/report"
    bundle_result = buyer_api.create_runtime_session_bundle(
        buyer_api.settings,
        session_id=session.id,
        buyer_user_id=buyer_user.id,
        seller_node_id=node.id,
        runtime_service_name=session.service_name,
        config_name=session.config_name,
        gateway_service_name=session.gateway_service_name,
        gateway_port=gateway_port,
        placement_constraint=_placement_constraint_for_node(node),
        runtime_image=runtime_image,
        session_mode=session_mode,
        entry_command=entry_command,
        report_url=report_url,
        session_token=session.session_token,
        code_filename=code_filename,
        code_content=code_content,
        source_type=source_type,
        archive_filename=archive_filename,
        archive_content_base64=archive_content_base64,
        working_dir=working_dir,
        run_command=run_command,
    )
    if not bundle_result.get("ok"):
        raise SwarmManagerError("runtime_session_bundle_create_failed")

    inspect_result = buyer_api.inspect_runtime_session_bundle(
        buyer_api.settings,
        runtime_service_name=session.service_name,
        gateway_service_name=session.gateway_service_name,
    )
    runtime_inspect = inspect_result.get("runtime", {})
    gateway_inspect = inspect_result.get("gateway", {})
    session.status = _runtime_session_status_from_task(runtime_inspect.get("current_task", {}))
    session.gateway_status = _gateway_status_from_task(gateway_inspect.get("current_task", {}))
    session.started_at = utcnow()
    session.gateway_last_seen_at = utcnow()
    session.last_logs = str(runtime_inspect.get("logs") or "")
    return session


@router.post("/runtime-sessions", response_model=BuyerRuntimeSessionCreateResponse)
def create_buyer_runtime_session(
    payload: BuyerRuntimeSessionCreateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BuyerRuntimeSessionCreateResponse:
    offer = None
    if payload.offer_id is not None:
        offer = db.get(ImageOffer, payload.offer_id)
        if offer is None or offer.offer_status != "active":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image offer not found.")
        node = db.get(Node, offer.node_id)
        if node is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Seller node not found.")
        runtime_image = offer.runtime_image_ref
    else:
        if not payload.seller_node_key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="seller_node_key is required for ad hoc sessions.",
            )
        node = db.scalar(select(Node).where(Node.node_key == payload.seller_node_key))
        if node is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Seller node not found.")
        runtime_image = payload.runtime_image
        _require_node_wireguard_ready(node)

    if node.status != "available":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Seller node is not available.")
    if payload.session_mode not in {"code_run", "shell"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported session_mode.")
    if payload.source_type not in {"inline_code", "archive"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported source_type.")
    if payload.session_mode == "code_run" and payload.source_type == "inline_code" and not payload.code_content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="code_content is required for inline_code mode.")
    if payload.session_mode == "code_run" and payload.source_type == "archive" and not payload.archive_content_base64:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="archive_content_base64 is required for archive mode.",
        )

    code_filename = "__shell__" if payload.session_mode == "shell" else payload.code_filename
    if payload.session_mode == "shell":
        code_sha256 = "shell-session"
    elif payload.source_type == "archive":
        code_sha256 = hashlib.sha256(payload.archive_content_base64.encode("utf-8")).hexdigest()
    else:
        code_sha256 = hashlib.sha256(payload.code_content.encode("utf-8")).hexdigest()
    entry_command = _entry_command_for_session(
        session_mode=payload.session_mode,
        code_filename=payload.code_filename,
        entry_command=payload.entry_command,
    )

    try:
        session = _create_runtime_session_record(
            db=db,
            request=request,
            buyer_user=current_user,
            node=node,
            runtime_image=runtime_image,
            requested_duration_minutes=payload.requested_duration_minutes,
            session_mode=payload.session_mode,
            source_type=payload.source_type,
            source_ref=payload.source_ref,
            working_dir=payload.working_dir,
            code_filename=code_filename,
            code_sha256=code_sha256,
            code_content=payload.code_content,
            archive_filename=payload.archive_filename,
            archive_content_base64=payload.archive_content_base64,
            run_command=payload.run_command,
            entry_command=entry_command,
            image_artifact_id=offer.image_artifact_id if offer else None,
            image_offer_id=offer.id if offer else None,
            connect_source="buyer_runtime_session_create",
        )
    except SwarmManagerError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    log_activity(
        db,
        seller_user_id=node.seller_user_id,
        node_id=node.id,
        event_type="buyer_runtime_session_created",
        summary=f"Created buyer runtime session bundle on {node.hostname}",
        metadata={
            "session_id": session.id,
            "buyer_user_id": current_user.id,
            "runtime_image": runtime_image,
            "service_name": session.service_name,
            "gateway_service_name": session.gateway_service_name,
            "source_type": payload.source_type,
            "offer_id": offer.id if offer else None,
        },
    )
    db.commit()
    return _serialize_runtime_session_create(session, seller_node_key=node.node_key)


@router.post("/orders/{order_id}/start-session", response_model=BuyerOrderStartSessionResponse)
def start_buyer_order_session(
    order_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BuyerOrderStartSessionResponse:
    order = get_buyer_order(db, buyer_user_id=current_user.id, order_id=order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")

    offer = db.get(ImageOffer, order.offer_id)
    node = db.get(Node, offer.node_id) if offer else None
    if offer is None or node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order offer not found.")
    if offer.offer_status != "active":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Offer is not active.")
    if node.status != "available":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Seller node is not available.")

    source_ref = f"order:{order.id}"
    existing_session = db.scalar(
        select(RuntimeAccessSession)
        .where(
            RuntimeAccessSession.buyer_user_id == current_user.id,
            RuntimeAccessSession.source_ref == source_ref,
            RuntimeAccessSession.status.not_in(TERMINAL_SESSION_STATES),
        )
        .order_by(RuntimeAccessSession.id.desc())
    )
    if existing_session is not None:
        return _serialize_order_start_session(existing_session, order=order, seller_node_key=node.node_key)

    redeem_order_if_needed(order)

    try:
        session = _create_runtime_session_record(
            db=db,
            request=request,
            buyer_user=current_user,
            node=node,
            runtime_image=offer.runtime_image_ref,
            requested_duration_minutes=order.requested_duration_minutes,
            session_mode="shell",
            source_type="licensed_order",
            source_ref=source_ref,
            working_dir=None,
            code_filename="__shell__",
            code_sha256="shell-session",
            code_content="",
            archive_filename=None,
            archive_content_base64="",
            run_command=None,
            entry_command=_entry_command_for_session(
                session_mode="shell",
                code_filename="__shell__",
                entry_command=None,
            ),
            image_artifact_id=offer.image_artifact_id,
            image_offer_id=offer.id,
            connect_source="buyer_order_start_session",
        )
    except SwarmManagerError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    log_activity(
        db,
        seller_user_id=offer.seller_user_id,
        node_id=node.id,
        image_id=offer.image_artifact_id,
        event_type="buyer_order_session_started",
        summary=f"Started runtime session bundle for order {order.id}",
        metadata={
            "order_id": order.id,
            "session_id": session.id,
            "buyer_user_id": current_user.id,
            "offer_id": offer.id,
            "gateway_service_name": session.gateway_service_name,
        },
    )
    db.commit()
    return _serialize_order_start_session(session, order=order, seller_node_key=node.node_key)


@router.post("/runtime-sessions/{session_id}/report")
def report_buyer_runtime_session(
    session_id: int,
    payload: BuyerRuntimeSessionReportRequest,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    session = db.get(RuntimeAccessSession, session_id)
    if session is None or session.session_token != payload.session_token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Runtime session not found.")

    session.status = payload.status
    session.last_logs = payload.logs
    if session.started_at is None:
        session.started_at = utcnow()
    if payload.status in {"completed", "failed"}:
        session.ended_at = utcnow()
        session.gateway_status = "stopped"
    db.commit()
    return {"ok": True}


@router.post("/runtime-sessions/redeem", response_model=BuyerRuntimeSessionRedeemResponse)
def redeem_buyer_runtime_session(
    payload: BuyerRuntimeSessionRedeemRequest,
    db: Session = Depends(get_db),
) -> BuyerRuntimeSessionRedeemResponse:
    statement = select(RuntimeAccessSession).where(RuntimeAccessSession.connect_code == payload.connect_code)
    session = db.scalar(statement)
    expires_at = _coerce_utc(session.expires_at) if session is not None else None
    if session is None or (expires_at and expires_at < utcnow()):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connect code not found or expired.")

    return BuyerRuntimeSessionRedeemResponse(
        session_id=session.id,
        session_token=session.session_token,
        access_mode="relay",
        network_mode=session.network_mode,
        relay_endpoint=_relay_endpoint(session.id),
        runtime_image=session.runtime_image,
        status=session.status,
        gateway_required=_session_gateway_required(session),
        gateway_protocol=session.gateway_protocol,
        gateway_port=session.gateway_port,
        supported_features=_session_supported_features(session),
    )


@router.post(
    "/runtime-sessions/{session_id}/gateway/handshake",
    response_model=BuyerRuntimeSessionGatewayHandshakeResponse,
)
def handshake_buyer_runtime_gateway(
    session_id: int,
    payload: BuyerRuntimeSessionGatewayHandshakeRequest,
    db: Session = Depends(get_db),
) -> BuyerRuntimeSessionGatewayHandshakeResponse:
    session = db.scalar(
        select(RuntimeAccessSession).where(
            RuntimeAccessSession.id == session_id,
            RuntimeAccessSession.session_token == payload.session_token,
        )
    )
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Runtime session not found.")

    expires_at = _coerce_utc(session.expires_at)
    if expires_at and expires_at < utcnow():
        session = expire_runtime_session(db, session)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"runtime_session_{session.status}")
    if session.status in {"stopped", "expired", "failed"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"runtime_session_{session.status}")
    if not _session_gateway_required(session):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="runtime_session_gateway_unavailable")

    node = db.get(Node, session.seller_node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Seller node not found.")

    gateway_host = session.seller_wireguard_target or extract_node_wireguard_target(node)
    if not gateway_host:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="session_gateway_target_unavailable")

    session.seller_wireguard_target = gateway_host
    session.gateway_last_seen_at = utcnow()
    db.commit()
    return BuyerRuntimeSessionGatewayHandshakeResponse(
        session_id=session.id,
        gateway_service_name=session.gateway_service_name or "",
        gateway_protocol=session.gateway_protocol,
        gateway_host=gateway_host,
        gateway_port=int(session.gateway_port or 0),
        handshake_mode=_session_handshake_mode(session),
        supported_features=_session_supported_features(session),
        seller_wireguard_target=gateway_host,
        expires_at=session.expires_at,
    )


@router.post("/runtime-sessions/{session_id}/wireguard/bootstrap", response_model=BuyerRuntimeSessionWireGuardBootstrapResponse)
def bootstrap_buyer_runtime_wireguard(
    session_id: int,
    payload: BuyerRuntimeSessionWireGuardBootstrapRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BuyerRuntimeSessionWireGuardBootstrapResponse:
    session = _get_runtime_session_for_buyer(db, session_id, current_user.id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Runtime session not found.")
    expires_at = _coerce_utc(session.expires_at)
    if expires_at and expires_at < utcnow():
        session = expire_runtime_session(db, session)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"runtime_session_{session.status}")
    if session.status in {"stopped", "expired", "failed"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"runtime_session_{session.status}")
    node = db.get(Node, session.seller_node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Seller node not found.")

    if session.buyer_wireguard_public_key and session.buyer_wireguard_public_key != payload.client_public_key:
        try:
            remove_server_peer(buyer_api.settings, public_key=session.buyer_wireguard_public_key)
        except Exception:
            pass

    try:
        bundle = build_buyer_wireguard_bootstrap(buyer_api.settings, session, node, payload.client_public_key)
        buyer_api.apply_server_peer(
            buyer_api.settings,
            public_key=payload.client_public_key,
            client_address=bundle["client_address"],
            persistent_keepalive=bundle["persistent_keepalive"],
        )
    except RuntimeBootstrapError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except WireGuardServerError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    session.buyer_wireguard_public_key = payload.client_public_key
    session.buyer_wireguard_client_address = bundle["client_address"]
    session.seller_wireguard_target = bundle.get("seller_wireguard_target")
    session.network_mode = "wireguard"
    db.commit()
    return BuyerRuntimeSessionWireGuardBootstrapResponse(**bundle)


@router.get("/runtime-sessions/{session_id}", response_model=BuyerRuntimeSessionStatusResponse)
def read_buyer_runtime_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BuyerRuntimeSessionStatusResponse:
    session = _get_runtime_session_for_buyer(db, session_id, current_user.id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Runtime session not found.")

    expires_at = _coerce_utc(session.expires_at)
    if expires_at and expires_at < utcnow() and session.status not in TERMINAL_SESSION_STATES:
        session = expire_runtime_session(db, session)

    should_refresh_remote = session.status not in TERMINAL_SESSION_STATES or (
        session.status in {"completed", "failed"} and not session.last_logs
    )
    if should_refresh_remote:
        try:
            inspect_result = buyer_api.inspect_runtime_session_bundle(
                buyer_api.settings,
                runtime_service_name=session.service_name,
                gateway_service_name=session.gateway_service_name,
            )
            runtime_inspect = inspect_result.get("runtime", {})
            gateway_inspect = inspect_result.get("gateway", {})
            session.status = _runtime_session_status_from_task(runtime_inspect.get("current_task", {}))
            if gateway_inspect:
                session.gateway_status = _gateway_status_from_task(gateway_inspect.get("current_task", {}))
                session.gateway_last_seen_at = utcnow()
            inspected_logs = str(runtime_inspect.get("logs") or "")
            if inspected_logs:
                session.last_logs = inspected_logs
            if session.status in {"completed", "failed"} and session.ended_at is None:
                session.ended_at = utcnow()
            db.commit()
        except Exception:
            pass

    node = db.get(Node, session.seller_node_id)
    current_hourly_price = None
    if session.image_offer_id is not None:
        offer = db.get(ImageOffer, session.image_offer_id)
        if offer is not None:
            current_hourly_price = offer.current_billable_price_cny_per_hour
    return BuyerRuntimeSessionStatusResponse(
        session_id=session.id,
        offer_id=session.image_offer_id,
        seller_node_key=node.node_key if node else "",
        runtime_image=session.runtime_image,
        source_type=session.source_type,
        code_filename=session.code_filename,
        session_mode=_session_mode(session),
        network_mode=session.network_mode,
        buyer_wireguard_client_address=session.buyer_wireguard_client_address,
        seller_wireguard_target=session.seller_wireguard_target,
        status=session.status,
        service_name=session.service_name,
        gateway_service_name=session.gateway_service_name,
        gateway_protocol=session.gateway_protocol,
        gateway_port=session.gateway_port,
        gateway_status=session.gateway_status,
        gateway_last_seen_at=session.gateway_last_seen_at,
        supported_features=_session_supported_features(session),
        connect_source=session.connect_source,
        relay_endpoint=_relay_endpoint(session.id),
        current_hourly_price_cny=current_hourly_price,
        accrued_usage_cny=float(session.accrued_usage_cny or 0.0),
        logs=session.last_logs or "",
        created_at=session.created_at,
        started_at=session.started_at,
        expires_at=session.expires_at,
        ended_at=session.ended_at,
    )


@router.post("/runtime-sessions/{session_id}/stop", response_model=BuyerRuntimeSessionStopResponse)
def stop_buyer_runtime_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BuyerRuntimeSessionStopResponse:
    session = _get_runtime_session_for_buyer(db, session_id, current_user.id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Runtime session not found.")

    try:
        buyer_api.remove_runtime_session_bundle(
            buyer_api.settings,
            runtime_service_name=session.service_name,
            config_name=session.config_name,
            gateway_service_name=session.gateway_service_name,
        )
    except SwarmManagerError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    if session.buyer_wireguard_public_key:
        try:
            remove_server_peer(buyer_api.settings, public_key=session.buyer_wireguard_public_key)
        except WireGuardServerError:
            pass

    session.status = "stopped"
    session.gateway_status = "stopped"
    session.ended_at = utcnow()
    db.commit()
    return BuyerRuntimeSessionStopResponse(session_id=session.id, status=session.status)


@router.post("/runtime-sessions/{session_id}/renew", response_model=BuyerRuntimeSessionRenewResponse)
def renew_buyer_runtime_session(
    session_id: int,
    payload: BuyerRuntimeSessionRenewRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BuyerRuntimeSessionRenewResponse:
    session = _get_runtime_session_for_buyer(db, session_id, current_user.id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Runtime session not found.")

    try:
        session = renew_runtime_session(db, session, payload.additional_minutes)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return BuyerRuntimeSessionRenewResponse(
        session_id=session.id,
        status=session.status,
        expires_at=session.expires_at,
    )
