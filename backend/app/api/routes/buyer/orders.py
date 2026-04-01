from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routes.buyer.common import serialize_order
from app.core.db import get_db
from app.models.buyer import BuyerOrder
from app.models.identity import User
from app.models.seller import ImageOffer, Node
from app.schemas.buyer.orders import BuyerOrderCreateRequest, BuyerOrderRedeemRequest, BuyerOrderRedeemResponse, BuyerOrderResponse
from app.services.activity import log_activity
from app.services.buyer_orders import (
    get_buyer_order,
    get_order_offer_and_node,
    issue_buyer_order,
    list_buyer_orders,
    redeem_order_if_needed,
)

router = APIRouter()


@router.post("/orders", response_model=BuyerOrderResponse)
def create_buyer_order(
    payload: BuyerOrderCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BuyerOrderResponse:
    offer = db.get(ImageOffer, payload.offer_id)
    if offer is None or offer.offer_status != "active":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found.")
    node = db.get(Node, offer.node_id)
    if node is None or node.status != "available":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Seller node is not available.")
    if offer.current_billable_price_cny_per_hour is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Offer price is unavailable.")

    order = issue_buyer_order(
        db,
        buyer_user_id=current_user.id,
        offer=offer,
        requested_duration_minutes=payload.requested_duration_minutes,
    )
    log_activity(
        db,
        seller_user_id=offer.seller_user_id,
        node_id=offer.node_id,
        image_id=offer.image_artifact_id,
        event_type="buyer_order_issued",
        summary=f"Issued buyer order for {offer.repository}:{offer.tag}",
        metadata={
            "order_id": order.id,
            "buyer_user_id": current_user.id,
            "offer_id": offer.id,
            "requested_duration_minutes": payload.requested_duration_minutes,
        },
    )
    db.commit()
    db.refresh(order)
    return serialize_order(order, offer, node)


@router.get("/orders", response_model=list[BuyerOrderResponse])
def list_buyer_orders_route(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[BuyerOrderResponse]:
    orders = list_buyer_orders(db, current_user.id)
    offers = (
        {offer.id: offer for offer in db.scalars(select(ImageOffer).where(ImageOffer.id.in_([order.offer_id for order in orders]))).all()}
        if orders
        else {}
    )
    nodes = (
        {node.id: node for node in db.scalars(select(Node).where(Node.id.in_([offer.node_id for offer in offers.values()]))).all()}
        if offers
        else {}
    )
    return [
        serialize_order(
            order,
            offers.get(order.offer_id),
            nodes.get(offers.get(order.offer_id).node_id) if offers.get(order.offer_id) else None,
        )
        for order in orders
    ]


@router.get("/orders/{order_id}", response_model=BuyerOrderResponse)
def read_buyer_order(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BuyerOrderResponse:
    order = get_buyer_order(db, buyer_user_id=current_user.id, order_id=order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")
    offer, node = get_order_offer_and_node(db, order)
    return serialize_order(order, offer, node)


@router.post("/orders/redeem", response_model=BuyerOrderRedeemResponse)
def redeem_buyer_order_license(payload: BuyerOrderRedeemRequest, db: Session = Depends(get_db)) -> BuyerOrderRedeemResponse:
    order = db.scalar(select(BuyerOrder).where(BuyerOrder.license_token == payload.license_token))
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="License token not found.")
    redeem_order_if_needed(order)
    db.commit()
    db.refresh(order)
    offer, node = get_order_offer_and_node(db, order)
    if offer is None or node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order offer not found.")
    return BuyerOrderRedeemResponse(
        order_id=order.id,
        offer_id=order.offer_id,
        seller_node_key=node.node_key,
        runtime_image_ref=offer.runtime_image_ref,
        requested_duration_minutes=order.requested_duration_minutes,
        issued_hourly_price_cny=order.issued_hourly_price_cny,
        order_status=order.order_status,
        license_token=order.license_token,
    )
