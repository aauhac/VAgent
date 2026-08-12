"""Fresh Alembic upgrade — no create_all."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, inspect, text


@pytest.mark.skipif(
    not os.environ.get("VAGENT_MIGRATION_DATABASE_URL"),
    reason="Set VAGENT_MIGRATION_DATABASE_URL to a fresh empty Postgres DB",
)
def test_alembic_upgrade_head_creates_tables(monkeypatch):
    url = os.environ["VAGENT_MIGRATION_DATABASE_URL"]
    monkeypatch.setenv("DATABASE_URL", url)

    # Ensure empty
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))

    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")

    insp = inspect(engine)
    tables = set(insp.get_table_names())
    required = {
        "users",
        "analyses",
        "diagnostic_sessions",
        "diagnostic_task_attempts",
        "entitlements",
        "purchase_orders",
        "alembic_version",
    }
    assert required <= tables

    # Constraints
    with engine.connect() as conn:
        ver = conn.execute(text("select version_num from alembic_version")).scalar()
        assert ver == "20260812_0002"

    uq = {c["name"] for c in insp.get_unique_constraints("users")}
    assert "uq_users_external" in uq or any(
        set(c.get("column_names") or []) >= {"external_provider", "external_subject"}
        for c in insp.get_unique_constraints("users")
    )
    po = insp.get_unique_constraints("purchase_orders")
    assert any("toss_order_id" in (c.get("column_names") or []) for c in po)
    ent = insp.get_unique_constraints("entitlements")
    assert any(c.get("name") == "uq_entitlement_resource" for c in ent) or any(
        len(c.get("column_names") or []) >= 4 for c in ent
    )

    # columns on diagnostic_sessions
    cols = {c["name"] for c in insp.get_columns("diagnostic_sessions")}
    for name in (
        "selected_tasks",
        "unresolved_dimensions",
        "tasks_state",
        "diagnostic_offer",
        "updated_at",
    ):
        assert name in cols
