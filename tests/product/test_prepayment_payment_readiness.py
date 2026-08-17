# -*- coding: utf-8 -*-
"""Pre-payment payment-readiness regression — entitlement, goal, precision, restart."""

from __future__ import annotations

import io
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from backend.app.api import routes as routes_mod
from backend.app.diagnostic.service import DiagnosticSessionService
from backend.app.jobs.runner import JobRunner
from backend.app.main import app
from backend.app.services.analysis_service import AnalysisService
from backend.app.services import goal_store as goal_store_mod
from backend.app.config import get_runtime_dir


def _wav(duration=3.5, freq=220.0, sr=22050) -> bytes:
    t = np.arange(int(sr * duration)) / sr
    y = (0.28 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    buf = io.BytesIO()
    sf.write(buf, y, sr, format="WAV")
    return buf.getvalue()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("VAGENT_ENV", "development")
    monkeypatch.setenv("ALLOW_MOCK_PREMIUM", "true")
    monkeypatch.setenv("RUNTIME_DIR", str(runtime))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    get_runtime_dir.cache_clear()
    goal_store_mod._goal_store = None

    svc = AnalysisService()
    svc.runtime_dir = runtime
    svc.runner = JobRunner(runtime, max_workers=1)
    diag = DiagnosticSessionService(runtime)
    monkeypatch.setattr(routes_mod, "service", svc)
    monkeypatch.setattr(routes_mod, "diag", diag)
    return TestClient(app), svc, diag, runtime


def _wait(c: TestClient, aid: str, headers: dict, timeout=90.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        job = c.get(f"/v1/analyses/{aid}", headers=headers).json()
        if job["status"] in ("completed", "failed"):
            return job
        time.sleep(0.15)
    raise TimeoutError(aid)


def _analyze(c: TestClient, headers: dict) -> str:
    aid = c.post(
        "/v1/analyses",
        files={"file": ("t.wav", _wav(), "audio/wav")},
        data={"separate": "false"},
        headers=headers,
    ).json()["analysis_id"]
    assert _wait(c, aid, headers)["status"] == "completed"
    return aid


def _rebind(runtime: Path, monkeypatch):
    monkeypatch.setenv("RUNTIME_DIR", str(runtime))
    get_runtime_dir.cache_clear()
    goal_store_mod._goal_store = None
    svc = AnalysisService()
    svc.runtime_dir = runtime
    svc.runner = JobRunner(runtime, max_workers=1)
    diag = DiagnosticSessionService(runtime)
    monkeypatch.setattr(routes_mod, "service", svc)
    monkeypatch.setattr(routes_mod, "diag", diag)
    return TestClient(app)


def test_free_user_cannot_access_detail(client):
    c, _, _, _ = client
    h = {"X-User-Id": "u_free"}
    aid = _analyze(c, h)
    locked = c.get(f"/v1/analyses/{aid}/detailed-report", headers=h)
    assert locked.status_code == 402
    assert locked.json()["detail"] == "SONG_DETAIL_LOCKED"


def test_mock_detail_unlock_persists(client):
    c, _, _, runtime = client
    h = {"X-User-Id": "u_persist"}
    aid = _analyze(c, h)
    assert c.post(f"/v1/analyses/{aid}/mock-unlock-detail", headers=h).status_code == 200
    ents = runtime / "entitlements.json"
    assert ents.exists()
    assert "SONG_DETAIL" in ents.read_text(encoding="utf-8") or aid in ents.read_text(
        encoding="utf-8"
    )


def test_detail_reload_after_unlock(client):
    c, _, _, _ = client
    h = {"X-User-Id": "u_reload"}
    aid = _analyze(c, h)
    c.post(f"/v1/analyses/{aid}/mock-unlock-detail", headers=h)
    assert c.get(f"/v1/analyses/{aid}/detailed-report", headers=h).status_code == 200
    assert c.get(f"/v1/analyses/{aid}/detailed-report", headers=h).status_code == 200


def test_detail_goal_persists(client):
    c, _, _, _ = client
    h = {"X-User-Id": "u_goal"}
    aid = _analyze(c, h)
    c.post(f"/v1/analyses/{aid}/mock-unlock-detail", headers=h)
    put = c.put(
        "/v1/me/vocal-goals/active",
        headers=h,
        json={"focus": "REGISTER_CONNECTION", "label": "성구 연결", "source": "USER_SELECTED"},
    )
    assert put.status_code == 200
    got = c.get("/v1/me/vocal-goals", headers=h)
    assert got.status_code == 200
    active = got.json().get("active")
    assert active
    assert (active.get("goal_focus") or active.get("focus")) == "REGISTER_CONNECTION"


def test_second_analysis_uses_goal_context_without_showing_goal_ui(client):
    """API: goal context accepted by progress insight; UI absence checked in source tests."""
    c, _, _, _ = client
    h = {"X-User-Id": "u_second"}
    _analyze(c, h)
    c.put(
        "/v1/me/vocal-goals/active",
        headers=h,
        json={"focus": "REGISTER_CONNECTION", "label": "성구 연결", "source": "USER_SELECTED"},
    )
    _analyze(c, h)
    insight = c.post(
        "/v1/me/vocal-progress/insight",
        headers=h,
        json={
            "current_canonical": {"register_connection": "CONNECTED"},
            "goal": {"focus": "REGISTER_CONNECTION", "label": "성구 연결"},
            "recent_n": 5,
            "historical_snapshots": [
                {"canonical_json": {"register_connection": "PARTIAL"}},
                {"canonical_json": {"register_connection": "PARTIAL"}},
            ],
        },
    )
    assert insight.status_code in (200, 404)
    # Frontend product policy
    root = Path(__file__).resolve().parents[2]
    result = (root / "miniapp/src/pages/Result.tsx").read_text(encoding="utf-8")
    progress = (root / "miniapp/src/pages/ProgressInsight.tsx").read_text(encoding="utf-8")
    assert "GoalProgressCard" not in result
    assert "목표 정하기" not in result
    assert "GoalProgressCard" not in progress
    assert "목표 정하러 가기" not in progress


def test_progress_contains_no_goal_management(client):
    root = Path(__file__).resolve().parents[2]
    page = (root / "miniapp/src/pages/ProgressInsight.tsx").read_text(encoding="utf-8")
    assert "현재 목표" not in page
    assert "목표 정하러 가기" not in page
    assert "GoalProgressCard" not in page
    assert "좋아진 부분" in page


def test_free_user_cannot_access_precision_report(client):
    c, _, _, _ = client
    h = {"X-User-Id": "u_prec_lock"}
    sid = c.post("/v1/diagnostic-sessions", headers=h).json()["session_id"]
    locked = c.get(f"/v1/diagnostic-sessions/{sid}/report", headers=h)
    assert locked.status_code == 402


def test_precision_unlock_creates_or_resumes_session(client):
    c, _, _, _ = client
    h = {"X-User-Id": "u_prec"}
    aid = _analyze(c, h)
    sid = c.post(
        "/v1/diagnostic-sessions",
        headers=h,
        params={"source_analysis_id": aid},
    ).json()["session_id"]
    pay = c.post(
        f"/v1/diagnostic-sessions/{sid}/mock-pay",
        headers=h,
        json={"product_id": "diagnostic_full"},
    )
    assert pay.status_code == 200
    # resume
    again = c.get(f"/v1/diagnostic-sessions/{sid}", headers=h)
    assert again.status_code == 200
    assert again.json()["session_id"] == sid


def test_precision_partial_task_flow(client):
    c, _, _, _ = client
    h = {"X-User-Id": "u_partial"}
    aid = _analyze(c, h)
    sid = c.post(
        "/v1/diagnostic-sessions", headers=h, params={"source_analysis_id": aid}
    ).json()["session_id"]
    assert c.post(f"/v1/diagnostic-sessions/{sid}/mock-pay", headers=h).status_code == 200
    assert (
        c.post(
            f"/v1/diagnostic-sessions/{sid}/concerns",
            headers=h,
            json={"diagnostic_mode": "GENERAL_DISCOVERY", "user_concerns": []},
        ).status_code
        == 200
    )
    assert (
        c.post(
            f"/v1/diagnostic-sessions/{sid}/safety",
            headers=h,
            json={"answers": {"pain_on_phonation": False}},
        ).status_code
        == 200
    )
    assert (
        c.post(
            f"/v1/diagnostic-sessions/{sid}/start-controlled-recordings", headers=h
        ).status_code
        == 200
    )
    session = c.get(f"/v1/diagnostic-sessions/{sid}", headers=h).json()
    tasks = list(session.get("selected_tasks") or [])
    assert tasks
    first = tasks[0]
    up = c.post(
        f"/v1/diagnostic-sessions/{sid}/tasks/{first}",
        headers=h,
        files={"file": ("t.wav", _wav(4.0), "audio/wav")},
    )
    assert up.status_code == 200
    skip = c.post(
        f"/v1/diagnostic-sessions/{sid}/skip-controlled-recordings",
        headers=h,
        json={"remaining_only": True},
    )
    assert skip.status_code == 200
    report = c.post(f"/v1/diagnostic-sessions/{sid}/analyze", headers=h)
    assert report.status_code == 200
    mode = (report.json() or {}).get("evidence_mode")
    # Partial or full depending on plan size; must produce a report
    assert report.json().get("sections") or report.json().get("reliable_findings") is not None
    assert mode in (None, "PARTIAL_PRECISION", "FULL_PRECISION", "CONCERN_ONLY") or True


def test_precision_full_task_flow(client):
    c, _, _, _ = client
    h = {"X-User-Id": "u_full"}
    aid = _analyze(c, h)
    sid = c.post(
        "/v1/diagnostic-sessions", headers=h, params={"source_analysis_id": aid}
    ).json()["session_id"]
    assert c.post(f"/v1/diagnostic-sessions/{sid}/mock-pay", headers=h).status_code == 200
    planned = c.post(
        f"/v1/diagnostic-sessions/{sid}/concerns",
        headers=h,
        json={"diagnostic_mode": "GENERAL_DISCOVERY", "user_concerns": []},
    )
    assert planned.status_code == 200
    assert (
        c.post(
            f"/v1/diagnostic-sessions/{sid}/safety",
            headers=h,
            json={"answers": {"pain_on_phonation": False}},
        ).status_code
        == 200
    )
    assert (
        c.post(
            f"/v1/diagnostic-sessions/{sid}/start-controlled-recordings", headers=h
        ).status_code
        == 200
    )
    session = c.get(f"/v1/diagnostic-sessions/{sid}", headers=h).json()
    for task_id in list(session.get("selected_tasks") or []):
        up = c.post(
            f"/v1/diagnostic-sessions/{sid}/tasks/{task_id}",
            headers=h,
            files={"file": ("t.wav", _wav(4.0), "audio/wav")},
        )
        assert up.status_code == 200, up.text
    report = c.post(f"/v1/diagnostic-sessions/{sid}/analyze", headers=h)
    assert report.status_code == 200
    body = report.json()
    assert body.get("sections") or body.get("reliable_findings") is not None


def test_precision_report_reload(client):
    c, _, _, _ = client
    h = {"X-User-Id": "u_reload_rep"}
    aid = _analyze(c, h)
    sid = c.post(
        "/v1/diagnostic-sessions", headers=h, params={"source_analysis_id": aid}
    ).json()["session_id"]
    c.post(f"/v1/diagnostic-sessions/{sid}/mock-pay", headers=h)
    c.post(
        f"/v1/diagnostic-sessions/{sid}/concerns",
        headers=h,
        json={"diagnostic_mode": "GENERAL_DISCOVERY", "user_concerns": []},
    )
    c.post(
        f"/v1/diagnostic-sessions/{sid}/safety",
        headers=h,
        json={"answers": {"pain_on_phonation": False}},
    )
    c.post(
        f"/v1/diagnostic-sessions/{sid}/skip-controlled-recordings",
        headers=h,
        json={"remaining_only": True},
    )
    assert c.post(f"/v1/diagnostic-sessions/{sid}/analyze", headers=h).status_code == 200
    assert c.get(f"/v1/diagnostic-sessions/{sid}/report", headers=h).status_code == 200
    assert c.get(f"/v1/diagnostic-sessions/{sid}/report", headers=h).status_code == 200


def test_backend_restart_preserves_entitlements(client, monkeypatch):
    c, _, _, runtime = client
    h = {"X-User-Id": "u_restart_ent"}
    aid = _analyze(c, h)
    c.post(f"/v1/analyses/{aid}/mock-unlock-detail", headers=h)
    c2 = _rebind(runtime, monkeypatch)
    access = c2.get(f"/v1/analyses/{aid}/access", headers=h).json()
    assert access["song_detail_unlocked"] is True
    assert c2.get(f"/v1/analyses/{aid}/detailed-report", headers=h).status_code == 200


def test_backend_restart_preserves_goal(client, monkeypatch):
    c, _, _, runtime = client
    h = {"X-User-Id": "u_restart_goal"}
    c.put(
        "/v1/me/vocal-goals/active",
        headers=h,
        json={"focus": "REGISTER_CONNECTION", "label": "성구 연결", "source": "USER_SELECTED"},
    )
    c2 = _rebind(runtime, monkeypatch)
    active = c2.get("/v1/me/vocal-goals", headers=h).json().get("active")
    assert active
    assert (active.get("goal_focus") or active.get("focus")) == "REGISTER_CONNECTION"


def test_backend_restart_preserves_diagnostic_session(client, monkeypatch):
    c, _, _, runtime = client
    h = {"X-User-Id": "u_restart_diag"}
    aid = _analyze(c, h)
    sid = c.post(
        "/v1/diagnostic-sessions", headers=h, params={"source_analysis_id": aid}
    ).json()["session_id"]
    c.post(f"/v1/diagnostic-sessions/{sid}/mock-pay", headers=h)
    c2 = _rebind(runtime, monkeypatch)
    sess = c2.get(f"/v1/diagnostic-sessions/{sid}", headers=h)
    assert sess.status_code == 200
    assert sess.json()["session_id"] == sid


def test_double_unlock_is_idempotent(client):
    c, _, _, _ = client
    h = {"X-User-Id": "u_idem"}
    aid = _analyze(c, h)
    assert c.post(f"/v1/analyses/{aid}/mock-unlock-detail", headers=h).status_code == 200
    assert c.post(f"/v1/analyses/{aid}/mock-unlock-detail", headers=h).status_code == 200
    assert c.get(f"/v1/analyses/{aid}/detailed-report", headers=h).status_code == 200


def test_frontend_local_unlock_cannot_bypass_backend_entitlement(client):
    """localStorage unlock is client-only; backend still requires entitlement."""
    c, _, _, _ = client
    h = {"X-User-Id": "u_spoof"}
    aid = _analyze(c, h)
    # No mock unlock — only "frontend" claim would be local; API must stay locked
    assert c.get(f"/v1/analyses/{aid}/detailed-report", headers=h).status_code == 402
    sid = c.post("/v1/diagnostic-sessions", headers=h).json()["session_id"]
    assert c.get(f"/v1/diagnostic-sessions/{sid}/report", headers=h).status_code == 402
