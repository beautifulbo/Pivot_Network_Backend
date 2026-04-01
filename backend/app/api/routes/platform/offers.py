from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routes import platform as platform_api
from app.api.routes.platform.common import serialize_image_offer
from app.core.db import get_db
from app.models.identity import User
from app.models.seller import ImageArtifact, Node
from app.schemas.platform.offers import ImageOfferCreateRequest, ImageOfferProbeRequest, ImageOfferResponse
from app.services.platform_offers import get_offer_dependencies_for_seller, get_seller_image_offer, list_seller_image_offers
from app.services.pricing_engine import PricingEngineError
from app.services.swarm_manager import SwarmManagerError

router = APIRouter()


@router.post("/image-offers", response_model=ImageOfferResponse)
def publish_image_offer(
    payload: ImageOfferCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImageOfferResponse:
    image = db.scalar(
        select(ImageArtifact).where(
            ImageArtifact.id == payload.image_artifact_id,
            ImageArtifact.seller_user_id == current_user.id,
        )
    )
    if image is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image artifact not found.")
    if image.node_id is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Image artifact is not bound to a node.")
    node = db.scalar(select(Node).where(Node.id == image.node_id, Node.seller_user_id == current_user.id))
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Seller node not found.")

    try:
        offer = platform_api.run_offer_probe_and_pricing(
            db,
            seller_user_id=current_user.id,
            image=image,
            node=node,
            timeout_seconds=platform_api.settings.PRICING_PROBE_TIMEOUT_SECONDS,
        )
    except SwarmManagerError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except PricingEngineError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return serialize_image_offer(offer)


@router.post("/image-offers/{offer_id}/probe", response_model=ImageOfferResponse)
def reprobe_image_offer(
    offer_id: int,
    payload: ImageOfferProbeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImageOfferResponse:
    offer = get_seller_image_offer(db, seller_user_id=current_user.id, offer_id=offer_id)
    if offer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image offer not found.")
    image, node = get_offer_dependencies_for_seller(db, seller_user_id=current_user.id, offer=offer)
    if image is None or node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image offer dependencies not found.")

    try:
        offer = platform_api.run_offer_probe_and_pricing(
            db,
            seller_user_id=current_user.id,
            image=image,
            node=node,
            timeout_seconds=payload.timeout_seconds,
        )
    except SwarmManagerError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except PricingEngineError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return serialize_image_offer(offer)


@router.get("/image-offers", response_model=list[ImageOfferResponse])
def list_image_offers(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ImageOfferResponse]:
    return [serialize_image_offer(offer) for offer in list_seller_image_offers(db, current_user.id)]
