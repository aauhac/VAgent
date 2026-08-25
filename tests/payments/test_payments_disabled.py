"""PAYMENTS_ENABLED=false must fail-closed for IAP and expose catalog flag."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.app.db.models import Base, PaymentIntent
from backend.app.db.session import reset_engine
from backend.app.payments.errors import PaymentError
from backend.app.payments.service import create_intent, require_payments_enabled
from backend.app.payments.toss_clients import set_iap_client, set_login_client
from backend.app.products.catalog import product_catalog
from pathlib import Path


class FakeLoginClient:
    def exchange_code(self, authorization_code: str, referrer: str) -> dict:
        return {
            "accessToken": "toss-access-secret",
            "refreshToken": "toss-refresh-secret",
            "tokenType": "Bearer",
            "expiresIn": 3600,
        }

    def login_me(self, access_token: str) -> dict:
        return {"userKey": 443731104}


class FakeIapClient:
    def get_order_status(self, order_id: str, *, toss_user_key: str | None = None):
        from backend.app.payments.toss_clients import TossOrderStatus

        return TossOrderStatus(order_id, None, "NOT_FOUND", None, "SUCCESS", {})


@pytest.fixture()
def payments_off_env(tmp_path, monkeypatch):
    db = tmp_path / "pay.sqlite"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db}")
    monkeypatch.setenv("VAGENT_ENV", "development")
    monkeypatch.setenv("VAGENT_SESSION_SECRET", "test-session-secret-not-for-prod")
    monkeypatch.setenv("PAYMENTS_ENABLED", "false")
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
    set_iap_client(FakeIapClient())
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
    yield client
    set_iap_client(None)
    set_login_client(None)
    reset_engine()


def test_products_exposes_payments_enabled_false(payments_off_env, monkeypatch):
    monkeypatch.setenv("PAYMENTS_ENABLED", "false")
    cat = product_catalog()
    assert cat["payments_enabled"] is False
    client = payments_off_env
    res = client.get("/v1/products")
    assert res.status_code == 200
    assert res.json()["payments_enabled"] is False


def test_intent_blocked_when_payments_disabled(payments_off_env):
    client = payments_off_env
    login = client.post(
        "/v1/auth/toss/login",
        json={"authorization_code": "valid-code-xx", "referrer": "SANDBOX"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["session_token"]
    res = client.post(
        "/v1/payments/iap/intents",
        headers={"Authorization": f"Bearer {token}"},
        json={"product_id": "song_detail", "analysis_id": "does-not-matter"},
    )
    assert res.status_code == 503
    body = res.json()
    assert body["detail"]["error"]["code"] == "PAYMENTS_DISABLED"
    from backend.app.db.session import session_scope

    with session_scope() as session:
        count = session.scalar(select(func.count()).select_from(PaymentIntent))
    assert int(count or 0) == 0


def test_require_payments_enabled_helper(monkeypatch):
    monkeypatch.setenv("PAYMENTS_ENABLED", "false")
    with pytest.raises(PaymentError) as exc:
        require_payments_enabled()
    assert exc.value.code == "PAYMENTS_DISABLED"


def test_create_intent_service_blocked(monkeypatch, payments_off_env):
    monkeypatch.setenv("PAYMENTS_ENABLED", "false")
    from backend.app.db.session import session_scope

    with pytest.raises(PaymentError) as exc:
        with session_scope() as session:
            create_intent(
                session,
                toss_user_key="443731104",
                product_id="song_detail",
                analysis_id="x",
                session_id=None,
            )
    assert exc.value.code == "PAYMENTS_DISABLED"


def test_products_payments_enabled_true(monkeypatch):
    monkeypatch.setenv("PAYMENTS_ENABLED", "true")
    assert product_catalog()["payments_enabled"] is True
