"""Live PostgreSQL payment + history persistence gate.

Skipped unless POSTGRES_QA_URL is set. Do not treat SQLite as a Postgres pass.
"""

from __future__ import annotations

import os
import threading
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import inspect, select, text

from backend.app.db.models import Analysis, Entitlement, PaymentIntent, PurchaseOrder
from backend.app.db.purchases import PaymentOrderBindingMismatch, grant_from_purchase, revoke_from_refund
from backend.app.db.session import database_reachable, reset_engine
from backend.app.db.users import get_or_create_user

POSTGRES_QA_URL = (os.environ.get("POSTGRES_QA_URL") or "").strip()

pytestmark = pytest.mark.skipif(
    not POSTGRES_QA_URL,
    reason="POSTGRES_QA_URL not set — live Postgres gate not run",
)


@pytest.fixture()
def pg_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", POSTGRES_QA_URL)
    monkeypatch.setenv("VAGENT_ENV", "development")
    monkeypatch.setenv("VAGENT_SESSION_SECRET", "test-session-secret-not-for-prod")
    monkeypatch.setenv("PAYMENTS_ENABLED", "true")
    monkeypatch.setenv("TOSS_LOGIN_ENABLED", "true")
    monkeypatch.setenv("IAP_SONG_DETAIL_SKU", "sku.song.detail.test")
    monkeypatch.setenv("IAP_DIAGNOSTIC_FULL_SKU", "sku.diag.full.test")
    monkeypatch.setenv("IAP_DIAGNOSTIC_UPGRADE_SKU", "sku.diag.upgrade.test")
    monkeypatch.setenv("RUNTIME_DIR", str(tmp_path / "runtime"))
    (tmp_path / "runtime").mkdir()
    reset_engine()
    from backend.app.config import get_runtime_dir

    get_runtime_dir.cache_clear()
    yield POSTGRES_QA_URL
    reset_engine()
    get_runtime_dir.cache_clear()


def test_postgres_engine_is_postgresql(pg_env):
    from backend.app.db.session import get_engine

    engine = get_engine()
    assert engine is not None
    assert engine.dialect.name == "postgresql"
    assert database_reachable() is True


def test_payment_tables_and_unique_constraint(pg_env):
    from backend.app.db.session import get_engine

    insp = inspect(get_engine())
    tables = set(insp.get_table_names())
    for name in (
        "users",
        "analyses",
        "entitlements",
        "purchase_orders",
        "payment_intents",
        "auth_sessions",
        "diagnostic_sessions",
    ):
        assert name in tables, name
    uniques = {c["name"] for c in insp.get_unique_constraints("purchase_orders")}
    assert "uq_purchase_orders_provider_order" in uniques


def test_postgres_payment_persist_and_restart(pg_env):
    from backend.app.db.session import session_scope

    aid = uuid.uuid4().hex
    with session_scope() as session:
        user = get_or_create_user(session, provider="TOSS", subject="pg-live-user")
        session.add(Analysis(id=aid, user_id=user.id, status="completed", original_filename="live.wav"))
        session.flush()
        uid = user.id
        order, ent, created = grant_from_purchase(
            session,
            user_id=uid,
            toss_order_id="pg-order-1",
            product_id="song_detail",
            resource_type="ANALYSIS",
            resource_id=aid,
            entitlement_type="SONG_DETAIL",
            sku="sku.song.detail.test",
        )
        assert created is True
        assert ent.status == "ACTIVE"
        oid = str(order.id)

    reset_engine()
    from backend.app.config import get_runtime_dir
    from backend.app.db.session import session_scope as scope2

    get_runtime_dir.cache_clear()
    with scope2() as session:
        order = session.scalar(select(PurchaseOrder).where(PurchaseOrder.toss_order_id == "pg-order-1"))
        ent = session.scalar(
            select(Entitlement).where(
                Entitlement.resource_id == aid,
                Entitlement.entitlement_type == "SONG_DETAIL",
                Entitlement.status == "ACTIVE",
            )
        )
        assert order is not None
        assert str(order.id) == oid
        assert ent is not None


def test_postgres_refund_revokes(pg_env):
    from backend.app.db.session import session_scope

    aid = uuid.uuid4().hex
    with session_scope() as session:
        user = get_or_create_user(session, provider="TOSS", subject="pg-refund-user")
        session.add(Analysis(id=aid, user_id=user.id, status="completed"))
        session.flush()
        grant_from_purchase(
            session,
            user_id=user.id,
            toss_order_id="pg-order-ref",
            product_id="song_detail",
            resource_type="ANALYSIS",
            resource_id=aid,
            entitlement_type="SONG_DETAIL",
            sku="sku.song.detail.test",
        )
        order = revoke_from_refund(session, toss_order_id="pg-order-ref")
        assert order is not None
        assert order.status == "REFUNDED"
        ent = session.scalar(select(Entitlement).where(Entitlement.resource_id == aid))
        assert ent.status == "REVOKED"
        assert ent.revoked_at is not None


def test_postgres_replay_and_concurrent_unique(pg_env):
    from backend.app.db.session import session_scope

    aid = uuid.uuid4().hex
    aid2 = uuid.uuid4().hex
    with session_scope() as session:
        a = get_or_create_user(session, provider="TOSS", subject="pg-replay-a")
        b = get_or_create_user(session, provider="TOSS", subject="pg-replay-b")
        session.add(Analysis(id=aid, user_id=a.id, status="completed"))
        session.add(Analysis(id=aid2, user_id=a.id, status="completed"))
        session.flush()
        aid_a, aid_b = a.id, b.id
        grant_from_purchase(
            session,
            user_id=aid_a,
            toss_order_id="pg-order-replay",
            product_id="song_detail",
            resource_type="ANALYSIS",
            resource_id=aid,
            entitlement_type="SONG_DETAIL",
            sku="sku.song.detail.test",
        )
        o2, e2, created2 = grant_from_purchase(
            session,
            user_id=aid_a,
            toss_order_id="pg-order-replay",
            product_id="song_detail",
            resource_type="ANALYSIS",
            resource_id=aid,
            entitlement_type="SONG_DETAIL",
            sku="sku.song.detail.test",
        )
        assert created2 is False
        with pytest.raises(PaymentOrderBindingMismatch):
            grant_from_purchase(
                session,
                user_id=aid_b,
                toss_order_id="pg-order-replay",
                product_id="song_detail",
                resource_type="ANALYSIS",
                resource_id=aid,
                entitlement_type="SONG_DETAIL",
                sku="sku.song.detail.test",
            )
        with pytest.raises(PaymentOrderBindingMismatch):
            grant_from_purchase(
                session,
                user_id=aid_a,
                toss_order_id="pg-order-replay",
                product_id="song_detail",
                resource_type="ANALYSIS",
                resource_id=aid2,
                entitlement_type="SONG_DETAIL",
                sku="sku.song.detail.test",
            )
        with pytest.raises(PaymentOrderBindingMismatch):
            grant_from_purchase(
                session,
                user_id=aid_a,
                toss_order_id="pg-order-replay",
                product_id="diagnostic_full",
                resource_type="ANALYSIS",
                resource_id=aid,
                entitlement_type="DIAGNOSTIC",
                sku="sku.song.detail.test",
            )

    with session_scope() as session:
        racer = get_or_create_user(session, provider="TOSS", subject="pg-race")
        session.add(Analysis(id="a" * 32, user_id=racer.id, status="completed"))

    errors: list[str] = []

    def _race() -> None:
        try:
            from backend.app.db.session import session_scope as inner

            with inner() as session:
                user = get_or_create_user(session, provider="TOSS", subject="pg-race")
                grant_from_purchase(
                    session,
                    user_id=user.id,
                    toss_order_id="pg-order-race",
                    product_id="song_detail",
                    resource_type="ANALYSIS",
                    resource_id="a" * 32,
                    entitlement_type="SONG_DETAIL",
                    sku="sku.song.detail.test",
                )
        except PaymentOrderBindingMismatch:
            pass
        except Exception as exc:  # noqa: BLE001
            errors.append(type(exc).__name__)

    t1 = threading.Thread(target=_race)
    t2 = threading.Thread(target=_race)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    with session_scope() as session:
        count = len(
            session.scalars(select(PurchaseOrder).where(PurchaseOrder.toss_order_id == "pg-order-race")).all()
        )
        ents = session.scalars(
            select(Entitlement).where(Entitlement.resource_id == "a" * 32, Entitlement.entitlement_type == "SONG_DETAIL")
        ).all()
        assert count == 1
        assert len(ents) == 1
    assert errors == []
