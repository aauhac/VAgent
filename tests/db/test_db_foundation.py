"""DB foundation unit tests (SQLite — not a production default)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db.models import Analysis, Base, Entitlement, PurchaseOrder, User
from backend.app.db.purchases import grant_from_purchase
from backend.app.db.users import get_or_create_user


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
        session.commit()
    finally:
        session.close()
        engine.dispose()


def test_create_user_idempotent(db_session: Session):
    u1 = get_or_create_user(db_session, provider="DEV", subject="demo-user")
    u2 = get_or_create_user(db_session, provider="DEV", subject="demo-user")
    assert u1.id == u2.id


def test_create_analysis_belongs_to_user(db_session: Session):
    user = get_or_create_user(db_session, provider="DEV", subject="alice")
    aid = uuid.uuid4().hex
    row = Analysis(id=aid, user_id=user.id, status="completed", original_filename="a.wav")
    db_session.add(row)
    db_session.flush()
    loaded = db_session.get(Analysis, aid)
    assert loaded is not None
    assert loaded.user_id == user.id


def test_other_user_cannot_own_row(db_session: Session):
    alice = get_or_create_user(db_session, provider="DEV", subject="alice")
    bob = get_or_create_user(db_session, provider="DEV", subject="bob")
    aid = uuid.uuid4().hex
    db_session.add(Analysis(id=aid, user_id=alice.id, status="completed"))
    db_session.flush()
    row = db_session.get(Analysis, aid)
    assert row.user_id != bob.id


def test_history_query_own_analyses(db_session: Session):
    alice = get_or_create_user(db_session, provider="DEV", subject="alice")
    bob = get_or_create_user(db_session, provider="DEV", subject="bob")
    db_session.add(Analysis(id=uuid.uuid4().hex, user_id=alice.id, status="completed"))
    db_session.add(Analysis(id=uuid.uuid4().hex, user_id=bob.id, status="completed"))
    db_session.flush()
    rows = db_session.scalars(select(Analysis).where(Analysis.user_id == alice.id)).all()
    assert len(rows) == 1


def test_purchase_order_duplicate_no_double_grant(db_session: Session):
    user = get_or_create_user(db_session, provider="DEV", subject="alice")
    aid = uuid.uuid4().hex
    db_session.add(Analysis(id=aid, user_id=user.id, status="completed"))
    db_session.flush()
    o1, e1, created1 = grant_from_purchase(
        db_session,
        user_id=user.id,
        toss_order_id="order-1",
        product_id="song_detail",
        resource_type="ANALYSIS",
        resource_id=aid,
        entitlement_type="SONG_DETAIL",
    )
    o2, e2, created2 = grant_from_purchase(
        db_session,
        user_id=user.id,
        toss_order_id="order-1",
        product_id="song_detail",
        resource_type="ANALYSIS",
        resource_id=aid,
        entitlement_type="SONG_DETAIL",
    )
    assert o1.id == o2.id
    assert e1.id == e2.id
    assert created1 is True
    assert created2 is False
    ents = db_session.scalars(select(Entitlement).where(Entitlement.user_id == user.id)).all()
    assert len(ents) == 1
    orders = db_session.scalars(select(PurchaseOrder).where(PurchaseOrder.user_id == user.id)).all()
    assert len(orders) == 1
