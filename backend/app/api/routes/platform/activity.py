from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routes.platform.common import serialize_activity
from app.core.db import get_db
from app.models.activity import ActivityEvent
from app.models.identity import User
from app.schemas.activity import ActivityEventResponse

router = APIRouter()


@router.get("/activity", response_model=list[ActivityEventResponse])
def list_platform_activity(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ActivityEventResponse]:
    events = db.scalars(
        select(ActivityEvent)
        .where(ActivityEvent.seller_user_id == current_user.id)
        .order_by(ActivityEvent.id.desc())
        .limit(100)
    ).all()
    return [serialize_activity(event) for event in events]
