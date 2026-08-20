"""Add analysis_completion_notifications for analysis-complete smart messages.

Revision ID: 20260818_0007
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260818_0007"
down_revision = "20260818_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "analyses" not in insp.get_table_names():
        return
    if "analysis_completion_notifications" in insp.get_table_names():
        return
    op.create_table(
        "analysis_completion_notifications",
        sa.Column("analysis_id", sa.String(64), sa.ForeignKey("analyses.id"), primary_key=True),
        sa.Column("recipient_kind", sa.String(16), nullable=False),
        sa.Column("recipient_key", sa.String(255), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="REQUESTED"),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "analysis_completion_notifications" in insp.get_table_names():
        op.drop_table("analysis_completion_notifications")
