"""add runtime session gateway bundle fields

Revision ID: 20260401_0002
Revises: 20260326_0001
Create Date: 2026-04-01 20:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260401_0002"
down_revision = "20260326_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("runtime_access_sessions") as batch_op:
        batch_op.add_column(sa.Column("gateway_service_name", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("gateway_protocol", sa.String(length=50), nullable=False, server_default="http"))
        batch_op.add_column(sa.Column("gateway_port", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("gateway_status", sa.String(length=50), nullable=False, server_default="pending"))
        batch_op.add_column(sa.Column("gateway_last_seen_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("access_scope", sa.JSON(), nullable=False, server_default="{}"))
        batch_op.add_column(
            sa.Column("connect_source", sa.String(length=50), nullable=False, server_default="legacy_runtime_session")
        )
        batch_op.create_index(
            batch_op.f("ix_runtime_access_sessions_gateway_service_name"),
            ["gateway_service_name"],
            unique=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("runtime_access_sessions") as batch_op:
        batch_op.drop_index(batch_op.f("ix_runtime_access_sessions_gateway_service_name"))
        batch_op.drop_column("connect_source")
        batch_op.drop_column("access_scope")
        batch_op.drop_column("gateway_last_seen_at")
        batch_op.drop_column("gateway_status")
        batch_op.drop_column("gateway_port")
        batch_op.drop_column("gateway_protocol")
        batch_op.drop_column("gateway_service_name")
