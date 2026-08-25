"""History association: source_analysis_id join, no unsafe heuristics, cross-user isolation."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.app.db.models import Analysis, Base, DiagnosticSession, Entitlement
from backend.app.db.session import reset_engine
from backend.app.db.users import get_or_create_user


def _aid() -> str:
    return uuid.uuid4().hex


@pytest.fixture()
def history_env(tmp_path, monkeypatch):
    db = tmp_path / "hist.sqlite"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db}")
    monkeypatch.setenv("VAGENT_ENV", "development")
    monkeypatch.setenv("RUNTIME_DIR", str(tmp_path / "runtime"))
    (tmp_path / "runtime").mkdir()
    reset_engine()
    from backend.app.config import get_runtime_dir

    get_runtime_dir.cache_clear()
    from backend.app.db.session import get_engine

    engine = get_engine()
    assert engine is not None
    Base.metadata.create_all(engine)
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
    reset_engine()
    get_runtime_dir.cache_clear()


def _seed_user(subject: str, provider: str = "DEV"):
    from backend.app.db.session import session_scope

    with session_scope() as session:
        user = get_or_create_user(session, provider=provider, subject=subject)
        return user.id


def _add_analysis(user_id, *, filename: str | None, vocal: str | None = None, detail: bool = False):
    from backend.app.db.session import session_scope

    aid = _aid()
    now = datetime.now(timezone.utc)
    with session_scope() as session:
        session.add(
            Analysis(
                id=aid,
                user_id=user_id,
                status="completed",
                original_filename=filename,
                public_summary={"vocal_type": {"display_name": vocal}} if vocal else {},
                created_at=now,
                updated_at=now,
            )
        )
        if detail:
            session.add(
                Entitlement(
                    user_id=user_id,
                    resource_type="ANALYSIS",
                    resource_id=aid,
                    entitlement_type="SONG_DETAIL",
                    status="ACTIVE",
                )
            )
    return aid


def _add_session(
    user_id,
    *,
    source: str | None,
    status: str = "COMPLETED",
    persisted: str | None = None,
    paid: bool = True,
):
    """Seed a diagnostic session.

    `paid` grants the ACTIVE DIAGNOSTIC entitlement that makes a session visible.
    History hides unpaid sessions, so association behaviour is only observable on paid
    ones; pass paid=False to exercise the hiding rule itself.
    """
    from backend.app.db.session import session_scope

    sid = _aid()
    now = datetime.now(timezone.utc)
    rationale = {}
    if persisted:
        rationale = {"_session_ext": {"persisted_source_analysis_id": persisted}}
    with session_scope() as session:
        session.add(
            DiagnosticSession(
                id=sid,
                user_id=user_id,
                source_analysis_id=source,
                status=status,
                plan_rationale=rationale or None,
                created_at=now,
                updated_at=now,
                completed_at=now if status == "COMPLETED" else None,
            )
        )
        if paid:
            session.add(
                Entitlement(
                    user_id=user_id,
                    resource_type="DIAGNOSTIC_SESSION",
                    resource_id=sid,
                    entitlement_type="DIAGNOSTIC",
                    status="ACTIVE",
                    granted_at=now,
                )
            )
    return sid


def test_free_only_analysis_is_primary_free(history_env):
    client = history_env
    user = _seed_user("hist-a")
    aid = _add_analysis(user, filename="free.wav", vocal="낮은 힘 사용")
    body = client.get("/v1/history", headers={"X-User-Id": "hist-a"}).json()
    row = next(i for i in body["items"] if i["analysis_id"] == aid)
    assert row["song_detail_unlocked"] is False
    assert row["filename"] == "free.wav"
    assert row["vocal_type"] == "낮은 힘 사용"
    assert row["diagnostic_sessions"] == []


def test_detail_entitlement_flags_song_detail(history_env):
    client = history_env
    user = _seed_user("hist-b")
    aid = _add_analysis(user, filename="t.wav", vocal="발성 성향 판단 보류", detail=True)
    body = client.get("/v1/history", headers={"X-User-Id": "hist-b"}).json()
    row = next(i for i in body["items"] if i["analysis_id"] == aid)
    assert row["song_detail_unlocked"] is True
    assert row["vocal_type"] != "발성 성향 판단 보류"
    assert "충분히 구분하기 어려웠어요" in (row["vocal_type"] or "")


def test_source_analysis_id_joins_into_history_card(history_env):
    client = history_env
    user = _seed_user("hist-c")
    aid = _add_analysis(user, filename="song.m4a", detail=True)
    sid = _add_session(user, source=aid)
    body = client.get("/v1/history", headers={"X-User-Id": "hist-c"}).json()
    row = next(i for i in body["items"] if i["analysis_id"] == aid)
    assert row["diagnostic_session_id"] == sid
    assert sid in [s["session_id"] for s in row["diagnostic_sessions"]]
    assert body["unlinked_diagnostics"] == []


def test_multiple_diagnostics_keep_all_and_pick_latest_completed(history_env):
    client = history_env
    user = _seed_user("hist-d")
    aid = _add_analysis(user, filename="multi.wav")
    old = _add_session(user, source=aid, status="COMPLETED")
    newest = _add_session(user, source=aid, status="COMPLETED")
    body = client.get("/v1/history", headers={"X-User-Id": "hist-d"}).json()
    row = next(i for i in body["items"] if i["analysis_id"] == aid)
    ids = [s["session_id"] for s in row["diagnostic_sessions"]]
    assert old in ids and newest in ids
    assert row["diagnostic_session_id"] == newest


def test_true_orphan_has_no_source(history_env):
    client = history_env
    user = _seed_user("hist-e")
    _add_analysis(user, filename="owned.wav")
    orphan = _add_session(user, source=None)
    body = client.get("/v1/history", headers={"X-User-Id": "hist-e"}).json()
    assert all(orphan not in [s["session_id"] for s in (i.get("diagnostic_sessions") or [])] for i in body["items"])
    assert any(s["session_id"] == orphan for s in body["unlinked_diagnostics"])


def test_legacy_filename_none_is_not_invented(history_env):
    client = history_env
    user = _seed_user("hist-f")
    aid = _add_analysis(user, filename=None, vocal=None)
    row = next(i for i in client.get("/v1/history", headers={"X-User-Id": "hist-f"}).json()["items"] if i["analysis_id"] == aid)
    assert row["filename"] in (None, "")
    assert row["vocal_type"] in (None, "")


def test_safe_backfill_from_persisted_source_id(history_env):
    client = history_env
    user = _seed_user("hist-g")
    aid = _add_analysis(user, filename="restored.wav")
    sid = _add_session(user, source=None, persisted=aid)
    body = client.get("/v1/history", headers={"X-User-Id": "hist-g"}).json()
    row = next(i for i in body["items"] if i["analysis_id"] == aid)
    assert sid == row["diagnostic_session_id"]
    assert not any(s["session_id"] == sid for s in body["unlinked_diagnostics"])


def test_other_user_diagnostic_never_appears(history_env):
    client = history_env
    a = _seed_user("hist-owner")
    b = _seed_user("hist-other")
    aid = _add_analysis(a, filename="a.wav")
    _add_session(b, source=aid)
    _add_session(b, source=None)
    body = client.get("/v1/history", headers={"X-User-Id": "hist-owner"}).json()
    row = next(i for i in body["items"] if i["analysis_id"] == aid)
    assert row["diagnostic_sessions"] == []
    assert body["unlinked_diagnostics"] == []
    other = client.get("/v1/history", headers={"X-User-Id": "hist-other"}).json()
    assert not any(i["analysis_id"] == aid for i in other["items"])


def test_does_not_link_by_filename_or_date(history_env):
    client = history_env
    user = _seed_user("hist-h")
    aid = _add_analysis(user, filename="same.wav")
    orphan = _add_session(user, source=None)
    body = client.get("/v1/history", headers={"X-User-Id": "hist-h"}).json()
    row = next(i for i in body["items"] if i["analysis_id"] == aid)
    assert row["diagnostic_sessions"] == []
    assert any(s["session_id"] == orphan for s in body["unlinked_diagnostics"])


def test_history_pagination(history_env):
    client = history_env
    user = _seed_user("hist-page")
    for i in range(5):
        _add_analysis(user, filename=f"{i}.wav")
    page = client.get("/v1/history?limit=2&offset=0", headers={"X-User-Id": "hist-page"}).json()
    assert len(page["items"]) == 2
    assert page["has_more"] is True
    page2 = client.get("/v1/history?limit=2&offset=2", headers={"X-User-Id": "hist-page"}).json()
    assert len(page2["items"]) == 2
    ids = {i["analysis_id"] for i in page["items"]} | {i["analysis_id"] for i in page2["items"]}
    assert len(ids) == 4
