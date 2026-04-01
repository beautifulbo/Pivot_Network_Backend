from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routes.platform.common import serialize_image, serialize_node
from app.core.db import get_db
from app.models.identity import User
from app.schemas.platform.nodes import PlatformOverviewResponse
from app.services.platform_images import list_seller_images
from app.services.platform_nodes import list_seller_nodes

router = APIRouter()


@router.get("/overview", response_model=PlatformOverviewResponse)
def seller_overview(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PlatformOverviewResponse:
    nodes = list_seller_nodes(db, current_user.id)
    images = list_seller_images(db, current_user.id)
    return PlatformOverviewResponse(
        seller_id=current_user.id,
        node_count=len(nodes),
        image_count=len(images),
        nodes=[serialize_node(node) for node in nodes],
        images=[serialize_image(image) for image in images],
    )
