"""Additive diagnostic session columns for existing DBs stamped under create_all.

Revision ID: 20260812_0002
Revises: 20260811_0001
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260812_0002"
down_revision = "20260811_0001"
branch_labels = None
depends_on = None

JSONType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    cols = [
        ("diagnostic_offer", JSONType),
        ("tasks_state", JSONType),
        ("task_results", JSONType),
        ("safety_answers", JSONType),
        ("safety_flags", JSONType),
        ("plan_rationale", JSONType),
        ("final_diagnostic_profile", JSONType),
        ("current_task_index", sa.Integer()),
        ("entitlement_id", sa.String(128)),
        ("product_id", sa.String(64)),
        ("report_storage_key", sa.Text()),
        ("error_message", sa.Text()),
        ("updated_at", sa.DateTime(timezone=True)),
    ]
    for name, coltype in cols:
        if not _has_column("diagnostic_sessions", name):
            op.add_column("diagnostic_sessions", sa.Column(name, coltype, nullable=True))


def downgrade() -> None:
    for name in (
        "diagnostic_offer",
        "tasks_state",
        "task_results",
        "safety_answers",
        "safety_flags",
        "plan_rationale",
        "final_diagnostic_profile",
        "current_task_index",
        "entitlement_id",
        "product_id",
        "report_storage_key",
        "error_message",
        "updated_at",
    ):
        if _has_column("diagnostic_sessions", name):
            op.drop_column("diagnostic_sessions", name)
