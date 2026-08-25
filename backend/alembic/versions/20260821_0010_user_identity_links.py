"""Add user_identity_links: permanent anon-hash ↔ verified Toss userKey mapping.

Replaces the destructive anonymous→TOSS ownership migration. Rows are no longer moved;
identity resolution unions the users that belong to one canonical identity instead.

Revision ID: 20260821_0010
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "20260821_0010"
down_revision = "20260820_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "users" not in insp.get_table_names():
        return
    if "user_identity_links" in insp.get_table_names():
        return
    op.create_table(
        "user_identity_links",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("anon_subject", sa.String(length=255), nullable=False),
        sa.Column("toss_user_key", sa.String(length=255), nullable=False),
        sa.Column(
            "canonical_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("anon_subject", name="uq_identity_link_anon"),
    )
    op.create_index(
        "ix_user_identity_links_toss_user_key", "user_identity_links", ["toss_user_key"]
    )
    op.create_index(
        "ix_user_identity_links_canonical_user_id",
        "user_identity_links",
        ["canonical_user_id"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "user_identity_links" not in insp.get_table_names():
        return
    op.drop_index("ix_user_identity_links_canonical_user_id", table_name="user_identity_links")
    op.drop_index("ix_user_identity_links_toss_user_key", table_name="user_identity_links")
    op.drop_table("user_identity_links")
