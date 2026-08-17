"""Add users.auth_revoked_at for Toss disconnect session revoke.

Revision ID: 20260818_0006
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260818_0006"
down_revision = "20260817_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "users" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("users")}
    if "auth_revoked_at" not in cols:
        op.add_column("users", sa.Column("auth_revoked_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "users" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("users")}
    if "auth_revoked_at" in cols:
        op.drop_column("users", "auth_revoked_at")
