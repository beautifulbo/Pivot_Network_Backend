"""add buyer payment domain tables and fields

Revision ID: 20260402_0003
Revises: 20260401_0002
Create Date: 2026-04-02 03:10:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260402_0003"
down_revision = "20260401_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("buyer_wallets") as batch_op:
        batch_op.add_column(sa.Column("status", sa.String(length=50), nullable=False, server_default="active"))
        batch_op.add_column(sa.Column("frozen_amount_cny", sa.Float(), nullable=False, server_default="0"))

    op.create_table(
        "payment_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("buyer_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("payment_no", sa.String(length=64), nullable=False),
        sa.Column("payment_type", sa.String(length=50), nullable=False, server_default="wallet_topup"),
        sa.Column("amount_cny", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(length=16), nullable=False, server_default="CNY"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("channel", sa.String(length=50), nullable=False, server_default="manual"),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("third_party_txn_id", sa.String(length=255), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_payment_orders_buyer_user_id", "payment_orders", ["buyer_user_id"], unique=False)
    op.create_index("ix_payment_orders_payment_no", "payment_orders", ["payment_no"], unique=True)

    op.create_table(
        "payment_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("payment_order_id", sa.Integer(), sa.ForeignKey("payment_orders.id"), nullable=False),
        sa.Column("buyer_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("transaction_type", sa.String(length=50), nullable=False),
        sa.Column("amount_cny", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("channel", sa.String(length=50), nullable=False),
        sa.Column("reference_no", sa.String(length=255), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_payment_transactions_payment_order_id", "payment_transactions", ["payment_order_id"], unique=False)
    op.create_index("ix_payment_transactions_buyer_user_id", "payment_transactions", ["buyer_user_id"], unique=False)

    with op.batch_alter_table("wallet_ledgers") as batch_op:
        batch_op.add_column(sa.Column("payment_order_id", sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f("ix_wallet_ledgers_payment_order_id"), ["payment_order_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_wallet_ledgers_payment_order_id_payment_orders",
            "payment_orders",
            ["payment_order_id"],
            ["id"],
        )

    with op.batch_alter_table("buyer_orders") as batch_op:
        batch_op.add_column(sa.Column("order_no", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("payment_status", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index(batch_op.f("ix_buyer_orders_order_no"), ["order_no"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_payment_transactions_buyer_user_id", table_name="payment_transactions")
    op.drop_index("ix_payment_transactions_payment_order_id", table_name="payment_transactions")
    op.drop_table("payment_transactions")

    op.drop_index("ix_payment_orders_payment_no", table_name="payment_orders")
    op.drop_index("ix_payment_orders_buyer_user_id", table_name="payment_orders")
    op.drop_table("payment_orders")

    with op.batch_alter_table("buyer_orders") as batch_op:
        batch_op.drop_index(batch_op.f("ix_buyer_orders_order_no"))
        batch_op.drop_column("paid_at")
        batch_op.drop_column("payment_status")
        batch_op.drop_column("order_no")

    with op.batch_alter_table("wallet_ledgers") as batch_op:
        batch_op.drop_constraint("fk_wallet_ledgers_payment_order_id_payment_orders", type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_wallet_ledgers_payment_order_id"))
        batch_op.drop_column("payment_order_id")

    with op.batch_alter_table("buyer_wallets") as batch_op:
        batch_op.drop_column("frozen_amount_cny")
        batch_op.drop_column("status")
