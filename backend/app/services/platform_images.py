from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.identity import NodeRegistrationToken
from app.models.seller import ImageArtifact, Node
from app.schemas.platform.images import ImageReportRequest


def create_or_update_reported_image(
    db: Session,
    *,
    node_token: NodeRegistrationToken,
    node: Node,
    payload: ImageReportRequest,
) -> ImageArtifact:
    statement = select(ImageArtifact).where(
        ImageArtifact.seller_user_id == node_token.user_id,
        ImageArtifact.repository == payload.repository,
        ImageArtifact.tag == payload.tag,
        ImageArtifact.registry == payload.registry,
    )
    image = db.scalar(statement)
    if image is None:
        image = ImageArtifact(
            seller_user_id=node_token.user_id,
            node_id=node.id,
            repository=payload.repository,
            tag=payload.tag,
            digest=payload.digest,
            registry=payload.registry,
            source_image=payload.source_image,
            status=payload.status,
        )
        db.add(image)
    else:
        image.node_id = node.id
        image.digest = payload.digest
        image.source_image = payload.source_image
        image.status = payload.status
    return image


def list_seller_images(db: Session, seller_user_id: int) -> list[ImageArtifact]:
    return db.scalars(
        select(ImageArtifact).where(ImageArtifact.seller_user_id == seller_user_id).order_by(ImageArtifact.id)
    ).all()


def get_seller_image(db: Session, *, seller_user_id: int, image_id: int) -> ImageArtifact | None:
    return db.scalar(select(ImageArtifact).where(ImageArtifact.id == image_id, ImageArtifact.seller_user_id == seller_user_id))
