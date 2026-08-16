"""Add voice profile / personal vocal history / singer shadow tables."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260816_0004"
down_revision = "20260812_0003"
branch_labels = None
depends_on = None

JSONType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
UUIDType = sa.Uuid().with_variant(postgresql.UUID(as_uuid=True), "postgresql")


def _has_table(table: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return table in insp.get_table_names()


def upgrade() -> None:
    if not _has_table("user_voice_profiles"):
        op.create_table(
            "user_voice_profiles",
            sa.Column("id", UUIDType, primary_key=True),
            sa.Column("user_id", UUIDType, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("external_subject", sa.String(255), nullable=False),
            sa.Column("singer_id", sa.String(128), nullable=False),
            sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
            sa.Column("profile_status", sa.String(32), nullable=False, server_default="INITIAL"),
            sa.Column("recording_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("profile_version", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("strategy", sa.String(32), nullable=False, server_default="CENTROID"),
            sa.Column("encoder_name", sa.String(128), nullable=True),
            sa.Column("encoder_version", sa.String(64), nullable=True),
            sa.Column("embedding_dim", sa.Integer(), nullable=True),
            sa.Column("compatibility_state", sa.String(32), nullable=False, server_default="COMPATIBLE"),
            sa.Column("consented_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("user_id", name="uq_user_voice_profiles_user"),
            sa.UniqueConstraint("singer_id"),
        )
        op.create_index("ix_user_voice_profiles_user_id", "user_voice_profiles", ["user_id"])
        op.create_index("ix_user_voice_profiles_external_subject", "user_voice_profiles", ["external_subject"])

    if not _has_table("voice_profile_enrollments"):
        op.create_table(
            "voice_profile_enrollments",
            sa.Column("id", UUIDType, primary_key=True),
            sa.Column("user_id", UUIDType, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("singer_id", sa.String(128), nullable=False),
            sa.Column("recording_id", sa.String(64), nullable=True),
            sa.Column("analysis_id", sa.String(64), nullable=True),
            sa.Column("audio_sha256", sa.String(64), nullable=False),
            sa.Column("consent_source", sa.String(64), nullable=False),
            sa.Column("consented_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("label_source", sa.String(64), nullable=False, server_default="USER_ENROLLED"),
            sa.Column("model_version", sa.String(64), nullable=True),
            sa.Column("profile_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("user_id", "audio_sha256", name="uq_voice_enrollment_user_sha"),
        )
        op.create_index("ix_voice_profile_enrollments_user_id", "voice_profile_enrollments", ["user_id"])
        op.create_index("ix_voice_profile_enrollments_singer_id", "voice_profile_enrollments", ["singer_id"])

    if not _has_table("personal_vocal_snapshots"):
        op.create_table(
            "personal_vocal_snapshots",
            sa.Column("id", UUIDType, primary_key=True),
            sa.Column("user_id", UUIDType, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("singer_id", sa.String(128), nullable=True),
            sa.Column("recording_id", sa.String(64), nullable=True),
            sa.Column("analysis_id", sa.String(64), nullable=True),
            sa.Column("diagnostic_session_id", sa.String(64), nullable=True),
            sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("analyzer_version", sa.String(64), nullable=True),
            sa.Column("analysis_quality", sa.String(32), nullable=True),
            sa.Column("canonical_json", JSONType, nullable=True),
            sa.Column("goal_json", JSONType, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_personal_vocal_snapshots_user_id", "personal_vocal_snapshots", ["user_id"])
        op.create_index("ix_personal_vocal_snapshots_analysis_id", "personal_vocal_snapshots", ["analysis_id"])

    if not _has_table("singer_identity_shadow_events"):
        op.create_table(
            "singer_identity_shadow_events",
            sa.Column("id", UUIDType, primary_key=True),
            sa.Column("user_id", UUIDType, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("singer_id", sa.String(128), nullable=True),
            sa.Column("profile_version", sa.Integer(), nullable=True),
            sa.Column("recording_id", sa.String(64), nullable=True),
            sa.Column("analysis_id", sa.String(64), nullable=True),
            sa.Column("centroid_score", sa.Float(), nullable=True),
            sa.Column("centroid_decision", sa.String(32), nullable=True),
            sa.Column("k2_score", sa.Float(), nullable=True),
            sa.Column("k2_decision", sa.String(32), nullable=True),
            sa.Column("disagreement", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("model_version", sa.String(64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_singer_identity_shadow_events_user_id", "singer_identity_shadow_events", ["user_id"])


def downgrade() -> None:
    for table in (
        "singer_identity_shadow_events",
        "personal_vocal_snapshots",
        "voice_profile_enrollments",
        "user_voice_profiles",
    ):
        if _has_table(table):
            op.drop_table(table)
