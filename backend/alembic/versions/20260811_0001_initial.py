"""Initial VAgent schema — explicit DDL (no create_all).

Revision ID: 20260811_0001
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260811_0001"
down_revision = None
branch_labels = None
depends_on = None

JSONType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
UUIDType = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", UUIDType, primary_key=True, nullable=False),
        sa.Column("external_provider", sa.String(32), nullable=False),
        sa.Column("external_subject", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("external_provider", "external_subject", name="uq_users_external"),
    )

    op.create_table(
        "purchase_orders",
        sa.Column("id", UUIDType, primary_key=True, nullable=False),
        sa.Column("user_id", UUIDType, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("toss_order_id", sa.String(128), nullable=False),
        sa.Column("sku", sa.String(64), nullable=True),
        sa.Column("product_id", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("status_determined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("toss_order_id", name="uq_purchase_orders_toss_order_id"),
    )
    op.create_index("ix_purchase_orders_user_id", "purchase_orders", ["user_id"])

    op.create_table(
        "analyses",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("user_id", UUIDType, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("stage", sa.String(64), nullable=True),
        sa.Column("progress", sa.Integer(), nullable=True),
        sa.Column("analysis_mode", sa.String(32), nullable=True),
        sa.Column("input_mode", sa.String(32), nullable=True),
        sa.Column("separate", sa.Boolean(), nullable=True),
        sa.Column("original_filename", sa.String(512), nullable=True),
        sa.Column("audio_storage_key", sa.Text(), nullable=True),
        sa.Column("preview_storage_key", sa.Text(), nullable=True),
        sa.Column("result_storage_key", sa.Text(), nullable=True),
        sa.Column("engine_version", sa.String(64), nullable=True),
        sa.Column("report_version", sa.String(64), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("public_summary", JSONType, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("audio_deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_analyses_user_id", "analyses", ["user_id"])

    op.create_table(
        "diagnostic_sessions",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("user_id", UUIDType, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("source_analysis_id", sa.String(64), sa.ForeignKey("analyses.id"), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("planner_version", sa.String(64), nullable=True),
        sa.Column("protocol_version", sa.String(64), nullable=True),
        sa.Column("report_version", sa.String(64), nullable=True),
        sa.Column("selected_tasks", JSONType, nullable=True),
        sa.Column("unresolved_dimensions", JSONType, nullable=True),
        sa.Column("diagnostic_offer", JSONType, nullable=True),
        sa.Column("tasks_state", JSONType, nullable=True),
        sa.Column("task_results", JSONType, nullable=True),
        sa.Column("safety_answers", JSONType, nullable=True),
        sa.Column("safety_flags", JSONType, nullable=True),
        sa.Column("plan_rationale", JSONType, nullable=True),
        sa.Column("final_diagnostic_profile", JSONType, nullable=True),
        sa.Column("current_task_index", sa.Integer(), nullable=True),
        sa.Column("entitlement_id", sa.String(128), nullable=True),
        sa.Column("product_id", sa.String(64), nullable=True),
        sa.Column("report_storage_key", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_diagnostic_sessions_user_id", "diagnostic_sessions", ["user_id"])

    op.create_table(
        "diagnostic_task_attempts",
        sa.Column("id", UUIDType, primary_key=True, nullable=False),
        sa.Column("session_id", sa.String(64), sa.ForeignKey("diagnostic_sessions.id"), nullable=False),
        sa.Column("task_id", sa.String(64), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("audio_storage_key", sa.Text(), nullable=True),
        sa.Column("quality_status", sa.String(32), nullable=True),
        sa.Column("dimension_evidence", JSONType, nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_diagnostic_task_attempts_session_id", "diagnostic_task_attempts", ["session_id"])

    op.create_table(
        "entitlements",
        sa.Column("id", UUIDType, primary_key=True, nullable=False),
        sa.Column("user_id", UUIDType, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("resource_type", sa.String(32), nullable=False),
        sa.Column("resource_id", sa.String(64), nullable=False),
        sa.Column("entitlement_type", sa.String(32), nullable=False),
        sa.Column("product_id", sa.String(64), nullable=True),
        sa.Column("purchase_order_id", UUIDType, sa.ForeignKey("purchase_orders.id"), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "user_id",
            "resource_type",
            "resource_id",
            "entitlement_type",
            name="uq_entitlement_resource",
        ),
    )
    op.create_index("ix_entitlements_user_id", "entitlements", ["user_id"])


def downgrade() -> None:
    op.drop_table("entitlements")
    op.drop_table("diagnostic_task_attempts")
    op.drop_table("diagnostic_sessions")
    op.drop_table("analyses")
    op.drop_table("purchase_orders")
    op.drop_table("users")
