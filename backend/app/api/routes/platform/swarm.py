from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routes import platform as platform_api
from app.core.db import get_db
from app.models.identity import User
from app.schemas.platform.runtime import SwarmRemoteOverviewResponse, SwarmWorkerJoinTokenResponse
from app.services.activity import log_activity
from app.services.swarm_manager import SwarmManagerError

router = APIRouter()


@router.get("/swarm/worker-join-token", response_model=SwarmWorkerJoinTokenResponse)
def read_swarm_worker_join_token(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SwarmWorkerJoinTokenResponse:
    try:
        payload = platform_api.get_worker_join_token(platform_api.settings)
    except SwarmManagerError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    log_activity(
        db,
        seller_user_id=current_user.id,
        event_type="swarm_worker_join_token_issued",
        summary="Issued swarm worker join token",
        metadata={"manager_host": payload["manager_host"], "manager_port": payload["manager_port"]},
    )
    db.commit()
    return SwarmWorkerJoinTokenResponse(**payload)


@router.get("/swarm/overview", response_model=SwarmRemoteOverviewResponse)
def read_remote_swarm_overview(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SwarmRemoteOverviewResponse:
    try:
        payload = platform_api.get_manager_overview(platform_api.settings)
    except SwarmManagerError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    log_activity(
        db,
        seller_user_id=current_user.id,
        event_type="swarm_overview_viewed",
        summary="Viewed remote swarm overview",
        metadata={"manager_host": payload["manager_host"], "manager_port": payload["manager_port"]},
    )
    db.commit()
    return SwarmRemoteOverviewResponse(**payload)
