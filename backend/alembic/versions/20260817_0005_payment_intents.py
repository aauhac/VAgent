"""Payment intents, order binding, auth sessions.

Revision ID: 20260817_0005
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260817_0005"
down_revision = "20260816_0004"
branch_labels = None
depends_on = None

UUIDType = sa.Uuid().with_variant(postgresql.UUID(as_uuid=True), "postgresql")


def _cols(table: str) -> set[str]:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    cols = _cols("purchase_orders")
    if "provider" not in cols:
        op.add_column(
            "purchase_orders",
            sa.Column("provider", sa.String(32), nullable=False, server_default="TOSS"),
        )
    if "provider_order_id" not in cols:
        op.add_column("purchase_orders", sa.Column("provider_order_id", sa.String(128), nullable=True))
        op.execute("UPDATE purchase_orders SET provider_order_id = toss_order_id WHERE provider_order_id IS NULL")
        op.alter_column("purchase_orders", "provider_order_id", nullable=False)
    if "resource_type" not in cols:
        op.add_column("purchase_orders", sa.Column("resource_type", sa.String(32), nullable=True))
    if "resource_id" not in cols:
        op.add_column("purchase_orders", sa.Column("resource_id", sa.String(64), nullable=True))
    if "amount" not in cols:
        op.add_column("purchase_orders", sa.Column("amount", sa.Integer(), nullable=True))
    if "currency" not in cols:
        op.add_column("purchase_orders", sa.Column("currency", sa.String(16), nullable=True))
    if "provider_status" not in cols:
        op.add_column("purchase_orders", sa.Column("provider_status", sa.String(32), nullable=True))
    if "verified_at" not in cols:
        op.add_column("purchase_orders", sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))

    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing = {i["name"] for i in insp.get_indexes("purchase_orders")} if "purchase_orders" in insp.get_table_names() else set()
    uniques = {c["name"] for c in insp.get_unique_constraints("purchase_orders")} if "purchase_orders" in insp.get_table_names() else set()
    if "uq_purchase_orders_provider_order" not in uniques:
        op.create_unique_constraint(
            "uq_purchase_orders_provider_order",
            "purchase_orders",
            ["provider", "provider_order_id"],
        )

    if "payment_intents" not in insp.get_table_names():
        op.create_table(
            "payment_intents",
            sa.Column("id", UUIDType, primary_key=True),
            sa.Column("user_id", UUIDType, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("product_id", sa.String(64), nullable=False),
            sa.Column("sku", sa.String(128), nullable=False),
            sa.Column("resource_type", sa.String(32), nullable=False),
            sa.Column("resource_id", sa.String(64), nullable=False),
            sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("toss_order_id", sa.String(128), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_payment_intents_user_id", "payment_intents", ["user_id"])
        op.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_payment_intents_active
            ON payment_intents (user_id, product_id, resource_type, resource_id)
            WHERE status = 'PENDING'
            """
        )

    if "auth_sessions" not in insp.get_table_names():
        op.create_table(
            "auth_sessions",
            sa.Column("id", UUIDType, primary_key=True),
            sa.Column("user_id", UUIDType, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("jti", sa.String(64), nullable=False),
            sa.Column("toss_user_key", sa.String(128), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("jti", name="uq_auth_sessions_jti"),
        )
        op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])


def downgrade() -> None:
    return
