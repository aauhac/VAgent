"""Add worker claim/lease columns for SQS consumer idempotency.

Revision ID: 20260819_0008
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260819_0008"
down_revision = "20260818_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "analyses" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("analyses")}
    if "worker_claim_token" not in cols:
        op.add_column("analyses", sa.Column("worker_claim_token", sa.String(64), nullable=True))
    if "worker_lease_expires_at" not in cols:
        op.add_column(
            "analyses",
            sa.Column("worker_lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "worker_attempt_count" not in cols:
        op.add_column(
            "analyses",
            sa.Column("worker_attempt_count", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "analyses" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("analyses")}
    if "worker_attempt_count" in cols:
        op.drop_column("analyses", "worker_attempt_count")
    if "worker_lease_expires_at" in cols:
        op.drop_column("analyses", "worker_lease_expires_at")
    if "worker_claim_token" in cols:
        op.drop_column("analyses", "worker_claim_token")
