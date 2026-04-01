from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.buyer import BuyerOrder
from app.models.seller import ImageOffer, Node


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def generate_order_no() -> str:
    return f"ORD-{int(utcnow().timestamp())}-{secrets.token_hex(4)}"


def issue_buyer_order(
    db: Session,
    *,
    buyer_user_id: int,
    offer: ImageOffer,
    requested_duration_minutes: int,
) -> BuyerOrder:
    order = BuyerOrder(
        buyer_user_id=buyer_user_id,
        offer_id=offer.id,
        order_no=generate_order_no(),
        requested_duration_minutes=requested_duration_minutes,
        issued_hourly_price_cny=float(offer.current_billable_price_cny_per_hour or 0.0),
        payment_status="not_required",
        order_status="issued",
        license_token=secrets.token_urlsafe(24),
    )
    db.add(order)
    db.flush()
    return order


def list_buyer_orders(db: Session, buyer_user_id: int) -> list[BuyerOrder]:
    return db.scalars(select(BuyerOrder).where(BuyerOrder.buyer_user_id == buyer_user_id).order_by(BuyerOrder.id.desc())).all()


def get_buyer_order(db: Session, *, buyer_user_id: int, order_id: int) -> BuyerOrder | None:
    return db.scalar(select(BuyerOrder).where(BuyerOrder.id == order_id, BuyerOrder.buyer_user_id == buyer_user_id))


def get_order_offer_and_node(db: Session, order: BuyerOrder) -> tuple[ImageOffer | None, Node | None]:
    offer = db.get(ImageOffer, order.offer_id)
    node = db.get(Node, offer.node_id) if offer else None
    return offer, node


def redeem_order_if_needed(order: BuyerOrder) -> BuyerOrder:
    if order.license_redeemed_at is None:
        order.license_redeemed_at = utcnow()
        order.order_status = "redeemed"
    return order
