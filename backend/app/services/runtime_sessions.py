from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import SessionLocal
from app.models.platform import RuntimeAccessSession
from app.services.swarm_manager import SwarmManagerError, remove_runtime_session_bundle
from app.services.wireguard_server import remove_server_peer

TERMINAL_SESSION_STATES = {"completed", "failed", "stopped", "expired"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def expire_runtime_session(db: Session, session: RuntimeAccessSession) -> RuntimeAccessSession:
    if session.status in TERMINAL_SESSION_STATES:
        return session

    try:
        remove_runtime_session_bundle(
            settings,
            runtime_service_name=session.service_name,
            config_name=session.config_name,
            gateway_service_name=session.gateway_service_name,
        )
    except SwarmManagerError:
        # Even if cleanup is partially unavailable, mark the lease as expired.
        pass
    if session.buyer_wireguard_public_key:
        try:
            remove_server_peer(settings, public_key=session.buyer_wireguard_public_key)
        except Exception:
            pass

    session.status = "expired"
    session.gateway_status = "stopped"
    session.ended_at = utcnow()
    db.commit()
    return session


def cleanup_expired_runtime_sessions() -> int:
    db = SessionLocal()
    try:
        now = utcnow()
        statement = select(RuntimeAccessSession).where(
            RuntimeAccessSession.expires_at.is_not(None),
            RuntimeAccessSession.expires_at < now,
            RuntimeAccessSession.status.not_in(TERMINAL_SESSION_STATES),
        )
        sessions = db.scalars(statement).all()
        count = 0
        for session in sessions:
            expire_runtime_session(db, session)
            count += 1
        return count
    finally:
        db.close()


def renew_runtime_session(db: Session, session: RuntimeAccessSession, minutes: int) -> RuntimeAccessSession:
    if session.status in TERMINAL_SESSION_STATES:
        raise ValueError("runtime_session_not_renewable")
    expires_at = _coerce_utc(session.expires_at)
    if expires_at is not None and expires_at < utcnow():
        expire_runtime_session(db, session)
        raise ValueError("runtime_session_not_renewable")
    if expires_at is None:
        session.expires_at = utcnow()
    else:
        session.expires_at = expires_at
    session.expires_at = session.expires_at + timedelta(minutes=minutes)
    db.commit()
    db.refresh(session)
    return session
