"""Rewarded ad session/claim + Asia/Seoul daily slot caps.

Revision ID: 20260820_0009
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260820_0009"
down_revision = "20260819_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())
    if "analyses" not in tables:
        return
    if "rewarded_ad_claims" not in tables:
        op.create_table(
            "rewarded_ad_claims",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("analysis_id", sa.String(64), sa.ForeignKey("analyses.id"), nullable=False),
            sa.Column("principal_key", sa.String(320), nullable=False),
            sa.Column("principal_provider", sa.String(32), nullable=False),
            sa.Column("principal_subject", sa.String(255), nullable=False),
            sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("reward_type", sa.String(32), nullable=False, server_default="SONG_DETAIL"),
            sa.Column("claim_token_hash", sa.String(64), nullable=False),
            sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
            sa.Column("seoul_day", sa.String(10), nullable=False),
            sa.Column("claimed_analysis_id", sa.String(64), nullable=True),
            sa.Column("entitlement_id", sa.Uuid(), sa.ForeignKey("entitlements.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("rewarded_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("claim_token_hash", name="uq_rewarded_ad_claim_token"),
            sa.UniqueConstraint("claimed_analysis_id", name="uq_rewarded_ad_claimed_analysis"),
        )
        op.create_index("ix_rewarded_ad_claims_analysis_id", "rewarded_ad_claims", ["analysis_id"])
        op.create_index("ix_rewarded_ad_claims_principal_key", "rewarded_ad_claims", ["principal_key"])
        op.create_index("ix_rewarded_ad_claims_seoul_day", "rewarded_ad_claims", ["seoul_day"])
        op.create_index("ix_rewarded_ad_claims_user_id", "rewarded_ad_claims", ["user_id"])
    if "rewarded_ad_daily_slots" not in tables:
        op.create_table(
            "rewarded_ad_daily_slots",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("principal_key", sa.String(320), nullable=False),
            sa.Column("seoul_day", sa.String(10), nullable=False),
            sa.Column("slot_index", sa.Integer(), nullable=False),
            sa.Column("claim_id", sa.Uuid(), sa.ForeignKey("rewarded_ad_claims.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("principal_key", "seoul_day", "slot_index", name="uq_rewarded_ad_daily_slot"),
        )
        op.create_index("ix_rewarded_ad_daily_slots_principal_key", "rewarded_ad_daily_slots", ["principal_key"])
        op.create_index("ix_rewarded_ad_daily_slots_seoul_day", "rewarded_ad_daily_slots", ["seoul_day"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())
    if "rewarded_ad_daily_slots" in tables:
        op.drop_table("rewarded_ad_daily_slots")
    if "rewarded_ad_claims" in tables:
        op.drop_table("rewarded_ad_claims")
