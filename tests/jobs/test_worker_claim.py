"""Atomic worker claim/lease tests. No live AWS."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.db.analysis_repo import claim_analysis_job, extend_worker_lease, get_analysis_snapshot
from backend.app.db.models import Analysis, Base
from backend.app.db.session import reset_engine
from backend.app.db.users import get_or_create_user
from backend.app.db.session import session_scope


AID = "c7045e107d714b64880a468748b1f8b7"
KEY = f"analyses/{AID}/input.m4a"


@pytest.fixture()
def claim_db(tmp_path, monkeypatch):
    db = tmp_path / "claim.sqlite"
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db}")
    monkeypatch.setenv("VAGENT_ENV", "development")
    monkeypatch.setenv("RUNTIME_DIR", str(runtime))
    reset_engine()
    from backend.app.db.session import get_engine

    engine = get_engine()
    assert engine is not None
    Base.metadata.create_all(engine)
    with session_scope() as session:
        user = get_or_create_user(session, provider="DEV", subject="claim-owner")
        owner_id = user.id
        session.add(
            Analysis(
                id=AID,
                user_id=user.id,
                status="queued",
                stage="queued",
                progress=0,
                analysis_mode="FUNCTIONAL",
                input_mode="MIXED",
                audio_storage_key=KEY,
                worker_attempt_count=0,
            )
        )
    yield owner_id
    reset_engine()


def test_atomic_claim_success(claim_db):
    claimed = claim_analysis_job(AID, claim_token="token-a", lease_seconds=600)
    assert claimed is not None
    assert claimed["status"] == "analyzing"
    assert claimed["worker_claim_token"] == "token-a"
    assert claimed["worker_attempt_count"] == 1
    assert claimed["worker_lease_expires_at"] is not None


def test_active_lease_duplicate_claim_fails(claim_db):
    first = claim_analysis_job(AID, claim_token="token-a", lease_seconds=600)
    assert first is not None
    second = claim_analysis_job(AID, claim_token="token-b", lease_seconds=600)
    assert second is None
    snap = get_analysis_snapshot(AID)
    assert snap["worker_claim_token"] == "token-a"
    assert snap["worker_attempt_count"] == 1


def test_expired_lease_reclaim(claim_db):
    first = claim_analysis_job(AID, claim_token="token-a", lease_seconds=600)
    assert first is not None
    past = datetime.now(timezone.utc) - timedelta(seconds=30)
    with session_scope() as session:
        row = session.get(Analysis, AID)
        row.worker_lease_expires_at = past
    reclaimed = claim_analysis_job(AID, claim_token="token-b", lease_seconds=600)
    assert reclaimed is not None
    assert reclaimed["worker_claim_token"] == "token-b"
    assert reclaimed["worker_attempt_count"] == 2


def test_completed_is_never_claimed(claim_db):
    with session_scope() as session:
        row = session.get(Analysis, AID)
        row.status = "completed"
    assert claim_analysis_job(AID, claim_token="token-a", lease_seconds=600) is None


def test_duplicate_messages_only_one_claim(claim_db):
    winners: list[str] = []

    def attempt(token: str) -> None:
        got = claim_analysis_job(AID, claim_token=token, lease_seconds=600)
        if got is not None:
            winners.append(token)

    t1 = threading.Thread(target=attempt, args=("t1",))
    t2 = threading.Thread(target=attempt, args=("t2",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    assert len(winners) == 1
    snap = get_analysis_snapshot(AID)
    assert snap["worker_claim_token"] in ("t1", "t2")
    assert snap["worker_attempt_count"] == 1


def test_extend_worker_lease(claim_db):
    claimed = claim_analysis_job(AID, claim_token="token-a", lease_seconds=30)
    first_lease = claimed["worker_lease_expires_at"]
    assert extend_worker_lease(AID, claim_token="token-a", lease_seconds=600) is True
    snap = get_analysis_snapshot(AID)
    assert snap["worker_lease_expires_at"] is not None
    assert snap["worker_lease_expires_at"] != first_lease
    assert extend_worker_lease(AID, claim_token="wrong", lease_seconds=600) is False


def test_claim_does_not_change_owner(claim_db):
    owner_id = claim_db
    claim_analysis_job(AID, claim_token="token-a", lease_seconds=600)
    with session_scope() as session:
        row = session.get(Analysis, AID)
        assert row.user_id == owner_id
