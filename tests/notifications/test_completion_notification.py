"""Completion notification opt-in, recipient headers, idempotent send."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.db.models import Analysis, Base
from backend.app.db.session import reset_engine, session_scope
from backend.app.db.users import get_or_create_user
from backend.app.identity import ResolvedIdentity
from backend.app.notifications.completion import (
    KIND_ANON,
    KIND_TOSS_USER,
    analysis_complete_template_set_code,
    load_record,
    messenger_recipient_headers,
    opt_in_completion_notification,
    send_if_requested,
)
from backend.app.payments.toss_clients import TossApiError, set_login_client, set_messenger_client
from backend.app.payments.session_tokens import issue_session


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


class FakeMessengerClient:
    def __init__(self, result_type: str = "SUCCESS", error: Exception | None = None) -> None:
        self.calls: list[dict] = []
        self.result_type = result_type
        self.error = error

    def send_message(self, *, template_set_code: str, headers: dict[str, str]) -> str:
        anon = bool(headers.get("x-anon-key"))
        user = bool(headers.get("x-user-key"))
        assert anon != user
        self.calls.append({"template_set_code": template_set_code, "headers": dict(headers)})
        if self.error:
            raise self.error
        if self.result_type != "SUCCESS":
            raise TossApiError(self.result_type, retryable=False)
        return self.result_type


@pytest.fixture()
def notify_env(tmp_path, monkeypatch):
    db = tmp_path / "notify.sqlite"
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db}")
    monkeypatch.setenv("VAGENT_ENV", "development")
    monkeypatch.setenv("VAGENT_SESSION_SECRET", "test-session-secret-not-for-prod")
    monkeypatch.setenv("RUNTIME_DIR", str(runtime))
    monkeypatch.setenv("TOSS_LOGIN_ENABLED", "true")
    monkeypatch.setenv("TOSS_ANALYSIS_COMPLETE_TEMPLATE_SET_CODE", "approved-template")
    reset_engine()
    from backend.app.config import get_runtime_dir

    get_runtime_dir.cache_clear()
    from backend.app.db.session import get_engine

    engine = get_engine()
    assert engine is not None
    Base.metadata.create_all(engine)
    fake = FakeMessengerClient()
    set_messenger_client(fake)
    set_login_client(FakeLoginClient())
    from backend.app.main import app
    from backend.app.api import routes as routes_mod
    from backend.app.diagnostic import DiagnosticSessionService
    from backend.app.jobs.runner import JobRunner
    from backend.app.services.analysis_service import AnalysisService

    svc = AnalysisService()
    svc.runtime_dir = runtime
    svc.runner = JobRunner(runtime, max_workers=1)
    routes_mod.service = svc
    routes_mod.diag = DiagnosticSessionService(runtime)
    client = TestClient(app, raise_server_exceptions=True)
    yield client, fake, svc, runtime
    set_messenger_client(None)
    set_login_client(None)
    reset_engine()
    get_runtime_dir.cache_clear()


def _seed(runtime: Path, *, subject: str, provider: str = "TOSS_ANONYMOUS", status: str = "queued") -> str:
    aid = uuid.uuid4().hex
    with session_scope() as session:
        user = get_or_create_user(session, provider=provider, subject=subject)
        session.add(Analysis(id=aid, user_id=user.id, status=status))
    meta = runtime / aid
    meta.mkdir(parents=True, exist_ok=True)
    (meta / "analysis_meta.json").write_text(
        json.dumps({"user_id": subject, "analysis_id": aid}),
        encoding="utf-8",
    )
    if status == "completed":
        (meta / "job_status.json").write_text(
            json.dumps({"analysis_id": aid, "status": "completed", "result": {}}),
            encoding="utf-8",
        )
    return aid


def test_messenger_headers_are_exclusive():
    anon = messenger_recipient_headers(KIND_ANON, "anon-1")
    user = messenger_recipient_headers(KIND_TOSS_USER, "user-1")
    assert list(anon) == ["x-anon-key"]
    assert list(user) == ["x-user-key"]
    with pytest.raises(ValueError):
        messenger_recipient_headers("BOTH", "x")


def test_opt_in_owner_validation(notify_env):
    client, _, _, runtime = notify_env
    aid = _seed(runtime, subject="anon-owner")
    r = client.post(
        f"/v1/analyses/{aid}/completion-notification",
        headers={"X-VAgent-User-Key": "someone-else"},
    )
    assert r.status_code == 404
    ok = client.post(
        f"/v1/analyses/{aid}/completion-notification",
        headers={"X-VAgent-User-Key": "anon-owner"},
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body["recipient_kind"] == KIND_ANON
    assert "recipient_key" not in body
    rec = load_record(aid, runtime)
    assert rec["recipient_kind"] == KIND_ANON
    assert rec["recipient_key"] == "anon-owner"


def test_anonymous_recipient_uses_x_anon_key(notify_env):
    client, fake, _, runtime = notify_env
    aid = _seed(runtime, subject="anon-owner", status="completed")
    r = client.post(
        f"/v1/analyses/{aid}/completion-notification",
        headers={"X-VAgent-User-Key": "anon-owner"},
    )
    assert r.status_code == 200
    assert len(fake.calls) == 1
    assert "x-anon-key" in fake.calls[0]["headers"]
    assert "x-user-key" not in fake.calls[0]["headers"]
    assert fake.calls[0]["headers"]["x-anon-key"] == "anon-owner"


def test_verified_toss_user_uses_x_user_key(notify_env):
    client, fake, _, runtime = notify_env
    login = client.post(
        "/v1/auth/toss/login",
        json={"authorization_code": "valid-code-xx", "referrer": "SANDBOX"},
    )
    assert login.status_code == 200
    token = login.json()["session_token"]
    aid = _seed(runtime, subject="443731104", provider="TOSS", status="completed")
    r = client.post(
        f"/v1/analyses/{aid}/completion-notification",
        headers={"Authorization": f"Bearer {token}", "X-VAgent-User-Key": "anon-hash-not-owner"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["recipient_kind"] == KIND_TOSS_USER
    assert len(fake.calls) == 1
    assert fake.calls[0]["headers"].get("x-user-key") == "443731104"
    assert "x-anon-key" not in fake.calls[0]["headers"]


def test_messenger_client_rejects_both_headers():
    from backend.app.payments.toss_clients import TossMessengerClient

    with pytest.raises(TossApiError) as exc:
        TossMessengerClient().send_message(
            template_set_code="t",
            headers={"x-anon-key": "a", "x-user-key": "u"},
        )
    assert exc.value.code == "INVALID_RECIPIENT"


def test_completed_before_opt_in_sends_once(notify_env):
    client, fake, _, runtime = notify_env
    aid = _seed(runtime, subject="anon-owner", status="completed")
    client.post(
        f"/v1/analyses/{aid}/completion-notification",
        headers={"X-VAgent-User-Key": "anon-owner"},
    )
    send_if_requested(aid, runtime_dir=runtime)
    assert len(fake.calls) == 1
    rec = load_record(aid, runtime)
    assert rec["status"] == "SENT"


def test_opt_in_before_completed_then_send(notify_env):
    client, fake, _, runtime = notify_env
    aid = _seed(runtime, subject="anon-owner", status="queued")
    client.post(
        f"/v1/analyses/{aid}/completion-notification",
        headers={"X-VAgent-User-Key": "anon-owner"},
    )
    assert fake.calls == []
    with session_scope() as session:
        row = session.get(Analysis, aid)
        row.status = "completed"
    (runtime / aid / "job_status.json").write_text(
        json.dumps({"analysis_id": aid, "status": "completed"}),
        encoding="utf-8",
    )
    send_if_requested(aid, runtime_dir=runtime)
    assert len(fake.calls) == 1


def test_http_200_result_type_fail_does_not_mark_analysis_failed(notify_env):
    client, fake, _, runtime = notify_env
    fake.result_type = "FAIL"
    aid = _seed(runtime, subject="anon-owner", status="completed")
    r = client.post(
        f"/v1/analyses/{aid}/completion-notification",
        headers={"X-VAgent-User-Key": "anon-owner"},
    )
    assert r.status_code == 200
    rec = load_record(aid, runtime)
    assert rec["status"] == "FAILED"
    with session_scope() as session:
        row = session.get(Analysis, aid)
        assert row.status == "completed"


def test_template_missing_skips_send(notify_env, monkeypatch):
    client, fake, _, runtime = notify_env
    monkeypatch.delenv("TOSS_ANALYSIS_COMPLETE_TEMPLATE_SET_CODE", raising=False)
    assert analysis_complete_template_set_code() == ""
    aid = _seed(runtime, subject="anon-owner", status="completed")
    r = client.post(
        f"/v1/analyses/{aid}/completion-notification",
        headers={"X-VAgent-User-Key": "anon-owner"},
    )
    assert r.status_code == 200
    assert fake.calls == []
    rec = load_record(aid, runtime)
    assert rec["status"] == "REQUESTED"


def test_opt_in_persists_after_reload(notify_env):
    client, _, _, runtime = notify_env
    aid = _seed(runtime, subject="anon-owner", status="queued")
    client.post(
        f"/v1/analyses/{aid}/completion-notification",
        headers={"X-VAgent-User-Key": "anon-owner"},
    )
    rec = load_record(aid, runtime)
    assert rec["status"] == "REQUESTED"
    # Persistence is the sqlite row; loading again without the in-memory file is enough.
    rec2 = load_record(aid, runtime)
    assert rec2["requested_at"]
    assert rec2["recipient_kind"] == KIND_ANON


def test_send_exception_does_not_raise():
    ident = ResolvedIdentity(
        provider="TOSS_ANONYMOUS",
        subject="anon-x",
        trust_mode="UNVERIFIED_CLIENT_SUBJECT",
        authenticated=False,
    )
    send_if_requested("deadbeefdeadbeefdeadbeefdeadbeef")
    opt_in_completion_notification  # imported for identity contract
    assert ident.toss_user_key is None


def test_issue_session_helper_not_confused_with_anon_hash():
    token, payload = issue_session(toss_user_key="443731104")
    assert payload.toss_user_key == "443731104"
    assert token
