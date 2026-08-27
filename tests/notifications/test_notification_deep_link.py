"""`intoss://vocalfb/notification-result` resolver.

The Smart Message campaign has one fixed 이동 URL, so the click carries no analysis id.
The server answers with this device's newest DELIVERED completion alert that it may
actually open. "Nothing to open" is a normal 200, not an error.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.db.models import Analysis, AnalysisCompletionNotification, Base
from backend.app.db.session import reset_engine, session_scope
from backend.app.db.users import get_or_create_user
from backend.app.notifications.completion import load_record
from backend.app.payments import rate_limit
from backend.app.payments.toss_clients import TossApiError, set_login_client, set_messenger_client

LATEST_PATH = "/v1/notifications/latest-result"
VERIFIED_USER_KEY = "443731104"
OTHER_USER_KEY = "900000001"
ANON_A = "anon-A-hash"
ANON_B = "anon-B-hash"

# Nothing identifying may cross the wire back to the client.
FORBIDDEN_RESPONSE_KEYS = ("recipient_key", "recipient_kind", "user_id", "userKey", "toss_user_key")


class FakeLoginClient:
    def __init__(self, user_key: str = VERIFIED_USER_KEY) -> None:
        self.user_key = user_key

    def exchange_code(self, authorization_code: str, referrer: str) -> dict:
        return {"accessToken": "toss-access-secret", "tokenType": "Bearer", "expiresIn": 3600}

    def login_me(self, access_token: str) -> dict:
        return {"userKey": int(self.user_key)}


class FakeMessengerClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def send_message(
        self,
        *,
        template_set_code: str,
        headers: dict[str, str],
        context: dict | None = None,
    ) -> str:
        self.calls.append(
            {
                "template_set_code": template_set_code,
                "headers": dict(headers),
                "context": dict(context or {}),
            }
        )
        return "SUCCESS"


@pytest.fixture()
def deep_link_env(tmp_path, monkeypatch):
    db = tmp_path / "deeplink.sqlite"
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db}")
    monkeypatch.setenv("VAGENT_ENV", "development")
    monkeypatch.setenv("VAGENT_SESSION_SECRET", "test-session-secret-not-for-prod")
    monkeypatch.setenv("RUNTIME_DIR", str(runtime))
    monkeypatch.setenv("TOSS_LOGIN_ENABLED", "true")
    monkeypatch.setenv("TOSS_ANALYSIS_COMPLETE_TEMPLATE_SET_CODE", "approved-template")
    rate_limit.reset()
    reset_engine()
    from backend.app.config import get_runtime_dir

    get_runtime_dir.cache_clear()
    from backend.app.db.session import get_engine

    engine = get_engine()
    assert engine is not None
    Base.metadata.create_all(engine)
    fake = FakeMessengerClient()
    set_messenger_client(fake)
    login = FakeLoginClient()
    set_login_client(login)
    from backend.app.api import routes as routes_mod
    from backend.app.diagnostic import DiagnosticSessionService
    from backend.app.jobs.runner import JobRunner
    from backend.app.main import app
    from backend.app.services.analysis_service import AnalysisService

    svc = AnalysisService()
    svc.runner = JobRunner(svc.runtime_dir, max_workers=1)
    routes_mod.service = svc
    routes_mod.diag = DiagnosticSessionService(svc.runtime_dir)
    client = TestClient(app, raise_server_exceptions=True)
    yield client, fake, svc.runtime_dir, login
    set_messenger_client(None)
    set_login_client(None)
    reset_engine()
    get_runtime_dir.cache_clear()


def _seed(runtime: Path, *, subject: str, provider: str = "TOSS_ANONYMOUS") -> str:
    aid = uuid.uuid4().hex
    with session_scope() as session:
        user = get_or_create_user(session, provider=provider, subject=subject)
        session.add(Analysis(id=aid, user_id=user.id, status="completed"))
    meta = runtime / aid
    meta.mkdir(parents=True, exist_ok=True)
    (meta / "analysis_meta.json").write_text(
        json.dumps({"user_id": subject, "analysis_id": aid}), encoding="utf-8"
    )
    (meta / "job_status.json").write_text(
        json.dumps({"analysis_id": aid, "status": "completed", "result": {}}), encoding="utf-8"
    )
    return aid


def _opt_in(client: TestClient, aid: str, subject: str) -> None:
    r = client.post(
        f"/v1/analyses/{aid}/completion-notification",
        headers={"X-VAgent-User-Key": subject},
    )
    assert r.status_code == 200, r.text


def _force_status(aid: str, status: str, *, sent_at: datetime | None = None) -> None:
    """Drive a record into a state the happy path cannot produce on demand.

    Safe to touch the DB row directly here: with DATABASE_URL set, the JSON mirror is
    never written, so the DB is the only store this suite reads.
    """
    with session_scope() as session:
        row = session.get(AnalysisCompletionNotification, aid)
        assert row is not None
        row.status = status
        row.sent_at = sent_at


def _soft_delete(aid: str) -> None:
    with session_scope() as session:
        row = session.get(Analysis, aid)
        assert row is not None
        row.deleted_at = datetime.now(timezone.utc)
        row.status = "deleted"


def _login(client: TestClient, anon_subject: str | None = None) -> str:
    headers = {}
    if anon_subject:
        headers["X-VAgent-User-Key"] = anon_subject
    r = client.post(
        "/v1/auth/toss/login",
        json={"authorization_code": "valid-code-xx", "referrer": "SANDBOX"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["session_token"]


def _latest(client: TestClient, *, anon: str | None = None, token: str | None = None):
    headers = {}
    if anon:
        headers["X-VAgent-User-Key"] = anon
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = client.get(LATEST_PATH, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


# --- resolution ---------------------------------------------------------------------


def test_single_sent_notification_resolves(deep_link_env):
    client, fake, runtime, _ = deep_link_env
    aid = _seed(runtime, subject=ANON_A)
    _opt_in(client, aid, ANON_A)
    assert len(fake.calls) == 1
    assert load_record(aid, runtime)["status"] == "SENT"

    body = _latest(client, anon=ANON_A)
    assert body["found"] is True
    assert body["analysis_id"] == aid
    assert body["sent_at"]


def test_newest_sent_wins(deep_link_env):
    client, _, runtime, _ = deep_link_env
    older = _seed(runtime, subject=ANON_A)
    _opt_in(client, older, ANON_A)
    newer = _seed(runtime, subject=ANON_A)
    _opt_in(client, newer, ANON_A)

    now = datetime.now(timezone.utc)
    _force_status(older, "SENT", sent_at=now - timedelta(hours=2))
    _force_status(newer, "SENT", sent_at=now)

    assert _latest(client, anon=ANON_A)["analysis_id"] == newer


def test_requested_is_ignored(deep_link_env, monkeypatch):
    client, fake, runtime, _ = deep_link_env
    monkeypatch.delenv("TOSS_ANALYSIS_COMPLETE_TEMPLATE_SET_CODE", raising=False)
    aid = _seed(runtime, subject=ANON_A)
    _opt_in(client, aid, ANON_A)
    assert fake.calls == []
    assert load_record(aid, runtime)["status"] == "REQUESTED"

    assert _latest(client, anon=ANON_A)["found"] is False


def test_failed_is_ignored(deep_link_env):
    client, _, runtime, _ = deep_link_env
    aid = _seed(runtime, subject=ANON_A)
    _opt_in(client, aid, ANON_A)
    _force_status(aid, "FAILED", sent_at=None)

    assert _latest(client, anon=ANON_A)["found"] is False


def test_sent_without_timestamp_is_skipped(deep_link_env):
    """A SENT row with no sent_at cannot be ordered, so it is not a deep-link target."""
    client, _, runtime, _ = deep_link_env
    aid = _seed(runtime, subject=ANON_A)
    _opt_in(client, aid, ANON_A)
    _force_status(aid, "SENT", sent_at=None)

    assert _latest(client, anon=ANON_A)["found"] is False


def test_deleted_latest_falls_through_to_next_usable(deep_link_env):
    """A newer deleted alert must not hide an older usable one."""
    client, _, runtime, _ = deep_link_env
    older = _seed(runtime, subject=ANON_A)
    _opt_in(client, older, ANON_A)
    newer = _seed(runtime, subject=ANON_A)
    _opt_in(client, newer, ANON_A)

    now = datetime.now(timezone.utc)
    _force_status(older, "SENT", sent_at=now - timedelta(hours=2))
    _force_status(newer, "SENT", sent_at=now)
    _soft_delete(newer)

    body = _latest(client, anon=ANON_A)
    assert body["found"] is True
    assert body["analysis_id"] == older


def test_not_found_is_a_normal_two_hundred(deep_link_env):
    client, _, runtime, _ = deep_link_env
    _seed(runtime, subject=ANON_A)
    r = client.get(LATEST_PATH, headers={"X-VAgent-User-Key": ANON_A})
    assert r.status_code == 200
    assert r.json() == {"found": False, "analysis_id": None, "sent_at": None}


# --- identity ----------------------------------------------------------------------


def test_anonymous_recipient_resolves_without_login(deep_link_env):
    """Section 16: alert tapped while never logged in."""
    client, _, runtime, _ = deep_link_env
    aid = _seed(runtime, subject=ANON_A)
    _opt_in(client, aid, ANON_A)

    body = _latest(client, anon=ANON_A)
    assert body["analysis_id"] == aid

    result = client.get(f"/v1/analyses/{aid}", headers={"X-VAgent-User-Key": ANON_A})
    assert result.status_code == 200


def test_verified_toss_recipient_resolves(deep_link_env):
    client, _, runtime, _ = deep_link_env
    token = _login(client)
    aid = _seed(runtime, subject=VERIFIED_USER_KEY, provider="TOSS")
    r = client.post(
        f"/v1/analyses/{aid}/completion-notification",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text

    body = _latest(client, token=token)
    assert body["found"] is True
    assert body["analysis_id"] == aid


def test_anonymous_to_toss_migrated_analysis_still_resolves(deep_link_env):
    """Section 15: linking moves the analysis while the alert keeps its ANON recipient."""
    client, _, runtime, _ = deep_link_env
    aid = _seed(runtime, subject=ANON_A)
    _opt_in(client, aid, ANON_A)
    assert load_record(aid, runtime)["status"] == "SENT"

    token = _login(client, ANON_A)
    body = _latest(client, anon=ANON_A, token=token)
    assert body["found"] is True
    assert body["analysis_id"] == aid

    result = client.get(f"/v1/analyses/{aid}", headers={"Authorization": f"Bearer {token}"})
    assert result.status_code == 200


def test_anonymous_header_still_resolves_after_login(deep_link_env):
    """Canonical identity: the hash owns the data, so a logged-out reopen still works.

    Deliberate role split — the hash is the identity for reading one's own data; buying
    still requires a verified Toss session (see tests/payments/test_anonymous_toss_linking).
    This is why tapping the alert works even after the session token expires.
    """
    client, _, runtime, _ = deep_link_env
    aid = _seed(runtime, subject=ANON_A)
    _opt_in(client, aid, ANON_A)
    _login(client, ANON_A)  # records the hash ↔ userKey link; moves nothing

    body = _latest(client, anon=ANON_A)
    assert body["found"] is True
    assert body["analysis_id"] == aid


def test_a_foreign_hash_still_resolves_nothing_after_login(deep_link_env):
    """The canonical rule widens nothing for someone presenting a different hash."""
    client, _, runtime, _ = deep_link_env
    aid = _seed(runtime, subject=ANON_A)
    _opt_in(client, aid, ANON_A)
    _login(client, ANON_A)

    assert _latest(client, anon=ANON_B)["found"] is False


# --- cross-user isolation ------------------------------------------------------------


def test_anonymous_users_are_isolated(deep_link_env):
    client, _, runtime, _ = deep_link_env
    aid_a = _seed(runtime, subject=ANON_A)
    _opt_in(client, aid_a, ANON_A)
    aid_b = _seed(runtime, subject=ANON_B)
    _opt_in(client, aid_b, ANON_B)

    assert _latest(client, anon=ANON_A)["analysis_id"] == aid_a
    assert _latest(client, anon=ANON_B)["analysis_id"] == aid_b


def test_verified_user_cannot_read_another_verified_users_alert(deep_link_env):
    client, _, runtime, login = deep_link_env
    token_a = _login(client)
    aid_a = _seed(runtime, subject=VERIFIED_USER_KEY, provider="TOSS")
    assert (
        client.post(
            f"/v1/analyses/{aid_a}/completion-notification",
            headers={"Authorization": f"Bearer {token_a}"},
        ).status_code
        == 200
    )

    login.user_key = OTHER_USER_KEY
    token_b = _login(client)
    body = _latest(client, token=token_b)
    assert body["found"] is False


def test_knowing_an_analysis_id_grants_nothing(deep_link_env):
    """The endpoint takes no analysis id — B cannot steer it at A's analysis."""
    client, _, runtime, _ = deep_link_env
    aid_a = _seed(runtime, subject=ANON_A)
    _opt_in(client, aid_a, ANON_A)
    _seed(runtime, subject=ANON_B)

    r = client.get(
        LATEST_PATH,
        params={"analysis_id": aid_a},
        headers={"X-VAgent-User-Key": ANON_B},
    )
    assert r.status_code == 200
    assert r.json()["found"] is False


# --- response hygiene ----------------------------------------------------------------


def test_response_never_leaks_identifiers(deep_link_env):
    client, _, runtime, _ = deep_link_env
    aid = _seed(runtime, subject=ANON_A)
    _opt_in(client, aid, ANON_A)
    token = _login(client, ANON_A)

    raw = client.get(
        LATEST_PATH,
        headers={"X-VAgent-User-Key": ANON_A, "Authorization": f"Bearer {token}"},
    )
    assert raw.status_code == 200
    text = raw.text
    assert set(raw.json()) == {"found", "analysis_id", "sent_at"}
    for token_name in FORBIDDEN_RESPONSE_KEYS:
        assert token_name not in text
    assert ANON_A not in text
    assert VERIFIED_USER_KEY not in text
