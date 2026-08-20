# -*- coding: utf-8 -*-
"""Rewarded-ad SONG_DETAIL unlock: session/claim, daily limit, no diagnostic grants."""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from backend.app.db.models import Analysis, Base, Entitlement, RewardedAdClaim, RewardedAdDailySlot
from backend.app.db.session import reset_engine, session_scope
from backend.app.db.users import get_or_create_user
from backend.app.identity import ResolvedIdentity
from backend.app.rewards.rewarded_detail import (
    DAILY_LIMIT,
    claim_rewarded_song_detail,
    create_rewarded_session,
    rewarded_ad_status,
    seoul_day,
)


SEOUL = ZoneInfo("Asia/Seoul")
ROOT = Path(__file__).resolve().parents[2]
MINI = ROOT / "miniapp" / "src"


def _read(rel: str) -> str:
    return (MINI / rel).read_text(encoding="utf-8")


@pytest.fixture()
def rewarded_env(tmp_path, monkeypatch):
    db = tmp_path / "rewarded.sqlite"
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db}")
    monkeypatch.setenv("VAGENT_ENV", "development")
    monkeypatch.setenv("VAGENT_SESSION_SECRET", "test-session-secret-not-for-prod")
    monkeypatch.setenv("RUNTIME_DIR", str(runtime))
    monkeypatch.setenv("ALLOW_MOCK_PREMIUM", "true")
    reset_engine()
    from backend.app.config import get_runtime_dir

    get_runtime_dir.cache_clear()
    from backend.app.db.session import get_engine

    engine = get_engine()
    assert engine is not None
    Base.metadata.create_all(engine)
    yield {"runtime": runtime, "db": db}
    reset_engine()
    get_runtime_dir.cache_clear()


def _identity(subject: str = "anon-hash-1", provider: str = "TOSS_ANONYMOUS") -> ResolvedIdentity:
    return ResolvedIdentity(
        provider=provider,
        subject=subject,
        trust_mode="CLIENT_ASSERTED",
        authenticated=provider == "TOSS",
        toss_user_key=subject if provider == "TOSS" else None,
    )


def _seed_analysis(analysis_id: str, subject: str, provider: str = "TOSS_ANONYMOUS") -> None:
    with session_scope() as session:
        user = get_or_create_user(session, provider=provider, subject=subject)
        session.add(
            Analysis(
                id=analysis_id,
                user_id=user.id,
                status="completed",
                stage="done",
                progress=100,
            )
        )


def test_frontend_reward_only_on_user_earned_reward():
    ad = _read("lib/tossRewardedAd.ts")
    assert "loadFullScreenAd" in ad
    assert "showFullScreenAd" in ad
    assert "userEarnedReward" in ad
    assert "ait-ad-test-rewarded-id" in ad
    assert "VITE_TOSS_REWARDED_DETAIL_AD_GROUP_ID" in ad
    assert "dismissed_without_reward" in ad
    assert "reward_earned" in ad
    assert "₩990" not in ad
    page = _read("pages/Result.tsx")
    assert "광고 보고 무료로 열기" in page
    assert "useRewardedDetailUnlock" in page
    assert "watchAndUnlock" in page
    assert "₩990" not in page
    hook = _read("lib/useRewardedDetailUnlock.ts")
    assert "createRewardedAdSession" in hook
    assert "claimRewardedSongDetail" in hook


def test_seoul_day_boundary():
    # 2026-08-20 23:30 Seoul == 14:30 UTC
    utc = datetime(2026, 8, 20, 14, 30, tzinfo=timezone.utc)
    assert seoul_day(utc) == "2026-08-20"
    # 2026-08-20 00:30 Seoul == 2026-08-19 15:30 UTC
    before = datetime(2026, 8, 19, 15, 30, tzinfo=timezone.utc)
    assert seoul_day(before) == "2026-08-20"
    # Just after midnight Seoul
    after = datetime(2026, 8, 20, 15, 0, tzinfo=timezone.utc)
    assert seoul_day(after) == "2026-08-21"


def test_reward_claim_grants_song_detail_only(rewarded_env):
    from sqlalchemy import select

    aid = uuid.uuid4().hex[:16]
    ident = _identity()
    _seed_analysis(aid, ident.subject)
    status0 = rewarded_ad_status(aid, ident, already_unlocked=False)
    assert status0["remaining_today"] == 3
    assert status0["can_use_rewarded_ad"] is True

    session = create_rewarded_session(aid, ident, already_unlocked=False)
    token = session["session_token"]
    assert token

    claimed = claim_rewarded_song_detail(aid, ident, session_token=token)
    assert claimed["unlocked"] is True
    assert claimed["remaining_today"] == 2
    assert claimed["entitlement_type"] == "SONG_DETAIL"

    with session_scope() as db:
        rows = list(db.scalars(select(Entitlement)).all())
        assert len(rows) == 1
        assert rows[0].entitlement_type == "SONG_DETAIL"
        assert rows[0].product_id == "song_detail"
        assert rows[0].resource_id == aid
        assert all(r.entitlement_type != "DIAGNOSTIC" for r in rows)


def test_dismiss_path_does_not_auto_grant_without_claim(rewarded_env):
    """Session alone must not grant; claim required (simulates dismissed without reward)."""
    aid = uuid.uuid4().hex[:16]
    ident = _identity("anon-2")
    _seed_analysis(aid, ident.subject)
    create_rewarded_session(aid, ident, already_unlocked=False)
    from sqlalchemy import select

    with session_scope() as db:
        assert list(db.scalars(select(Entitlement)).all()) == []
        pendings = list(
            db.scalars(select(RewardedAdClaim).where(RewardedAdClaim.status == "pending")).all()
        )
        assert len(pendings) == 1


def test_duplicate_claim_idempotent(rewarded_env):
    aid = uuid.uuid4().hex[:16]
    ident = _identity("anon-3")
    _seed_analysis(aid, ident.subject)
    token = create_rewarded_session(aid, ident, already_unlocked=False)["session_token"]
    first = claim_rewarded_song_detail(aid, ident, session_token=token)
    second = claim_rewarded_song_detail(aid, ident, session_token=token)
    assert first["unlocked"] and second["unlocked"]
    assert second.get("duplicate") is True
    assert second["remaining_today"] == first["remaining_today"] == 2
    from sqlalchemy import select

    with session_scope() as db:
        assert len(list(db.scalars(select(Entitlement)).all())) == 1


def test_same_analysis_second_session_blocked(rewarded_env):
    from backend.app.rewards.rewarded_detail import RewardedAdError

    aid = uuid.uuid4().hex[:16]
    ident = _identity("anon-4")
    _seed_analysis(aid, ident.subject)
    token = create_rewarded_session(aid, ident, already_unlocked=False)["session_token"]
    claim_rewarded_song_detail(aid, ident, session_token=token)
    with pytest.raises(RewardedAdError) as exc:
        create_rewarded_session(aid, ident, already_unlocked=True)
    assert exc.value.code == "ALREADY_UNLOCKED"


def test_daily_limit_three_then_reject(rewarded_env, monkeypatch):
    from backend.app.rewards import rewarded_detail as rd
    from backend.app.rewards.rewarded_detail import RewardedAdError

    fixed = datetime(2026, 8, 20, 5, 0, tzinfo=timezone.utc)  # Seoul 14:00
    monkeypatch.setattr(rd, "seoul_day", lambda now=None: "2026-08-20")
    ident = _identity("anon-limit")
    for i in range(3):
        aid = f"analysis{i:02d}{uuid.uuid4().hex[:8]}"
        _seed_analysis(aid, ident.subject)
        token = create_rewarded_session(aid, ident, already_unlocked=False)["session_token"]
        claimed = claim_rewarded_song_detail(aid, ident, session_token=token)
        assert claimed["used_today"] == i + 1
        assert claimed["remaining_today"] == 3 - (i + 1)

    aid4 = f"analysis3x{uuid.uuid4().hex[:8]}"
    _seed_analysis(aid4, ident.subject)
    with pytest.raises(RewardedAdError) as exc:
        create_rewarded_session(aid4, ident, already_unlocked=False)
    assert exc.value.code == "DAILY_LIMIT_REACHED"

    status = rewarded_ad_status(aid4, ident, already_unlocked=False)
    assert status["remaining_today"] == 0
    assert status["can_use_rewarded_ad"] is False


def test_next_seoul_day_resets(rewarded_env, monkeypatch):
    from backend.app.rewards import rewarded_detail as rd

    monkeypatch.setattr(rd, "seoul_day", lambda now=None: "2026-08-20")
    ident = _identity("anon-next")
    for i in range(3):
        aid = f"dayA{i}{uuid.uuid4().hex[:8]}"
        _seed_analysis(aid, ident.subject)
        token = create_rewarded_session(aid, ident, already_unlocked=False)["session_token"]
        claim_rewarded_song_detail(aid, ident, session_token=token)

    monkeypatch.setattr(rd, "seoul_day", lambda now=None: "2026-08-21")
    aid = f"dayB{uuid.uuid4().hex[:8]}"
    _seed_analysis(aid, ident.subject)
    status = rewarded_ad_status(aid, ident, already_unlocked=False)
    assert status["remaining_today"] == 3
    token = create_rewarded_session(aid, ident, already_unlocked=False)["session_token"]
    claimed = claim_rewarded_song_detail(aid, ident, session_token=token)
    assert claimed["used_today"] == 1
    assert claimed["remaining_today"] == 2


def test_iap_already_unlocked_blocks_ad(rewarded_env):
    from backend.app.rewards.rewarded_detail import RewardedAdError

    aid = uuid.uuid4().hex[:16]
    ident = _identity("anon-iap")
    _seed_analysis(aid, ident.subject)
    from backend.app.entitlements import get_entitlement_provider

    ents = get_entitlement_provider(rewarded_env["runtime"])
    ents.grant_song_detail(ident.subject, aid, "iap_ent_1", product_id="song_detail")
    with pytest.raises(RewardedAdError) as exc:
        create_rewarded_session(aid, ident, already_unlocked=True)
    assert exc.value.code == "ALREADY_UNLOCKED"


def test_api_routes_session_claim(rewarded_env, monkeypatch):
    from backend.app.api import routes as api_routes
    from backend.app.main import app
    from backend.app.services.analysis_service import AnalysisService

    aid = uuid.uuid4().hex[:16]
    subject = "dev-user"
    _seed_analysis(aid, subject, provider="DEV")
    runtime = rewarded_env["runtime"]
    job_dir = runtime / aid
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "job_status.json").write_text(
        '{"analysis_id":"%s","status":"completed","stage":"done","progress":100}' % aid,
        encoding="utf-8",
    )

    # Rebind route service to pick up RUNTIME_DIR from fixture
    svc = AnalysisService()
    monkeypatch.setattr(api_routes, "service", svc)

    client = TestClient(app)
    headers = {"X-VAgent-User-Key": subject}

    status = client.get(f"/v1/analyses/{aid}/rewarded-ad", headers=headers)
    assert status.status_code == 200, status.text
    assert status.json()["remaining_today"] == 3

    session = client.post(f"/v1/analyses/{aid}/rewarded-ad/session", headers=headers)
    assert session.status_code == 200, session.text
    token = session.json()["session_token"]

    access = client.get(f"/v1/analyses/{aid}/access", headers=headers)
    assert access.status_code == 200
    assert access.json()["song_detail_unlocked"] is False
    assert "rewarded_ad" in access.json()

    claim = client.post(
        f"/v1/analyses/{aid}/rewarded-ad/claim",
        headers=headers,
        json={"session_token": token},
    )
    assert claim.status_code == 200, claim.text
    assert claim.json()["unlocked"] is True
    assert claim.json()["remaining_today"] == 2

    access2 = client.get(f"/v1/analyses/{aid}/access", headers=headers)
    assert access2.json()["song_detail_unlocked"] is True


def test_claim_without_token_rejected(rewarded_env):
    from backend.app.rewards.rewarded_detail import RewardedAdError

    aid = uuid.uuid4().hex[:16]
    ident = _identity("anon-notoken")
    _seed_analysis(aid, ident.subject)
    with pytest.raises(RewardedAdError) as exc:
        claim_rewarded_song_detail(aid, ident, session_token="")
    assert exc.value.code == "SESSION_TOKEN_REQUIRED"


def test_watched_true_forgery_impossible_without_session(rewarded_env):
    from backend.app.rewards.rewarded_detail import RewardedAdError

    aid = uuid.uuid4().hex[:16]
    ident = _identity("anon-forge")
    _seed_analysis(aid, ident.subject)
    with pytest.raises(RewardedAdError) as exc:
        claim_rewarded_song_detail(aid, ident, session_token="forged-token-value")
    assert exc.value.code == "SESSION_NOT_FOUND"


def test_concurrent_claims_respect_daily_limit(rewarded_env, monkeypatch):
    from backend.app.rewards import rewarded_detail as rd
    from backend.app.rewards.rewarded_detail import RewardedAdError

    monkeypatch.setattr(rd, "seoul_day", lambda now=None: "2026-08-20")
    ident = _identity("anon-race")
    # Pre-create sessions for 5 analyses
    tokens = []
    for i in range(5):
        aid = f"race{i}{uuid.uuid4().hex[:8]}"
        _seed_analysis(aid, ident.subject)
        token = create_rewarded_session(aid, ident, already_unlocked=False)["session_token"]
        tokens.append((aid, token))

    results = []

    def _claim(pair):
        aid, token = pair
        try:
            return claim_rewarded_song_detail(aid, ident, session_token=token)
        except RewardedAdError as exc:
            return {"error": exc.code}

    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(_claim, tokens))

    successes = [r for r in results if r.get("unlocked")]
    rejected = [r for r in results if r.get("error") == "DAILY_LIMIT_REACHED"]
    # SQLite may serialize; at most 3 unlocks
    assert len(successes) <= DAILY_LIMIT
    assert len(successes) + len(rejected) + len(
        [r for r in results if r.get("error") and r["error"] != "DAILY_LIMIT_REACHED"]
    ) == 5
    from sqlalchemy import select

    with session_scope() as db:
        from sqlalchemy import func, select

        used = int(
            db.scalar(
                select(func.count())
                .select_from(RewardedAdDailySlot)
                .where(
                    RewardedAdDailySlot.principal_key == f"TOSS_ANONYMOUS:{ident.subject}",
                    RewardedAdDailySlot.seoul_day == "2026-08-20",
                )
            )
            or 0
        )
        assert used <= DAILY_LIMIT
        assert used == len(successes)


def test_authenticated_owner_path(rewarded_env):
    aid = uuid.uuid4().hex[:16]
    ident = _identity("toss-user-99", provider="TOSS")
    _seed_analysis(aid, ident.subject, provider="TOSS")
    token = create_rewarded_session(aid, ident, already_unlocked=False)["session_token"]
    claimed = claim_rewarded_song_detail(aid, ident, session_token=token)
    assert claimed["unlocked"] is True
