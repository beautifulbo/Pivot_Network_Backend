from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ImageReportRequest(BaseModel):
    node_id: str
    repository: str
    tag: str
    digest: str | None = None
    registry: str
    source_image: str | None = None
    status: str = "uploaded"


class ImageArtifactResponse(BaseModel):
    id: int
    seller_user_id: int
    node_id: int | None
    repository: str
    tag: str
    digest: str | None
    registry: str
    source_image: str | None
    status: str
    push_ready: bool
    created_at: datetime
    updated_at: datetime
