"""Anonymous → verified Toss user linking at login, and the payment intent it unblocks.

Regression origin: a free analysis is owned by (TOSS_ANONYMOUS, anon-hash) while a
purchase runs as (TOSS, verified userKey). Without linking, create_intent's owner check
raises RESOURCE_NOT_FOUND and the miniapp shows "결제를 시작하지 못했어요".
Ownership checks are NOT relaxed — the anonymous row is migrated to the verified user.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.db.models import Analysis, Base, Entitlement, User
from backend.app.db.session import reset_engine, session_scope
from backend.app.db.users import get_or_create_user
from backend.app.payments import rate_limit
from backend.app.payments.toss_clients import TossApiError, set_iap_client, set_login_client

VERIFIED_USER_KEY = "443731104"
ANON_A = "anon-A-hash"
ANON_B = "anon-B-hash"


class FakeLoginClient:
    def exchange_code(self, authorization_code: str, referrer: str) -> dict:
        if authorization_code.startswith("bad"):
            raise TossApiError("INVALID_GRANT", retryable=False)
        return {"accessToken": "toss-access-secret", "tokenType": "Bearer", "expiresIn": 3600}

    def login_me(self, access_token: str) -> dict:
        return {"userKey": int(VERIFIED_USER_KEY)}


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
    # This suite logs in repeatedly; the login limiter is process-global and per-IP.
    rate_limit.reset()
    reset_engine()
    from backend.app.config import get_runtime_dir

    get_runtime_dir.cache_clear()
    from backend.app.db.session import get_engine

    engine = get_engine()
    assert engine is not None
    Base.metadata.create_all(engine)
    set_login_client(FakeLoginClient())
    from backend.app.main import app

    client = TestClient(app, raise_server_exceptions=True)
    yield client
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


def _login(client: TestClient, *, anon_subject: str | None, code: str = "valid-code-xx") -> object:
    headers = {"Content-Type": "application/json"}
    if anon_subject:
        headers["X-VAgent-User-Key"] = anon_subject
    return client.post(
        "/v1/auth/toss/login",
        json={"authorization_code": code, "referrer": "SANDBOX"},
        headers=headers,
    )


def test_anonymous_analysis_is_purchasable_after_toss_login(link_env):
    """The production blocker, end to end: anon analysis → login → intent 200."""
    client = link_env
    aid = _seed_anonymous_analysis(ANON_A)
    assert _owner_of(aid) == ("TOSS_ANONYMOUS", ANON_A)

    r = _login(client, anon_subject=ANON_A)
    assert r.status_code == 200, r.text
    token = r.json()["session_token"]

    # Ownership migrated to the verified Toss user — the check itself is unchanged.
    assert _owner_of(aid) == ("TOSS", VERIFIED_USER_KEY)

    intent = client.post(
        "/v1/payments/iap/intents",
        json={"product_id": "song_detail", "analysis_id": aid},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert intent.status_code == 200, intent.text
    body = intent.json()
    assert body["sku"] == "sku.song.detail.test"
    assert body["resource_id"] == aid

    with session_scope() as session:
        verified = session.scalar(
            select(User).where(
                User.external_provider == "TOSS", User.external_subject == VERIFIED_USER_KEY
            )
        )
        assert verified is not None
        row = session.get(Analysis, aid)
        assert row.user_id == verified.id


def test_failed_login_migrates_nothing(link_env):
    """Linking happens only after Toss verifies the userKey."""
    client = link_env
    aid = _seed_anonymous_analysis(ANON_A)
    r = _login(client, anon_subject=ANON_A, code="bad-code-xxxx")
    assert r.status_code in (401, 503)
    assert _owner_of(aid) == ("TOSS_ANONYMOUS", ANON_A)
    with session_scope() as session:
        assert (
            session.scalar(
                select(User).where(
                    User.external_provider == "TOSS",
                    User.external_subject == VERIFIED_USER_KEY,
                )
            )
            is None
        )


def test_other_anonymous_hash_cannot_claim_another_analysis(link_env):
    """Logging in while asserting anon-B must not adopt anon-A's analysis."""
    client = link_env
    aid_a = _seed_anonymous_analysis(ANON_A)
    aid_b = _seed_anonymous_analysis(ANON_B)

    r = _login(client, anon_subject=ANON_B)
    assert r.status_code == 200
    token = r.json()["session_token"]

    assert _owner_of(aid_b) == ("TOSS", VERIFIED_USER_KEY)
    assert _owner_of(aid_a) == ("TOSS_ANONYMOUS", ANON_A)

    stolen = client.post(
        "/v1/payments/iap/intents",
        json={"product_id": "song_detail", "analysis_id": aid_a},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert stolen.status_code == 404
    assert stolen.json()["detail"]["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_unknown_analysis_id_cannot_create_intent(link_env):
    client = link_env
    _seed_anonymous_analysis(ANON_A)
    r = _login(client, anon_subject=ANON_A)
    token = r.json()["session_token"]
    bogus = client.post(
        "/v1/payments/iap/intents",
        json={"product_id": "song_detail", "analysis_id": uuid.uuid4().hex},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert bogus.status_code == 404
    assert bogus.json()["detail"]["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_repeat_login_is_idempotent(link_env):
    client = link_env
    aid = _seed_anonymous_analysis(ANON_A)
    first = _login(client, anon_subject=ANON_A)
    assert first.status_code == 200
    assert first.json()["linked_analyses"] == 1

    second = _login(client, anon_subject=ANON_A)
    assert second.status_code == 200
    # Nothing left to move on the second pass.
    assert second.json()["linked_analyses"] == 0
    assert _owner_of(aid) == ("TOSS", VERIFIED_USER_KEY)

    with session_scope() as session:
        verified = list(
            session.scalars(
                select(User).where(
                    User.external_provider == "TOSS",
                    User.external_subject == VERIFIED_USER_KEY,
                )
            )
        )
        assert len(verified) == 1
        owned = list(
            session.scalars(select(Analysis).where(Analysis.user_id == verified[0].id))
        )
        assert [row.id for row in owned] == [aid]


def test_existing_toss_user_analyses_are_preserved(link_env):
    """Adoption adds to the verified user; it never replaces what they already own."""
    client = link_env
    prior = uuid.uuid4().hex
    with session_scope() as session:
        verified = get_or_create_user(session, provider="TOSS", subject=VERIFIED_USER_KEY)
        session.add(Analysis(id=prior, user_id=verified.id, status="completed"))
    aid = _seed_anonymous_analysis(ANON_A)

    r = _login(client, anon_subject=ANON_A)
    assert r.status_code == 200

    with session_scope() as session:
        verified = session.scalar(
            select(User).where(
                User.external_provider == "TOSS", User.external_subject == VERIFIED_USER_KEY
            )
        )
        owned = {
            row.id for row in session.scalars(select(Analysis).where(Analysis.user_id == verified.id))
        }
    assert owned == {prior, aid}


def test_history_still_shows_anonymous_era_analysis_after_login(link_env):
    client = link_env
    aid = _seed_anonymous_analysis(ANON_A)
    r = _login(client, anon_subject=ANON_A)
    token = r.json()["session_token"]

    history = client.get("/v1/history", headers={"Authorization": f"Bearer {token}"})
    assert history.status_code == 200, history.text
    ids = {item.get("analysis_id") or item.get("id") for item in history.json()["items"]}
    assert aid in ids


def test_entitlement_is_not_duplicated_on_link(link_env):
    """The verified user's own entitlement wins; no second ACTIVE row is created."""
    client = link_env
    aid = _seed_anonymous_analysis(ANON_A)
    with session_scope() as session:
        anon = session.scalar(
            select(User).where(
                User.external_provider == "TOSS_ANONYMOUS", User.external_subject == ANON_A
            )
        )
        verified = get_or_create_user(session, provider="TOSS", subject=VERIFIED_USER_KEY)
        for owner in (anon, verified):
            session.add(
                Entitlement(
                    user_id=owner.id,
                    resource_type="ANALYSIS",
                    resource_id=aid,
                    entitlement_type="SONG_DETAIL",
                    status="ACTIVE",
                )
            )

    assert _login(client, anon_subject=ANON_A).status_code == 200

    with session_scope() as session:
        verified = session.scalar(
            select(User).where(
                User.external_provider == "TOSS", User.external_subject == VERIFIED_USER_KEY
            )
        )
        rows = list(
            session.scalars(
                select(Entitlement).where(
                    Entitlement.user_id == verified.id,
                    Entitlement.resource_id == aid,
                    Entitlement.entitlement_type == "SONG_DETAIL",
                )
            )
        )
    assert len(rows) == 1


def test_rewarded_daily_cap_is_not_reset_by_linking(link_env):
    """Merging slots must never hand back free unlocks beyond the daily cap."""
    from backend.app.db.models import RewardedAdDailySlot

    client = link_env
    _seed_anonymous_analysis(ANON_A)
    day = "2026-08-24"
    with session_scope() as session:
        get_or_create_user(session, provider="TOSS", subject=VERIFIED_USER_KEY)
        for pkey, slot in (
            (f"TOSS_ANONYMOUS:{ANON_A}", 1),
            (f"TOSS:{VERIFIED_USER_KEY}", 1),
        ):
            session.add(RewardedAdDailySlot(principal_key=pkey, seoul_day=day, slot_index=slot))

    assert _login(client, anon_subject=ANON_A).status_code == 200

    with session_scope() as session:
        used = sorted(
            row.slot_index
            for row in session.scalars(
                select(RewardedAdDailySlot).where(
                    RewardedAdDailySlot.principal_key == f"TOSS:{VERIFIED_USER_KEY}",
                    RewardedAdDailySlot.seoul_day == day,
                )
            )
        )
    # Both principals' consumption is now counted against the verified principal.
    assert used == [1, 2]
