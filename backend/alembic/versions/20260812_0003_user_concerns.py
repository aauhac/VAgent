"""Add user_concerns to diagnostic_sessions."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260812_0003"
down_revision = "20260812_0002"
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
    if not _has_column("diagnostic_sessions", "user_concerns"):
        op.add_column("diagnostic_sessions", sa.Column("user_concerns", JSONType, nullable=True))


def downgrade() -> None:
    if _has_column("diagnostic_sessions", "user_concerns"):
        op.drop_column("diagnostic_sessions", "user_concerns")
