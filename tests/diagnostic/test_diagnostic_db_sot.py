"""Diagnostic PostgreSQL SoT tests."""

from __future__ import annotations

import io

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from backend.app.api import routes as routes_mod
from backend.app.diagnostic.service import DiagnosticSessionService
from backend.app.jobs.runner import JobRunner
from backend.app.main import app
from backend.app.services.analysis_service import AnalysisService


@pytest.fixture()
def diag_client(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    db_path = tmp_path / "diag.sqlite"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_path}")
    monkeypatch.setenv("VAGENT_ENV", "development")
    monkeypatch.setenv("ALLOW_MOCK_PREMIUM", "true")
    import backend.app.db.session as sess
    from backend.app.config import get_runtime_dir

    sess._engine = None
    sess._SessionLocal = None
    monkeypatch.setenv("RUNTIME_DIR", str(runtime))
    get_runtime_dir.cache_clear()

    from backend.app.db.models import Base
    from backend.app.db.session import get_engine

    engine = get_engine()
    Base.metadata.create_all(engine)

    svc = AnalysisService()
    svc.runner = JobRunner(svc.runtime_dir, max_workers=1)
    diag = DiagnosticSessionService(svc.runtime_dir)
    monkeypatch.setattr(routes_mod, "service", svc)
    monkeypatch.setattr(routes_mod, "diag", diag)
    yield TestClient(app, raise_server_exceptions=True), diag, runtime
    sess._engine = None
    sess._SessionLocal = None
    get_runtime_dir.cache_clear()


def _wav(duration=4.0) -> bytes:
    sr = 22050
    t = np.arange(int(sr * duration)) / sr
    y = (0.25 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    buf = io.BytesIO()
    sf.write(buf, y, sr, format="WAV")
    return buf.getvalue()


def test_diagnostic_create_persists_db(diag_client):
    client, _, _ = diag_client
    h = {"X-User-Id": "diag-db-a"}
    r = client.post("/v1/diagnostic-sessions", headers=h)
    assert r.status_code == 200
    sid = r.json()["session_id"]
    from backend.app.db.models import DiagnosticSession
    from backend.app.db.session import session_scope

    with session_scope() as session:
        row = session.get(DiagnosticSession, sid)
        assert row is not None
        assert row.status == "CREATED"
        assert isinstance(row.selected_tasks, list)


def test_diagnostic_attempt_persists_db(diag_client):
    client, _, _ = diag_client
    h = {"X-User-Id": "diag-db-b"}
    sid = client.post("/v1/diagnostic-sessions", headers=h).json()["session_id"]
    client.post(
        f"/v1/diagnostic-sessions/{sid}/mock-pay",
        headers=h,
    )
    client.post(
        f"/v1/diagnostic-sessions/{sid}/concerns",
        headers=h,
        json={"diagnostic_mode": "GENERAL_DISCOVERY", "user_concerns": []},
    )
    client.post(
        f"/v1/diagnostic-sessions/{sid}/safety",
        headers=h,
        json={"answers": {"pain_on_phonation": False}},
    )
    # pick first selected task from session
    sess = client.get(f"/v1/diagnostic-sessions/{sid}", headers=h).json()
    tasks = sess.get("selected_tasks") or []
    if not tasks:
        pytest.skip("no selected tasks in plan")
    tid = tasks[0]
    up = client.post(
        f"/v1/diagnostic-sessions/{sid}/tasks/{tid}",
        headers=h,
        files={"file": ("t.wav", _wav(), "audio/wav")},
    )
    assert up.status_code == 200, up.text
    from backend.app.db.models import DiagnosticTaskAttempt
    from backend.app.db.session import session_scope
    from sqlalchemy import select

    with session_scope() as session:
        rows = session.scalars(
            select(DiagnosticTaskAttempt).where(DiagnosticTaskAttempt.session_id == sid)
        ).all()
        assert len(rows) >= 1
        assert rows[0].audio_storage_key
        assert "C:\\" not in (rows[0].audio_storage_key or "")


def test_diagnostic_restart_recovery(diag_client):
    client, diag, runtime = diag_client
    h = {"X-User-Id": "diag-db-c"}
    sid = client.post("/v1/diagnostic-sessions", headers=h).json()["session_id"]
    selected = client.get(f"/v1/diagnostic-sessions/{sid}", headers=h).json()["selected_tasks"]
    # Simulate process restart: new service instance, empty reliance on memory
    fresh = DiagnosticSessionService(runtime)
    loaded = fresh.get_session(sid, user_id="diag-db-c")
    assert loaded is not None
    assert loaded["selected_tasks"] == selected


def test_diagnostic_cross_user_denied(diag_client):
    client, _, _ = diag_client
    ha = {"X-User-Id": "diag-db-d"}
    hb = {"X-User-Id": "diag-db-e"}
    sid = client.post("/v1/diagnostic-sessions", headers=ha).json()["session_id"]
    assert client.get(f"/v1/diagnostic-sessions/{sid}", headers=hb).status_code == 404


def test_diagnostic_db_is_prod_source_of_truth(diag_client):
    client, diag, runtime = diag_client
    h = {"X-User-Id": "diag-db-f"}
    sid = client.post("/v1/diagnostic-sessions", headers=h).json()["session_id"]
    # Corrupt/remove file — DB should still serve
    path = runtime / "diagnostic_sessions" / sid / "session.json"
    if path.exists():
        path.unlink()
    loaded = diag.get_session(sid, user_id="diag-db-f")
    assert loaded is not None
    assert loaded["session_id"] == sid
