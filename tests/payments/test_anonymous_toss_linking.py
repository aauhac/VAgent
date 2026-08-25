"""Canonical identity: anon hash ↔ verified Toss userKey mapping.

Replaces the destructive ownership migration this file used to test. Rows are no longer
moved at login; a mapping is recorded and resolution unions the identity. That is what
lets history survive a session expiry — the old design left the anonymous user owning
nothing, so losing the session token emptied history.

Role split under test:
  - the hash is the canonical identity for data ownership
  - a verified Toss session remains the only thing that can buy or grant
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.db.models import Analysis, Base, Entitlement, User, UserIdentityLink
from backend.app.db.session import reset_engine, session_scope
from backend.app.db.users import get_or_create_user
from backend.app.payments import rate_limit
from backend.app.payments.toss_clients import TossApiError, set_iap_client, set_login_client

VERIFIED_USER_KEY = "443731104"
OTHER_USER_KEY = "900000001"
ANON_A = "anon-A-hash"
ANON_B = "anon-B-hash"


class FakeLoginClient:
    def __init__(self, user_key: str = VERIFIED_USER_KEY) -> None:
        self.user_key = user_key

    def exchange_code(self, authorization_code: str, referrer: str) -> dict:
        if authorization_code.startswith("bad"):
            raise TossApiError("INVALID_GRANT", retryable=False)
        return {"accessToken": "toss-access-secret", "tokenType": "Bearer", "expiresIn": 3600}

    def login_me(self, access_token: str) -> dict:
        return {"userKey": int(self.user_key)}


@pytest.fixture()
def link_env(tmp_path, monkeypatch):
    db = tmp_path / "link.sqlite"
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db}")
    monkeypatch.setenv("VAGENT_ENV", "development")
    monkeypatch.setenv("VAGENT_SESSION_SECRET", "test-session-secret-not-for-prod")
    monkeypatch.setenv("PAYMENTS_ENABLED", "true")
    monkeypatch.setenv("TOSS_LOGIN_ENABLED", "true")
    monkeypatch.setenv("IAP_SONG_DETAIL_SKU", "sku.song.detail.test")
    monkeypatch.setenv("IAP_DIAGNOSTIC_FULL_SKU", "sku.diag.full.test")
    monkeypatch.setenv("IAP_DIAGNOSTIC_UPGRADE_SKU", "sku.diag.upgrade.test")
    monkeypatch.setenv("RUNTIME_DIR", str(runtime))
    rate_limit.reset()
    reset_engine()
    from backend.app.config import get_runtime_dir

    get_runtime_dir.cache_clear()
    from backend.app.db.session import get_engine

    engine = get_engine()
    assert engine is not None
    Base.metadata.create_all(engine)
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
    yield client, login
    set_login_client(None)
    set_iap_client(None)
    reset_engine()
    get_runtime_dir.cache_clear()


def _seed_anonymous_analysis(subject: str) -> str:
    aid = uuid.uuid4().hex
    with session_scope() as session:
        user = get_or_create_user(session, provider="TOSS_ANONYMOUS", subject=subject)
        session.add(Analysis(id=aid, user_id=user.id, status="completed"))
    return aid


def _owner_of(analysis_id: str) -> tuple[str, str]:
    with session_scope() as session:
        row = session.get(Analysis, analysis_id)
        assert row is not None
        user = session.get(User, row.user_id)
        assert user is not None
        return user.external_provider, user.external_subject


def _login(client: TestClient, *, anon_subject: str | None, code: str = "valid-code-xx"):
    headers = {"Content-Type": "application/json"}
    if anon_subject:
        headers["X-VAgent-User-Key"] = anon_subject
    return client.post(
        "/v1/auth/toss/login",
        json={"authorization_code": code, "referrer": "SANDBOX"},
        headers=headers,
    )


def _intent(client: TestClient, analysis_id: str, token: str):
    return client.post(
        "/v1/payments/iap/intents",
        json={"product_id": "song_detail", "analysis_id": analysis_id},
        headers={"Authorization": f"Bearer {token}"},
    )


def _history_ids(client: TestClient, **headers) -> set[str]:
    r = client.get("/v1/history", headers=headers)
    assert r.status_code == 200, r.text
    return {i["analysis_id"] for i in r.json()["items"]}


# --- the original blocker, now solved without moving data -----------------------------


def test_anonymous_analysis_is_purchasable_after_toss_login(link_env):
    client, _ = link_env
    aid = _seed_anonymous_analysis(ANON_A)
    r = _login(client, anon_subject=ANON_A)
    assert r.status_code == 200, r.text
    assert r.json()["identity_linked"] is True
    token = r.json()["session_token"]

    intent = _intent(client, aid, token)
    assert intent.status_code == 200, intent.text
    assert intent.json()["sku"] == "sku.song.detail.test"


def test_login_does_not_move_ownership(link_env):
    """The regression that emptied history: linking must be non-destructive."""
    client, _ = link_env
    aid = _seed_anonymous_analysis(ANON_A)
    assert _login(client, anon_subject=ANON_A).status_code == 200
    assert _owner_of(aid) == ("TOSS_ANONYMOUS", ANON_A)


def test_history_survives_losing_the_session_token(link_env):
    """PHASE 2's whole point: an expired session must not empty history."""
    client, _ = link_env
    aid = _seed_anonymous_analysis(ANON_A)
    token = _login(client, anon_subject=ANON_A).json()["session_token"]

    assert aid in _history_ids(client, Authorization=f"Bearer {token}")
    # Session gone; the device still presents the same getAnonymousKey hash.
    assert aid in _history_ids(client, **{"X-VAgent-User-Key": ANON_A})


def test_history_after_login_includes_both_eras(link_env):
    client, _ = link_env
    before = _seed_anonymous_analysis(ANON_A)
    token = _login(client, anon_subject=ANON_A).json()["session_token"]
    # An analysis created while logged in lands on the canonical user.
    with session_scope() as session:
        from backend.app.db.analysis_repo import get_user_by_subject

        user = get_user_by_subject(session, VERIFIED_USER_KEY)
        after = uuid.uuid4().hex
        session.add(Analysis(id=after, user_id=user.id, status="completed"))

    ids = _history_ids(client, Authorization=f"Bearer {token}")
    assert before in ids and after in ids


# --- link creation rules ---------------------------------------------------------------


def test_failed_login_creates_no_link(link_env):
    client, _ = link_env
    aid = _seed_anonymous_analysis(ANON_A)
    r = _login(client, anon_subject=ANON_A, code="bad-code-xxxx")
    assert r.status_code in (401, 503)
    assert _owner_of(aid) == ("TOSS_ANONYMOUS", ANON_A)
    with session_scope() as session:
        assert session.scalars(select(UserIdentityLink)).first() is None


def test_repeat_login_is_idempotent(link_env):
    client, _ = link_env
    _seed_anonymous_analysis(ANON_A)
    assert _login(client, anon_subject=ANON_A).json()["identity_linked"] is True
    assert _login(client, anon_subject=ANON_A).json()["identity_linked"] is True
    with session_scope() as session:
        links = list(session.scalars(select(UserIdentityLink)))
    assert len(links) == 1


def test_second_toss_account_cannot_capture_an_existing_link(link_env):
    """Shared device: the first account keeps its canonical identity."""
    client, login = link_env
    aid = _seed_anonymous_analysis(ANON_A)
    assert _login(client, anon_subject=ANON_A).json()["identity_linked"] is True

    login.user_key = OTHER_USER_KEY
    r = _login(client, anon_subject=ANON_A)
    assert r.status_code == 200
    assert r.json()["identity_linked"] is False

    with session_scope() as session:
        keys = [link.toss_user_key for link in session.scalars(select(UserIdentityLink))]
    assert keys == [VERIFIED_USER_KEY]

    # The intruder's session cannot reach the first user's analysis.
    token = r.json()["session_token"]
    assert _intent(client, aid, token).status_code == 404


def test_many_hashes_map_to_one_user_key(link_env):
    """N:1 — a second device's hash joins the same canonical identity."""
    client, _ = link_env
    first = _seed_anonymous_analysis(ANON_A)
    assert _login(client, anon_subject=ANON_A).status_code == 200
    second = _seed_anonymous_analysis(ANON_B)
    assert _login(client, anon_subject=ANON_B).status_code == 200

    with session_scope() as session:
        links = list(session.scalars(select(UserIdentityLink)))
        assert len(links) == 2
        assert {link.toss_user_key for link in links} == {VERIFIED_USER_KEY}
        assert len({link.canonical_user_id for link in links}) == 1

    # Either device sees the whole identity.
    assert {first, second} <= _history_ids(client, **{"X-VAgent-User-Key": ANON_A})
    assert {first, second} <= _history_ids(client, **{"X-VAgent-User-Key": ANON_B})


# --- isolation -------------------------------------------------------------------------


def test_other_anonymous_hash_cannot_claim_another_analysis(link_env):
    client, _ = link_env
    aid_a = _seed_anonymous_analysis(ANON_A)
    _seed_anonymous_analysis(ANON_B)
    token = _login(client, anon_subject=ANON_B).json()["session_token"]

    assert _owner_of(aid_a) == ("TOSS_ANONYMOUS", ANON_A)
    stolen = _intent(client, aid_a, token)
    assert stolen.status_code == 404
    assert aid_a not in _history_ids(client, **{"X-VAgent-User-Key": ANON_B})


def test_unknown_analysis_id_cannot_create_intent(link_env):
    client, _ = link_env
    _seed_anonymous_analysis(ANON_A)
    token = _login(client, anon_subject=ANON_A).json()["session_token"]
    assert _intent(client, uuid.uuid4().hex, token).status_code == 404


def test_hash_alone_cannot_create_a_payment_intent(link_env):
    """Data ownership uses the hash; buying still requires a verified session."""
    client, _ = link_env
    aid = _seed_anonymous_analysis(ANON_A)
    _login(client, anon_subject=ANON_A)

    r = client.post(
        "/v1/payments/iap/intents",
        json={"product_id": "song_detail", "analysis_id": aid},
        headers={"X-VAgent-User-Key": ANON_A},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["error"]["code"] == "AUTH_REQUIRED"


def test_existing_toss_user_analyses_are_preserved(link_env):
    client, _ = link_env
    prior = uuid.uuid4().hex
    with session_scope() as session:
        verified = get_or_create_user(session, provider="TOSS", subject=VERIFIED_USER_KEY)
        session.add(Analysis(id=prior, user_id=verified.id, status="completed"))
    aid = _seed_anonymous_analysis(ANON_A)

    token = _login(client, anon_subject=ANON_A).json()["session_token"]
    ids = _history_ids(client, Authorization=f"Bearer {token}")
    assert {prior, aid} <= ids


def test_entitlement_is_not_duplicated_by_linking(link_env):
    client, _ = link_env
    aid = _seed_anonymous_analysis(ANON_A)
    with session_scope() as session:
        anon = session.scalar(
            select(User).where(
                User.external_provider == "TOSS_ANONYMOUS", User.external_subject == ANON_A
            )
        )
        session.add(
            Entitlement(
                user_id=anon.id,
                resource_type="ANALYSIS",
                resource_id=aid,
                entitlement_type="SONG_DETAIL",
                status="ACTIVE",
            )
        )

    assert _login(client, anon_subject=ANON_A).status_code == 200

    with session_scope() as session:
        rows = list(
            session.scalars(
                select(Entitlement).where(
                    Entitlement.resource_id == aid,
                    Entitlement.entitlement_type == "SONG_DETAIL",
                )
            )
        )
    assert len(rows) == 1
    # And the purchase is visible as already-owned, so it cannot be sold twice.
    token = _login(client, anon_subject=ANON_A).json()["session_token"]
    assert _intent(client, aid, token).status_code == 409


def test_rewarded_daily_cap_is_not_reset_by_linking(link_env):
    """Usage recorded before login must still count afterwards."""
    from backend.app.db.models import RewardedAdDailySlot

    client, _ = link_env
    _seed_anonymous_analysis(ANON_A)
    day = "2026-08-25"
    with session_scope() as session:
        session.add(
            RewardedAdDailySlot(
                principal_key=f"TOSS_ANONYMOUS:{ANON_A}", seoul_day=day, slot_index=1
            )
        )

    assert _login(client, anon_subject=ANON_A).status_code == 200

    from backend.app.identity import ResolvedIdentity
    from backend.app.rewards.rewarded_detail import _used_today_db, principal_keys

    ident = ResolvedIdentity(
        provider="TOSS",
        subject=VERIFIED_USER_KEY,
        trust_mode="VERIFIED_TOSS_SUBJECT",
        authenticated=True,
        toss_user_key=VERIFIED_USER_KEY,
    )
    with session_scope() as session:
        used = _used_today_db(session, principal_keys(ident)[0], day, principal_keys(ident))
    assert used == 1
