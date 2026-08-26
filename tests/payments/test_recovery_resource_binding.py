"""Recovering a pending Toss order must not attach it to the wrong analysis.

song_detail is a per-analysis entitlement, but every analysis is bought through the same
Toss SKU. A pending order therefore does not say which analysis it was for, so recovery
has to bind through the intent — never through the SKU alone.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from backend.app.db.models import Analysis, Base, Entitlement, PaymentIntent
from backend.app.db.session import reset_engine, session_scope
from backend.app.db.users import get_or_create_user
from backend.app.payments.errors import PaymentError
from backend.app.payments.service import recover_pending_order
from backend.app.payments.toss_clients import TossOrderStatus, set_iap_client

USER_KEY = "443731104"
OTHER_USER_KEY = "900000002"
SKU = "sku.song.detail.test"


class FakeIapClient:
    """Toss knows the order and its SKU — it does not know our analysis id."""

    def __init__(self, user: str = USER_KEY) -> None:
        self.user = user

    def get_order_status(self, order_id: str, *, toss_user_key: str | None = None):
        if toss_user_key and str(toss_user_key) != self.user:
            return TossOrderStatus(order_id, None, "NOT_FOUND", None, "SUCCESS", {})
        return TossOrderStatus(order_id, SKU, "PAYMENT_COMPLETED", None, "SUCCESS", {})


@pytest.fixture()
def env(tmp_path, monkeypatch):
    db = tmp_path / "recover.sqlite"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db}")
    monkeypatch.setenv("VAGENT_ENV", "development")
    monkeypatch.setenv("PAYMENTS_ENABLED", "true")
    monkeypatch.setenv("IAP_SONG_DETAIL_SKU", SKU)
    monkeypatch.setenv("RUNTIME_DIR", str(tmp_path / "runtime"))
    (tmp_path / "runtime").mkdir()
    reset_engine()
    from backend.app.config import get_runtime_dir

    get_runtime_dir.cache_clear()
    from backend.app.db.session import get_engine

    engine = get_engine()
    assert engine is not None
    Base.metadata.create_all(engine)
    set_iap_client(FakeIapClient())
    yield
    set_iap_client(None)
    reset_engine()
    get_runtime_dir.cache_clear()


def _analysis(subject: str = USER_KEY) -> str:
    aid = uuid.uuid4().hex
    with session_scope() as session:
        user = get_or_create_user(session, provider="TOSS", subject=subject)
        session.add(Analysis(id=aid, user_id=user.id, status="completed"))
    return aid


def _intent(analysis_id: str, *, subject: str = USER_KEY, expired: bool = False) -> str:
    now = datetime.now(timezone.utc)
    with session_scope() as session:
        user = get_or_create_user(session, provider="TOSS", subject=subject)
        row = PaymentIntent(
            user_id=user.id,
            product_id="song_detail",
            sku=SKU,
            resource_type="ANALYSIS",
            resource_id=analysis_id,
            status="PENDING",
            expires_at=now - timedelta(minutes=5) if expired else now + timedelta(minutes=10),
        )
        session.add(row)
        session.flush()
        return str(row.id)


def _entitlements(analysis_id: str) -> int:
    with session_scope() as session:
        return len(
            list(
                session.scalars(
                    select(Entitlement).where(Entitlement.resource_id == analysis_id)
                )
            )
        )


def test_single_pending_intent_recovers_its_own_analysis(env):
    aid = _analysis()
    _intent(aid)
    with session_scope() as session:
        result = recover_pending_order(session, toss_user_key=USER_KEY, order_id="order-1", sku=SKU)
    assert result["granted"] is True
    assert result["resource_id"] == aid
    assert _entitlements(aid) == 1


def test_two_same_sku_pending_intents_refuse_to_guess(env):
    """A and B both pending on one SKU: the order cannot be attributed."""
    aid_a, aid_b = _analysis(), _analysis()
    _intent(aid_a)
    _intent(aid_b)
    with session_scope() as session:
        with pytest.raises(PaymentError) as exc:
            recover_pending_order(session, toss_user_key=USER_KEY, order_id="order-1", sku=SKU)
    assert exc.value.code == "AMBIGUOUS_PENDING_PURCHASE"
    assert _entitlements(aid_a) == 0
    assert _entitlements(aid_b) == 0


def test_expired_intent_must_not_hand_its_order_to_another_analysis(env):
    """The dangerous case: A's payment is stranded and A's intent aged out.

    B is now the only PENDING candidate for this SKU. Binding A's order to B would grant
    the wrong analysis for a payment the user made for A.
    """
    aid_a, aid_b = _analysis(), _analysis()
    _intent(aid_a, expired=True)
    _intent(aid_b)

    with session_scope() as session:
        try:
            result = recover_pending_order(
                session, toss_user_key=USER_KEY, order_id="order-A", sku=SKU
            )
        except PaymentError as exc:
            assert exc.code in ("AMBIGUOUS_PENDING_PURCHASE", "NEEDS_MANUAL_RESTORE")
            result = None
    if result is not None:
        assert result["resource_id"] != aid_b, "A's order was granted to B"


def test_exact_intent_binding_is_honoured(env):
    aid_a, aid_b = _analysis(), _analysis()
    intent_a = _intent(aid_a)
    _intent(aid_b)

    with session_scope() as session:
        result = recover_pending_order(
            session,
            toss_user_key=USER_KEY,
            order_id="order-A",
            sku=SKU,
            intent_id=intent_a,
        )
    assert result["resource_id"] == aid_a
    assert _entitlements(aid_b) == 0


def test_intent_of_another_user_cannot_be_recovered(env):
    aid_other = _analysis(subject=OTHER_USER_KEY)
    intent_other = _intent(aid_other, subject=OTHER_USER_KEY)
    _analysis()

    with session_scope() as session:
        with pytest.raises(PaymentError):
            recover_pending_order(
                session,
                toss_user_key=USER_KEY,
                order_id="order-x",
                sku=SKU,
                intent_id=intent_other,
            )
    assert _entitlements(aid_other) == 0


def _terminal_intent(analysis_id: str, status: str) -> str:
    """A past purchase attempt for the same SKU that DB already moved off PENDING."""
    now = datetime.now(timezone.utc)
    with session_scope() as session:
        user = get_or_create_user(session, provider="TOSS", subject=USER_KEY)
        row = PaymentIntent(
            user_id=user.id,
            product_id="song_detail",
            sku=SKU,
            resource_type="ANALYSIS",
            resource_id=analysis_id,
            status=status,
            expires_at=now - timedelta(minutes=30),
        )
        session.add(row)
        session.flush()
        return str(row.id)


@pytest.mark.parametrize("status", ["EXPIRED", "FAILED", "CANCELLED"])
def test_historical_intent_must_not_hand_its_order_to_another_analysis(env, status):
    """A's attempt is off PENDING, so a PENDING-only rival check cannot see it.

    B then looks like the single candidate and would absorb A's payment.
    """
    aid_a, aid_b = _analysis(), _analysis()
    _terminal_intent(aid_a, status)
    _intent(aid_b)

    with session_scope() as session:
        try:
            result = recover_pending_order(
                session, toss_user_key=USER_KEY, order_id="order-A", sku=SKU
            )
        except PaymentError as exc:
            assert exc.code in ("AMBIGUOUS_PENDING_PURCHASE", "NEEDS_MANUAL_RESTORE")
            result = None
    if result is not None:
        assert result["resource_id"] != aid_b, f"{status}: A's order was granted to B"
    assert _entitlements(aid_b) == 0


def test_completed_intent_bound_to_another_order_does_not_block_a_clean_recovery(env):
    """A finished purchase is already settled, so it is not a rival for this order."""
    aid_a, aid_b = _analysis(), _analysis()
    with session_scope() as session:
        user = get_or_create_user(session, provider="TOSS", subject=USER_KEY)
        session.add(
            PaymentIntent(
                user_id=user.id,
                product_id="song_detail",
                sku=SKU,
                resource_type="ANALYSIS",
                resource_id=aid_a,
                status="COMPLETED",
                toss_order_id="order-old",
                expires_at=datetime.now(timezone.utc) - timedelta(minutes=30),
            )
        )
    _intent(aid_b)

    with session_scope() as session:
        result = recover_pending_order(
            session, toss_user_key=USER_KEY, order_id="order-new", sku=SKU
        )
    assert result["resource_id"] == aid_b


def test_diagnostic_products_get_the_same_protection(env, monkeypatch):
    """diagnostic_full shares one SKU across analyses exactly like song_detail."""
    monkeypatch.setenv("IAP_DIAGNOSTIC_FULL_SKU", "sku.diag.full.test")
    aid_a, aid_b = _analysis(), _analysis()
    now = datetime.now(timezone.utc)
    with session_scope() as session:
        user = get_or_create_user(session, provider="TOSS", subject=USER_KEY)
        for aid, status, exp in (
            (aid_a, "EXPIRED", now - timedelta(minutes=30)),
            (aid_b, "PENDING", now + timedelta(minutes=10)),
        ):
            session.add(
                PaymentIntent(
                    user_id=user.id,
                    product_id="diagnostic_full",
                    sku="sku.diag.full.test",
                    resource_type="ANALYSIS",
                    resource_id=aid,
                    status=status,
                    expires_at=exp,
                )
            )

    with session_scope() as session:
        try:
            result = recover_pending_order(
                session, toss_user_key=USER_KEY, order_id="order-A", sku="sku.diag.full.test"
            )
        except PaymentError:
            result = None
    if result is not None:
        assert result["resource_id"] != aid_b
    assert _entitlements(aid_b) == 0
