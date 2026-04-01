from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routes.buyer.common import serialize_catalog_offer
from app.core.db import get_db
from app.models.identity import User
from app.models.seller import ImageOffer, Node
from app.schemas.buyer.catalog import BuyerCatalogOfferResponse

router = APIRouter()


@router.get("/catalog/offers", response_model=list[BuyerCatalogOfferResponse])
def list_buyer_catalog_offers(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[BuyerCatalogOfferResponse]:
    _ = current_user
    offers = db.scalars(select(ImageOffer).where(ImageOffer.offer_status == "active").order_by(ImageOffer.id)).all()
    nodes = (
        {node.id: node for node in db.scalars(select(Node).where(Node.id.in_([offer.node_id for offer in offers]))).all()}
        if offers
        else {}
    )
    return [serialize_catalog_offer(offer, nodes.get(offer.node_id)) for offer in offers]


@router.get("/catalog/offers/{offer_id}", response_model=BuyerCatalogOfferResponse)
def read_buyer_catalog_offer(
    offer_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BuyerCatalogOfferResponse:
    _ = current_user
    offer = db.get(ImageOffer, offer_id)
    if offer is None or offer.offer_status != "active":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found.")
    node = db.get(Node, offer.node_id)
    return serialize_catalog_offer(offer, node)
