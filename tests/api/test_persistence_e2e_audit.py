"""Production persistence E2E audit tests (Postgres when DATABASE_URL set; else SQLite)."""

from __future__ import annotations

import io
import os
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Force DB for this module before app imports that cache engines
_TEST_DB = os.environ.get("VAGENT_E2E_DATABASE_URL") or "sqlite+pysqlite:///:memory:"


@pytest.fixture()
def db_url(tmp_path, monkeypatch):
    url = os.environ.get("VAGENT_E2E_DATABASE_URL")
    if url:
        monkeypatch.setenv("DATABASE_URL", url)
    else:
        # file-based sqlite so multiple connections see same data
        path = tmp_path / "e2e.sqlite"
        monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{path}")
    monkeypatch.setenv("VAGENT_ENV", "development")
    # reset engine singleton
    import backend.app.db.session as sess

    sess._engine = None
    sess._SessionLocal = None
    from backend.app.config import get_runtime_dir

    get_runtime_dir.cache_clear()
    yield os.environ["DATABASE_URL"]
    sess._engine = None
    sess._SessionLocal = None
    get_runtime_dir.cache_clear()


@pytest.fixture()
def app_client(db_url, tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.setenv("RUNTIME_DIR", str(runtime))
    from backend.app.config import get_runtime_dir

    get_runtime_dir.cache_clear()

    from backend.app.db.models import Base
    from backend.app.db.session import get_engine

    engine = get_engine()
    assert engine is not None
    Base.metadata.create_all(engine)

    from backend.app.api import routes as routes_mod
    from backend.app.diagnostic import DiagnosticSessionService
    from backend.app.jobs.runner import JobRunner
    from backend.app.main import app
    from backend.app.services.analysis_service import AnalysisService

    svc = AnalysisService()
    svc.runner = JobRunner(svc.runtime_dir, max_workers=1)
    monkeypatch.setattr(routes_mod, "service", svc)
    monkeypatch.setattr(routes_mod, "diag", DiagnosticSessionService(svc.runtime_dir))
    client = TestClient(app, raise_server_exceptions=True)
    yield client, svc, runtime


def _wav(duration=0.4, freq=220.0, sr=16000) -> bytes:
    t = np.arange(int(sr * duration)) / sr
    y = (0.2 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    buf = io.BytesIO()
    sf.write(buf, y, sr, format="WAV")
    return buf.getvalue()


def _wait(client, aid, headers, timeout=90.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = client.get(f"/v1/analyses/{aid}", headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()
        if body["status"] in ("completed", "failed"):
            return body
        time.sleep(0.25)
    raise TimeoutError(aid)


def test_runtime_path_is_project_relative(tmp_path, monkeypatch):
    from backend.app.config import get_runtime_dir, project_root

    monkeypatch.setenv("RUNTIME_DIR", "runtime")
    get_runtime_dir.cache_clear()
    monkeypatch.chdir(tmp_path)
    assert get_runtime_dir() == (project_root() / "runtime").resolve()
    get_runtime_dir.cache_clear()


def test_production_requires_database_url(monkeypatch):
    monkeypatch.setenv("VAGENT_ENV", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from backend.app.config import is_production

    assert is_production()
    # startup hook logic
    from backend.app import main as main_mod

    monkeypatch.setattr(main_mod, "database_url", lambda: None)
    monkeypatch.setattr(main_mod, "runtime_writable", lambda: True)
    monkeypatch.setattr(main_mod, "is_production", lambda: True)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        main_mod._on_startup()


def test_analysis_survives_runner_restart(app_client):
    client, svc, runtime = app_client
    headers = {"X-User-Id": "e2e-user-001", "X-VAgent-User-Key": "e2e-user-001"}
    r = client.post(
        "/v1/analyses",
        files={"file": ("t.wav", _wav(), "audio/wav")},
        data={"analysis_mode": "FUNCTIONAL", "input_mode": "VOCAL_ONLY", "separate": "false"},
        headers=headers,
    )
    assert r.status_code == 200
    aid = r.json()["analysis_id"]
    body = _wait(client, aid, headers)
    assert body["status"] == "completed"

    # empty memory runner
    from backend.app.jobs.runner import JobRunner

    fresh = JobRunner(runtime, max_workers=1)
    assert not fresh._jobs
    got = fresh.get(aid)
    assert got and got["status"] == "completed"


def test_history_from_db_and_user_scoped(app_client):
    client, _, _ = app_client
    ha = {"X-User-Id": "e2e-user-A", "X-VAgent-User-Key": "e2e-user-A"}
    hb = {"X-User-Id": "e2e-user-B", "X-VAgent-User-Key": "e2e-user-B"}
    ra = client.post(
        "/v1/analyses",
        files={"file": ("a.wav", _wav(), "audio/wav")},
        data={"analysis_mode": "FUNCTIONAL", "input_mode": "VOCAL_ONLY"},
        headers=ha,
    )
    assert ra.status_code == 200
    aid = ra.json()["analysis_id"]
    _wait(client, aid, ha)

    hist_a = client.get("/v1/history", headers=ha).json()["items"]
    hist_b = client.get("/v1/history", headers=hb).json()["items"]
    assert any(i["analysis_id"] == aid for i in hist_a)
    assert not any(i["analysis_id"] == aid for i in hist_b)
    row = next(i for i in hist_a if i["analysis_id"] == aid)
    assert "song_detail_unlocked" in row
    assert "status" in row


def test_analysis_and_preview_ownership(app_client):
    client, _, _ = app_client
    ha = {"X-User-Id": "own-A"}
    hb = {"X-User-Id": "own-B"}
    aid = client.post(
        "/v1/analyses",
        files={"file": ("a.wav", _wav(), "audio/wav")},
        data={"analysis_mode": "FUNCTIONAL", "input_mode": "VOCAL_ONLY"},
        headers=ha,
    ).json()["analysis_id"]
    _wait(client, aid, ha)
    assert client.get(f"/v1/analyses/{aid}", headers=ha).status_code == 200
    assert client.get(f"/v1/analyses/{aid}", headers=hb).status_code == 404
    assert client.get(f"/v1/analyses/{aid}/access", headers=hb).status_code == 404
    assert client.get(f"/v1/analyses/{aid}/preview", headers=hb).status_code == 404
    assert client.delete(f"/v1/analyses/{aid}", headers=hb).status_code == 401


def test_diagnostic_session_ownership(app_client):
    client, _, _ = app_client
    ha = {"X-User-Id": "diag-A"}
    hb = {"X-User-Id": "diag-B"}
    sid = client.post("/v1/diagnostic-sessions", headers=ha).json()["session_id"]
    assert client.get(f"/v1/diagnostic-sessions/{sid}", headers=ha).status_code == 200
    assert client.get(f"/v1/diagnostic-sessions/{sid}", headers=hb).status_code == 404
    assert client.post(f"/v1/diagnostic-sessions/{sid}/mock-pay", headers=hb).status_code == 404


def test_entitlement_survives_restart_memory(app_client):
    client, svc, runtime = app_client
    h = {"X-User-Id": "ent-user"}
    aid = client.post(
        "/v1/analyses",
        files={"file": ("a.wav", _wav(), "audio/wav")},
        data={"analysis_mode": "FUNCTIONAL", "input_mode": "VOCAL_ONLY"},
        headers=h,
    ).json()["analysis_id"]
    _wait(client, aid, h)
    assert client.post(f"/v1/analyses/{aid}/mock-unlock-detail", headers=h).status_code == 200
    # simulate process restart: new entitlement provider via fresh service entitlements
    from backend.app.entitlements import get_entitlement_provider

    ents = get_entitlement_provider(runtime)
    assert ents.has_song_detail("ent-user", aid) is True
    access = client.get(f"/v1/analyses/{aid}/access", headers=h)
    assert access.status_code == 200
    assert access.json()["song_detail_unlocked"] is True


def test_duplicate_purchase_order_idempotent(db_url):
    from backend.app.db.models import Base, Entitlement, PurchaseOrder
    from backend.app.db.purchases import grant_from_purchase
    from backend.app.db.session import get_engine, session_scope
    from backend.app.db.users import get_or_create_user

    engine = get_engine()
    Base.metadata.create_all(engine)
    with session_scope() as session:
        user = get_or_create_user(session, provider="DEV", subject="purchase-user")
        uid = user.id
        aid = "a" * 32
        from backend.app.db.models import Analysis

        session.add(Analysis(id=aid, user_id=uid, status="completed"))
        session.flush()
        grant_from_purchase(
            session,
            user_id=uid,
            toss_order_id="order-dup-1",
            product_id="song_detail",
            resource_type="ANALYSIS",
            resource_id=aid,
            entitlement_type="SONG_DETAIL",
        )
        grant_from_purchase(
            session,
            user_id=uid,
            toss_order_id="order-dup-1",
            product_id="song_detail",
            resource_type="ANALYSIS",
            resource_id=aid,
            entitlement_type="SONG_DETAIL",
        )
        assert len(session.scalars(select(PurchaseOrder).where(PurchaseOrder.toss_order_id == "order-dup-1")).all()) == 1
        assert len(session.scalars(select(Entitlement).where(Entitlement.user_id == uid)).all()) == 1


def test_interrupted_job_recovery(app_client):
    client, _, runtime = app_client
    h = {"X-User-Id": "int-user"}
    aid = "b" * 32
    d = runtime / aid
    d.mkdir()
    (d / "job_status.json").write_text(
        '{"analysis_id":"%s","status":"analyzing","progress":20}' % aid,
        encoding="utf-8",
    )
    from backend.app.services.history_service import write_analysis_meta

    write_analysis_meta(aid, user_id="int-user", runtime_dir=runtime)
    # Also insert DB row
    from backend.app.db.models import Analysis
    from backend.app.db.session import session_scope
    from backend.app.db.users import get_or_create_user

    with session_scope() as session:
        user = get_or_create_user(session, provider="DEV", subject="int-user")
        session.add(Analysis(id=aid, user_id=user.id, status="analyzing", progress=20))

    from backend.app.jobs.runner import JobRunner

    got = JobRunner(runtime).get(aid)
    assert got["status"] == "failed"
    assert got.get("error_code") == "INTERRUPTED_RESTART" or got.get("error") == "INTERRUPTED_RESTART"


def test_vocal_only_and_mixed_modes(app_client):
    client, _, _ = app_client
    h = {"X-User-Id": "mode-user"}
    r1 = client.post(
        "/v1/analyses",
        files={"file": ("v.wav", _wav(), "audio/wav")},
        data={"analysis_mode": "FUNCTIONAL", "input_mode": "VOCAL_ONLY", "separate": "false"},
        headers=h,
    )
    r2 = client.post(
        "/v1/analyses",
        files={"file": ("m.wav", _wav(), "audio/wav")},
        data={"analysis_mode": "FUNCTIONAL", "input_mode": "MIXED", "separate": "true"},
        headers=h,
    )
    assert r1.status_code == 200 and r1.json()["status"] == "queued"
    assert r2.status_code == 200 and r2.json()["status"] == "queued"
    from backend.app.db.models import Analysis
    from backend.app.db.session import session_scope

    with session_scope() as session:
        a1 = session.get(Analysis, r1.json()["analysis_id"])
        a2 = session.get(Analysis, r2.json()["analysis_id"])
        assert a1.input_mode == "VOCAL_ONLY" and a1.separate is False
        assert a2.input_mode == "MIXED" and a2.separate is True
