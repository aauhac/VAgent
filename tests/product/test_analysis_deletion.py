"""Analysis delete: server cascade, owner gate, payment preservation, path safety."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.db.models import Analysis, Base, DiagnosticSession, PurchaseOrder
from backend.app.db.purchases import grant_from_purchase
from backend.app.db.session import reset_engine, session_scope
from backend.app.db.users import get_or_create_user
from backend.app.jobs.runner import validate_analysis_id
from backend.app.payments.session_tokens import issue_session
from backend.app.payments.toss_clients import set_iap_client, set_login_client
from backend.app.services.deletion import delete_analysis_content


def _auth(user_key: str) -> dict[str, str]:
    token, _ = issue_session(toss_user_key=user_key)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def delete_env(tmp_path, monkeypatch):
    db = tmp_path / "del.sqlite"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db}")
    monkeypatch.setenv("VAGENT_ENV", "development")
    monkeypatch.setenv("VAGENT_SESSION_SECRET", "test-session-secret-not-for-prod")
    monkeypatch.setenv("RUNTIME_DIR", str(tmp_path / "runtime"))
    (tmp_path / "runtime").mkdir()
    reset_engine()
    from backend.app.config import get_runtime_dir

    get_runtime_dir.cache_clear()
    from backend.app.db.session import get_engine
    from backend.app.main import app
    from backend.app.api import routes as routes_mod
    from backend.app.diagnostic import DiagnosticSessionService
    from backend.app.jobs.runner import JobRunner
    from backend.app.services.analysis_service import AnalysisService

    engine = get_engine()
    assert engine is not None
    Base.metadata.create_all(engine)
    svc = AnalysisService()
    svc.runtime_dir = tmp_path / "runtime"
    svc.runner = JobRunner(svc.runtime_dir, max_workers=1)
    routes_mod.service = svc
    routes_mod.diag = DiagnosticSessionService(svc.runtime_dir)
    client = TestClient(app, raise_server_exceptions=True)
    yield client, svc
    set_iap_client(None)
    set_login_client(None)
    reset_engine()
    get_runtime_dir.cache_clear()


def _seed_analysis(runtime: Path, *, aid: str, user_key: str, with_purchase: bool = False):
    job = runtime / aid
    job.mkdir(parents=True)
    (job / "upload.wav").write_bytes(b"RIFF")
    (job / "analysis.wav").write_bytes(b"RIFF")
    (job / "preview.wav").write_bytes(b"RIFF")
    (job / "analysis.json").write_text("{}", encoding="utf-8")
    (job / "analysis_meta.json").write_text(
        json.dumps({"user_id": user_key}),
        encoding="utf-8",
    )
    with session_scope() as session:
        user = get_or_create_user(session, provider="TOSS", subject=user_key)
        session.add(Analysis(id=aid, user_id=user.id, status="completed", public_summary={"vocal_type": "x"}))
        session.flush()
        if with_purchase:
            grant_from_purchase(
                session,
                user_id=user.id,
                toss_order_id=f"order-{aid[:8]}",
                product_id="song_detail",
                resource_type="ANALYSIS",
                resource_id=aid,
                entitlement_type="SONG_DETAIL",
                sku="sku.song.detail.test",
            )
        return user.id


def _seed_diagnostic(runtime: Path, *, sid: str, user_key: str, source: str | None):
    d = runtime / "diagnostic_sessions" / sid
    d.mkdir(parents=True)
    (d / "session.json").write_text(
        json.dumps({"session_id": sid, "user_id": user_key, "source_analysis_id": source}),
        encoding="utf-8",
    )
    (d / "premium_report.json").write_text("{}", encoding="utf-8")
    task = d / "tasks" / "comfortable_glide" / "attempt_1"
    task.mkdir(parents=True)
    (task / "analysis.wav").write_bytes(b"RIFF")
    with session_scope() as session:
        user = get_or_create_user(session, provider="TOSS", subject=user_key)
        session.add(
            DiagnosticSession(
                id=sid,
                user_id=user.id,
                source_analysis_id=source,
                status="COMPLETED",
            )
        )


def test_delete_requires_verified_session(delete_env):
    client, svc = delete_env
    aid = "a" * 32
    _seed_analysis(svc.runtime_dir, aid=aid, user_key="user-a")
    r = client.delete(f"/v1/analyses/{aid}", headers={"X-User-Id": "user-a", "X-VAgent-User-Key": "user-a"})
    assert r.status_code == 401
    assert (svc.runtime_dir / aid / "upload.wav").exists()


def test_owner_delete_removes_audio_and_linked_diagnostic(delete_env):
    client, svc = delete_env
    aid = "b" * 32
    linked = "c" * 32
    orphan = "d" * 32
    other = "e" * 32
    _seed_analysis(svc.runtime_dir, aid=aid, user_key="user-a", with_purchase=True)
    _seed_analysis(svc.runtime_dir, aid=other, user_key="user-a")
    _seed_diagnostic(svc.runtime_dir, sid=linked, user_key="user-a", source=aid)
    _seed_diagnostic(svc.runtime_dir, sid=orphan, user_key="user-a", source=None)

    r = client.delete(f"/v1/analyses/{aid}", headers=_auth("user-a"))
    assert r.status_code == 200, r.text
    assert not (svc.runtime_dir / aid).exists()
    assert not (svc.runtime_dir / "diagnostic_sessions" / linked).exists()
    assert (svc.runtime_dir / "diagnostic_sessions" / orphan).exists()
    assert (svc.runtime_dir / other / "upload.wav").exists()

    with session_scope() as session:
        row = session.get(Analysis, aid)
        assert row is not None
        assert row.deleted_at is not None
        assert row.public_summary is None
        assert session.get(DiagnosticSession, linked) is None
        assert session.get(DiagnosticSession, orphan) is not None
        orders = list(session.scalars(select(PurchaseOrder)))
        assert len(orders) == 1
        assert orders[0].toss_order_id == f"order-{aid[:8]}"
        assert orders[0].refunded_at is None


def test_other_user_cannot_delete(delete_env):
    client, svc = delete_env
    aid = "f" * 32
    _seed_analysis(svc.runtime_dir, aid=aid, user_key="user-a")
    r = client.delete(f"/v1/analyses/{aid}", headers=_auth("user-b"))
    assert r.status_code == 404
    assert (svc.runtime_dir / aid / "upload.wav").exists()


def test_malformed_id_cannot_escape_runtime(tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("keep", encoding="utf-8")
    assert validate_analysis_id("../secret") is False
    assert validate_analysis_id("..\\..\\windows") is False
    result = delete_analysis_content(runtime, "../etc")
    assert result.ok is False
    assert outside.read_text(encoding="utf-8") == "keep"
    result2 = delete_analysis_content(runtime, "not-hex")
    assert result2.ok is False
    assert outside.read_text(encoding="utf-8") == "keep"


def test_same_name_does_not_share_identity(delete_env):
    client, svc = delete_env
    aid = "1" * 32
    _seed_analysis(svc.runtime_dir, aid=aid, user_key="key-a", with_purchase=True)
    assert client.get(f"/v1/analyses/{aid}", headers=_auth("key-b")).status_code == 404
    hist_b = client.get("/v1/history", headers=_auth("key-b")).json()
    items = hist_b.get("items") if isinstance(hist_b, dict) else []
    assert isinstance(items, list)
    assert not any(isinstance(it, dict) and it.get("analysis_id") == aid for it in items)
    assert client.delete(f"/v1/analyses/{aid}", headers=_auth("key-b")).status_code == 404
