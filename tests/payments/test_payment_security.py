"""Payment + verified identity security tests."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.db.models import Analysis, Base, Entitlement, PaymentIntent, PurchaseOrder, User
from backend.app.db.purchases import PaymentOrderBindingMismatch, grant_from_purchase, revoke_from_refund
from backend.app.db.session import reset_engine
from backend.app.db.users import get_or_create_user
from backend.app.identity import resolve_identity_from_headers
from backend.app.payments.session_tokens import issue_session, verify_session
from backend.app.payments.startup import validate_payment_production_config
from backend.app.payments.toss_clients import TossOrderStatus, set_iap_client, set_login_client
from backend.app.entitlements.provider import TossIAPEntitlementProvider
from pathlib import Path


class FakeLoginClient:
    def exchange_code(self, authorization_code: str, referrer: str) -> dict:
        if authorization_code.startswith("bad"):
            from backend.app.payments.toss_clients import TossApiError

            raise TossApiError("INVALID_GRANT", retryable=False)
        return {
            "accessToken": "toss-access-secret",
            "refreshToken": "toss-refresh-secret",
            "tokenType": "Bearer",
            "expiresIn": 3600,
        }

    def login_me(self, access_token: str) -> dict:
        assert access_token == "toss-access-secret"
        return {"userKey": 443731104}


class FakeIapClient:
    def __init__(self) -> None:
        self.orders: dict[str, dict] = {}

    def get_order_status(self, order_id: str, *, toss_user_key: str | None = None) -> TossOrderStatus:
        rec = self.orders.get(order_id)
        if rec is None:
            return TossOrderStatus(order_id, None, "NOT_FOUND", None, "SUCCESS", {})
        if toss_user_key and rec.get("user") and str(rec["user"]) != str(toss_user_key):
            return TossOrderStatus(order_id, rec.get("sku"), "NOT_FOUND", None, "SUCCESS", {})
        return TossOrderStatus(
            order_id=order_id,
            sku=rec.get("sku"),
            status=rec.get("status", "PAYMENT_COMPLETED"),
            reason=None,
            result_type=rec.get("result_type", "SUCCESS"),
            raw={"resultType": rec.get("result_type", "SUCCESS"), "success": rec},
        )


@pytest.fixture()
def payment_env(tmp_path, monkeypatch):
    db = tmp_path / "pay.sqlite"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db}")
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
    from backend.app.db.session import get_engine

    engine = get_engine()
    assert engine is not None
    Base.metadata.create_all(engine)
    fake_iap = FakeIapClient()
    set_iap_client(fake_iap)
    set_login_client(FakeLoginClient())
    from backend.app.main import app
    from backend.app.api import routes as routes_mod
    from backend.app.diagnostic import DiagnosticSessionService
    from backend.app.jobs.runner import JobRunner
    from backend.app.services.analysis_service import AnalysisService

    svc = AnalysisService()
    svc.runner = JobRunner(svc.runtime_dir, max_workers=1)
    routes_mod.service = svc
    routes_mod.diag = DiagnosticSessionService(svc.runtime_dir)
    client = TestClient(app, raise_server_exceptions=True)
    yield client, fake_iap, svc
    set_iap_client(None)
    set_login_client(None)
    reset_engine()
    get_runtime_dir.cache_clear()


def _login(client: TestClient) -> dict[str, str]:
    r = client.post(
        "/v1/auth/toss/login",
        json={"authorization_code": "valid-code-xx", "referrer": "SANDBOX"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "accessToken" not in body
    assert "refreshToken" not in body
    assert "access_token" not in body
    assert body["authenticated"] is True
    return {"Authorization": f"Bearer {body['session_token']}"}


def test_client_headers_are_never_verified_auth(monkeypatch):
    monkeypatch.setenv("TOSS_IDENTITY_TRUST_MODE", "VERIFIED_TOSS_SUBJECT")
    monkeypatch.setenv("VAGENT_ENV", "development")
    ident = resolve_identity_from_headers(x_user_id="forged-user", x_vagent_user_key="forged-user")
    assert ident.authenticated is False
    assert ident.trust_mode == "UNVERIFIED_CLIENT_SUBJECT"
    assert ident.auth_method == "CLIENT_ASSERTED_HEADER"


def test_prod_cannot_become_verified_by_env_only(monkeypatch):
    monkeypatch.setenv("VAGENT_ENV", "production")
    monkeypatch.setenv("TOSS_IDENTITY_TRUST_MODE", "VERIFIED_TOSS_SUBJECT")
    ident = resolve_identity_from_headers(x_vagent_user_key="attacker")
    assert ident.authenticated is False
    assert ident.trust_mode == "UNVERIFIED_CLIENT_SUBJECT"


def test_toss_login_code_exchange_is_server_side(payment_env):
    client, _, _ = payment_env
    headers = _login(client)
    me = client.get(" /v1/auth/me".replace(" ", ""), headers=headers)
    assert me.status_code == 200
    assert me.json()["authenticated"] is True


def test_toss_tokens_not_returned_to_frontend(payment_env):
    client, _, _ = payment_env
    r = client.post(
        "/v1/auth/toss/login",
        json={"authorization_code": "valid-code-xx", "referrer": "DEFAULT"},
    )
    blob = r.text.lower()
    assert "toss-access-secret" not in blob
    assert "toss-refresh-secret" not in blob


def test_payment_rejects_unverified_client_identity(payment_env):
    client, _, _ = payment_env
    r = client.post(
        "/v1/payments/iap/intents",
        json={"product_id": "song_detail", "analysis_id": "abc"},
        headers={"X-User-Id": "forged", "X-VAgent-User-Key": "forged"},
    )
    assert r.status_code == 401


def test_order_replay_same_user_same_resource_idempotent(payment_env):
    from backend.app.db.session import session_scope

    with session_scope() as session:
        user = get_or_create_user(session, provider="TOSS", subject="443731104")
        aid = uuid.uuid4().hex
        session.add(Analysis(id=aid, user_id=user.id, status="completed"))
        session.flush()
        o1, e1, c1 = grant_from_purchase(
            session,
            user_id=user.id,
            toss_order_id="order-same",
            product_id="song_detail",
            resource_type="ANALYSIS",
            resource_id=aid,
            entitlement_type="SONG_DETAIL",
            sku="sku.song.detail.test",
        )
        o2, e2, c2 = grant_from_purchase(
            session,
            user_id=user.id,
            toss_order_id="order-same",
            product_id="song_detail",
            resource_type="ANALYSIS",
            resource_id=aid,
            entitlement_type="SONG_DETAIL",
            sku="sku.song.detail.test",
        )
        assert o1.id == o2.id
        assert e1.id == e2.id
        assert c1 is True
        assert c2 is False
        assert session.scalars(select(Entitlement)).all().__len__() == 1


def test_order_replay_different_user_rejected(payment_env):
    from backend.app.db.session import session_scope

    with session_scope() as session:
        a = get_or_create_user(session, provider="TOSS", subject="user-a")
        b = get_or_create_user(session, provider="TOSS", subject="user-b")
        aid = uuid.uuid4().hex
        session.add(Analysis(id=aid, user_id=a.id, status="completed"))
        session.flush()
        grant_from_purchase(
            session,
            user_id=a.id,
            toss_order_id="order-x",
            product_id="song_detail",
            resource_type="ANALYSIS",
            resource_id=aid,
            entitlement_type="SONG_DETAIL",
            sku="sku.a",
        )
        with pytest.raises(PaymentOrderBindingMismatch):
            grant_from_purchase(
                session,
                user_id=b.id,
                toss_order_id="order-x",
                product_id="song_detail",
                resource_type="ANALYSIS",
                resource_id=aid,
                entitlement_type="SONG_DETAIL",
                sku="sku.a",
            )


def test_order_replay_different_resource_rejected(payment_env):
    from backend.app.db.session import session_scope

    with session_scope() as session:
        user = get_or_create_user(session, provider="TOSS", subject="user-a")
        a1, a2 = uuid.uuid4().hex, uuid.uuid4().hex
        session.add(Analysis(id=a1, user_id=user.id, status="completed"))
        session.add(Analysis(id=a2, user_id=user.id, status="completed"))
        session.flush()
        grant_from_purchase(
            session,
            user_id=user.id,
            toss_order_id="order-res",
            product_id="song_detail",
            resource_type="ANALYSIS",
            resource_id=a1,
            entitlement_type="SONG_DETAIL",
            sku="sku.a",
        )
        with pytest.raises(PaymentOrderBindingMismatch):
            grant_from_purchase(
                session,
                user_id=user.id,
                toss_order_id="order-res",
                product_id="song_detail",
                resource_type="ANALYSIS",
                resource_id=a2,
                entitlement_type="SONG_DETAIL",
                sku="sku.a",
            )


def test_order_replay_different_product_rejected(payment_env):
    from backend.app.db.session import session_scope

    with session_scope() as session:
        user = get_or_create_user(session, provider="TOSS", subject="user-a")
        aid = uuid.uuid4().hex
        session.add(Analysis(id=aid, user_id=user.id, status="completed"))
        session.flush()
        grant_from_purchase(
            session,
            user_id=user.id,
            toss_order_id="order-prod",
            product_id="song_detail",
            resource_type="ANALYSIS",
            resource_id=aid,
            entitlement_type="SONG_DETAIL",
            sku="sku.a",
        )
        with pytest.raises(PaymentOrderBindingMismatch):
            grant_from_purchase(
                session,
                user_id=user.id,
                toss_order_id="order-prod",
                product_id="diagnostic_full",
                resource_type="ANALYSIS",
                resource_id=aid,
                entitlement_type="DIAGNOSTIC",
                sku="sku.a",
            )


def test_verified_refund_revokes_entitlement(payment_env):
    from backend.app.db.session import session_scope

    with session_scope() as session:
        user = get_or_create_user(session, provider="TOSS", subject="user-a")
        aid = uuid.uuid4().hex
        session.add(Analysis(id=aid, user_id=user.id, status="completed"))
        session.flush()
        _, ent, _ = grant_from_purchase(
            session,
            user_id=user.id,
            toss_order_id="order-ref",
            product_id="song_detail",
            resource_type="ANALYSIS",
            resource_id=aid,
            entitlement_type="SONG_DETAIL",
            sku="sku.a",
        )
        assert ent.status == "ACTIVE"
        order = revoke_from_refund(session, toss_order_id="order-ref")
        assert order is not None
        assert order.status == "REFUNDED"
        session.refresh(ent)
        assert ent.status == "REVOKED"


def test_toss_iap_provider_fail_closed(tmp_path):
    p = TossIAPEntitlementProvider(tmp_path / "e.json")
    with pytest.raises(RuntimeError, match="UNVERIFIED_PAYMENT_PROVIDER"):
        p.grant_unlock("u", "ANALYSIS", "a", "SONG_DETAIL", "x")


def test_production_mock_unlock_403_even_with_allow_flag(payment_env, monkeypatch):
    client, _, _ = payment_env
    monkeypatch.setenv("VAGENT_ENV", "production")
    monkeypatch.setenv("ALLOW_MOCK_PREMIUM", "true")
    r = client.post(
        "/v1/analyses/not-a-real-id/mock-unlock-detail",
        headers={"X-User-Id": "u1", "X-VAgent-User-Key": "u1"},
    )
    assert r.status_code in (401, 403, 404)


def test_payment_enabled_requires_verified_identity(monkeypatch):
    monkeypatch.setenv("PAYMENTS_ENABLED", "true")
    monkeypatch.setenv("TOSS_LOGIN_ENABLED", "false")
    monkeypatch.setenv("VAGENT_ENV", "production")
    blockers = validate_payment_production_config()
    assert "UNVERIFIED_IDENTITY_WITH_PAYMENTS" in blockers


def test_payment_enabled_requires_real_skus(monkeypatch):
    monkeypatch.setenv("PAYMENTS_ENABLED", "true")
    monkeypatch.setenv("TOSS_LOGIN_ENABLED", "true")
    monkeypatch.setenv("VAGENT_SESSION_SECRET", "x" * 16)
    monkeypatch.setenv("TOSS_MTLS_CERT_PATH", "")
    monkeypatch.setenv("TOSS_MTLS_KEY_PATH", "")
    monkeypatch.setenv("IAP_SONG_DETAIL_SKU", "vagent.song_detail")
    blockers = validate_payment_production_config()
    assert any(b.startswith("PLACEHOLDER_SKU") for b in blockers)


def test_purchase_intent_and_grant(payment_env):
    client, iap, svc = payment_env
    headers = _login(client)
    import io
    import numpy as np
    import soundfile as sf

    t = np.arange(int(16000 * 0.4)) / 16000
    y = (0.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    buf = io.BytesIO()
    sf.write(buf, y, 16000, format="WAV")
    created = client.post(
        "/v1/analyses",
        files={"file": ("t.wav", buf.getvalue(), "audio/wav")},
        data={"analysis_mode": "FUNCTIONAL", "input_mode": "VOCAL_ONLY", "separate": "false"},
        headers=headers,
    )
    assert created.status_code == 200, created.text
    aid = created.json()["analysis_id"]
    intent = client.post(
        "/v1/payments/iap/intents",
        json={"product_id": "song_detail", "analysis_id": aid},
        headers=headers,
    )
    assert intent.status_code == 200, intent.text
    oid = str(uuid.uuid4())
    iap.orders[oid] = {
        "sku": intent.json()["sku"],
        "status": "PAYMENT_COMPLETED",
        "user": "443731104",
        "result_type": "SUCCESS",
    }
    grant = client.post(
        "/v1/payments/iap/grant",
        json={"intent_id": intent.json()["intent_id"], "order_id": oid},
        headers=headers,
    )
    assert grant.status_code == 200, grant.text
    assert grant.json()["granted"] is True
    # idempotent
    grant2 = client.post(
        "/v1/payments/iap/grant",
        json={"intent_id": intent.json()["intent_id"], "order_id": oid},
        headers=headers,
    )
    assert grant2.status_code == 200


def test_result_type_must_be_success(payment_env):
    client, iap, _ = payment_env
    headers = _login(client)
    from backend.app.db.session import session_scope

    with session_scope() as session:
        user = get_or_create_user(session, provider="TOSS", subject="443731104")
        aid = uuid.uuid4().hex
        session.add(Analysis(id=aid, user_id=user.id, status="completed"))
        session.flush()
        analysis_id = aid
    intent = client.post(
        "/v1/payments/iap/intents",
        json={"product_id": "song_detail", "analysis_id": analysis_id},
        headers=headers,
    )
    assert intent.status_code == 200, intent.text
    oid = str(uuid.uuid4())
    iap.orders[oid] = {
        "sku": intent.json()["sku"],
        "status": "PAYMENT_COMPLETED",
        "user": "443731104",
        "result_type": "FAIL",
    }
    grant = client.post(
        "/v1/payments/iap/grant",
        json={"intent_id": intent.json()["intent_id"], "order_id": oid},
        headers=headers,
    )
    assert grant.status_code in (502, 409, 403)


def test_miniapp_mismatch_does_not_grant(payment_env):
    client, iap, _ = payment_env
    headers = _login(client)
    from backend.app.db.session import session_scope

    with session_scope() as session:
        user = get_or_create_user(session, provider="TOSS", subject="443731104")
        aid = uuid.uuid4().hex
        session.add(Analysis(id=aid, user_id=user.id, status="completed"))
        analysis_id = aid
    intent = client.post(
        "/v1/payments/iap/intents",
        json={"product_id": "song_detail", "analysis_id": analysis_id},
        headers=headers,
    )
    oid = str(uuid.uuid4())
    iap.orders[oid] = {
        "sku": intent.json()["sku"],
        "status": "MINIAPP_MISMATCH",
        "user": "443731104",
        "result_type": "SUCCESS",
    }
    grant = client.post(
        "/v1/payments/iap/grant",
        json={"intent_id": intent.json()["intent_id"], "order_id": oid},
        headers=headers,
    )
    assert grant.status_code == 403


def test_pending_recovery_requires_unambiguous_intent(payment_env):
    client, iap, _ = payment_env
    headers = _login(client)
    from backend.app.db.session import session_scope

    with session_scope() as session:
        user = get_or_create_user(session, provider="TOSS", subject="443731104")
        a1, a2 = uuid.uuid4().hex, uuid.uuid4().hex
        session.add(Analysis(id=a1, user_id=user.id, status="completed"))
        session.add(Analysis(id=a2, user_id=user.id, status="completed"))
    i1 = client.post(
        "/v1/payments/iap/intents",
        json={"product_id": "song_detail", "analysis_id": a1},
        headers=headers,
    )
    i2 = client.post(
        "/v1/payments/iap/intents",
        json={"product_id": "song_detail", "analysis_id": a2},
        headers=headers,
    )
    assert i1.status_code == 200 and i2.status_code == 200
    oid = str(uuid.uuid4())
    iap.orders[oid] = {
        "sku": i1.json()["sku"],
        "status": "PAYMENT_COMPLETED",
        "user": "443731104",
        "result_type": "SUCCESS",
    }
    rec = client.post(
        "/v1/payments/iap/recover",
        json={"order_id": oid, "sku": i1.json()["sku"]},
        headers=headers,
    )
    assert rec.status_code == 409
    assert rec.json()["detail"]["error"]["code"] == "AMBIGUOUS_PENDING_PURCHASE"


def test_client_cannot_fake_refund(payment_env):
    client, iap, _ = payment_env
    headers = _login(client)
    oid = str(uuid.uuid4())
    iap.orders[oid] = {
        "sku": "sku.song.detail.test",
        "status": "PAYMENT_COMPLETED",
        "user": "443731104",
        "result_type": "SUCCESS",
    }
    r = client.post("/v1/payments/iap/refund", json={"order_id": oid}, headers=headers)
    assert r.status_code == 409
