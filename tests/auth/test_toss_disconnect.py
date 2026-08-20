"""Toss login disconnect callback — official userKey + referrer schema."""

from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from backend.app.db.models import Analysis, Base
from backend.app.db.session import reset_engine
from backend.app.db.users import get_or_create_user
from backend.app.payments.toss_clients import set_iap_client, set_login_client


class NamedLoginClient:
    def __init__(self, user_key: str, name: str) -> None:
        self.user_key = user_key
        self.name = name

    def exchange_code(self, authorization_code: str, referrer: str) -> dict:
        return {
            "accessToken": f"access-{authorization_code}",
            "refreshToken": f"refresh-{authorization_code}",
            "tokenType": "Bearer",
            "expiresIn": 3600,
        }

    def login_me(self, access_token: str) -> dict:
        return {"userKey": self.user_key, "name": self.name}


@pytest.fixture()
def auth_env(tmp_path, monkeypatch):
    db = tmp_path / "auth.sqlite"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db}")
    monkeypatch.setenv("VAGENT_ENV", "development")
    monkeypatch.setenv("VAGENT_SESSION_SECRET", "test-session-secret-not-for-prod")
    monkeypatch.setenv("TOSS_LOGIN_ENABLED", "true")
    monkeypatch.setenv("TOSS_DISCONNECT_BASIC_USER", "cb-user")
    monkeypatch.setenv("TOSS_DISCONNECT_BASIC_PASSWORD", "cb-pass")
    monkeypatch.setenv("RUNTIME_DIR", str(tmp_path / "runtime"))
    (tmp_path / "runtime").mkdir()
    reset_engine()
    from backend.app.config import get_runtime_dir
    from backend.app.db.session import get_engine, session_scope

    get_runtime_dir.cache_clear()
    engine = get_engine()
    assert engine is not None
    Base.metadata.create_all(engine)
    from backend.app.main import app

    client = TestClient(app, raise_server_exceptions=True)
    yield client
    set_iap_client(None)
    set_login_client(None)
    reset_engine()
    get_runtime_dir.cache_clear()


def _basic() -> dict[str, str]:
    raw = base64.b64encode(b"cb-user:cb-pass").decode("ascii")
    return {"Authorization": f"Basic {raw}"}


def test_same_name_users_do_not_share_session(auth_env, monkeypatch):
    client = auth_env
    set_login_client(NamedLoginClient("111", "김민수"))
    a = client.post("/v1/auth/toss/login", json={"authorization_code": "code-aaaaaa", "referrer": "SANDBOX"})
    assert a.status_code == 200
    assert "김민수" not in a.text
    ha = {"Authorization": f"Bearer {a.json()['session_token']}"}
    set_login_client(NamedLoginClient("222", "김민수"))
    b = client.post("/v1/auth/toss/login", json={"authorization_code": "code-bbbbbb", "referrer": "SANDBOX"})
    assert b.status_code == 200
    hb = {"Authorization": f"Bearer {b.json()['session_token']}"}
    assert a.json()["session_token"] != b.json()["session_token"]
    me_a = client.get("/v1/auth/me", headers=ha)
    me_b = client.get("/v1/auth/me", headers=hb)
    assert me_a.status_code == 200
    assert me_b.status_code == 200


def test_disconnect_revokes_session_not_analysis(auth_env):
    client = auth_env
    set_login_client(NamedLoginClient("443731104", "김민수"))
    login = client.post("/v1/auth/toss/login", json={"authorization_code": "code-cccccc", "referrer": "DEFAULT"})
    token = login.json()["session_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/v1/auth/me", headers=headers).status_code == 200

    from backend.app.db.session import session_scope

    with session_scope() as session:
        user = get_or_create_user(session, provider="TOSS", subject="443731104")
        session.add(Analysis(id="a" * 32, user_id=user.id, status="completed"))

    r = client.post(
        "/v1/auth/toss/disconnect",
        headers=_basic(),
        json={"userKey": 443731104, "referrer": "UNLINK"},
    )
    assert r.status_code == 200
    assert client.get("/v1/auth/me", headers=headers).status_code == 401
    with session_scope() as session:
        row = session.get(Analysis, "a" * 32)
        assert row is not None
        assert row.deleted_at is None


def test_disconnect_get_schema_and_rejects_bad_auth(auth_env):
    client = auth_env
    bad = client.get("/v1/auth/toss/disconnect", params={"userKey": "1", "referrer": "UNLINK"})
    assert bad.status_code == 401
    ok = client.get(
        "/v1/auth/toss/disconnect",
        params={"userKey": "1", "referrer": "WITHDRAWAL_TOSS"},
        headers=_basic(),
    )
    assert ok.status_code == 200


def test_disconnect_unconfigured_is_unavailable(auth_env, monkeypatch):
    client = auth_env
    monkeypatch.delenv("TOSS_DISCONNECT_BASIC_USER", raising=False)
    monkeypatch.delenv("TOSS_DISCONNECT_BASIC_PASSWORD", raising=False)
    r = client.post(
        "/v1/auth/toss/disconnect",
        json={"userKey": "1", "referrer": "UNLINK"},
    )
    assert r.status_code == 503


def test_disconnect_accepts_numeric_user_key_zero(auth_env):
    """Toss Console callback test posts userKey=0; must not coerce to empty."""
    client = auth_env
    r = client.post(
        "/v1/auth/toss/disconnect",
        headers=_basic(),
        json={"userKey": 0, "referrer": "UNLINK"},
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_disconnect_rejects_empty_user_key(auth_env):
    client = auth_env
    r = client.post(
        "/v1/auth/toss/disconnect",
        headers=_basic(),
        json={"userKey": "", "referrer": "UNLINK"},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "invalid disconnect payload"


def test_disconnect_rejects_missing_user_key(auth_env):
    client = auth_env
    r = client.post(
        "/v1/auth/toss/disconnect",
        headers=_basic(),
        json={"referrer": "UNLINK"},
    )
    assert r.status_code == 422


def test_disconnect_rejects_invalid_referrer(auth_env):
    client = auth_env
    r = client.post(
        "/v1/auth/toss/disconnect",
        headers=_basic(),
        json={"userKey": 1, "referrer": "NOT_A_REFERRER"},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "invalid disconnect payload"


def test_disconnect_rejects_bad_basic_auth(auth_env):
    client = auth_env
    bad = base64.b64encode(b"cb-user:wrong-pass").decode("ascii")
    r = client.post(
        "/v1/auth/toss/disconnect",
        headers={"Authorization": f"Basic {bad}"},
        json={"userKey": 1, "referrer": "UNLINK"},
    )
    assert r.status_code == 401
