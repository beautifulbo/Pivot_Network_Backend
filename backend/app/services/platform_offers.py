from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.seller import ImageArtifact, ImageOffer, Node


def list_seller_image_offers(db: Session, seller_user_id: int) -> list[ImageOffer]:
    return db.scalars(select(ImageOffer).where(ImageOffer.seller_user_id == seller_user_id).order_by(ImageOffer.id)).all()


def get_seller_image_offer(
    db: Session,
    *,
    seller_user_id: int,
    offer_id: int,
) -> ImageOffer | None:
    return db.scalar(select(ImageOffer).where(ImageOffer.id == offer_id, ImageOffer.seller_user_id == seller_user_id))


def get_offer_dependencies_for_seller(
    db: Session,
    *,
    seller_user_id: int,
    offer: ImageOffer,
) -> tuple[ImageArtifact | None, Node | None]:
    image = db.scalar(
        select(ImageArtifact).where(ImageArtifact.id == offer.image_artifact_id, ImageArtifact.seller_user_id == seller_user_id)
    )
    node = db.scalar(select(Node).where(Node.id == offer.node_id, Node.seller_user_id == seller_user_id))
    return image, node
