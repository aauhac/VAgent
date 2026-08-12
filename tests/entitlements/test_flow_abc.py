"""API-level E2E for Song Detail vs Diagnostic flows A/B/C."""

from __future__ import annotations

import io
import time

import numpy as np
import soundfile as sf
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.api import routes as routes_mod
from backend.app.diagnostic.service import DiagnosticSessionService
from backend.app.services.analysis_service import AnalysisService
from backend.app.jobs.runner import JobRunner


@pytest.fixture()
def client(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    svc = AnalysisService()
    svc.runtime_dir = runtime
    svc.max_upload_mb = 2.0
    svc.runner = JobRunner(runtime, max_workers=1)
    diag = DiagnosticSessionService(runtime)
    monkeypatch.setattr(routes_mod, "service", svc)
    monkeypatch.setattr(routes_mod, "diag", diag)
    monkeypatch.setenv("VAGENT_ENV", "development")
    monkeypatch.setenv("ALLOW_MOCK_PREMIUM", "true")
    return TestClient(app)


def _wav(duration=3.5, freq=220.0, sr=22050) -> bytes:
    t = np.arange(int(sr * duration)) / sr
    y = (0.28 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    buf = io.BytesIO()
    sf.write(buf, y, sr, format="WAV")
    return buf.getvalue()


def _wait(c, aid):
    t0 = time.time()
    while time.time() - t0 < 60:
        job = c.get(f"/v1/analyses/{aid}", headers={"X-User-Id": "demo-user"}).json()
        if job["status"] in ("completed", "failed"):
            return job
        time.sleep(0.2)
    raise TimeoutError(aid)


def test_flow_a_song_detail_no_safety_redirect(client):
    """FLOW A: free → mock song detail → detailed report (NOT diagnostic tasks)."""
    c = client
    h = {"X-User-Id": "demo-user"}
    aid = c.post(
        "/v1/analyses", files={"file": ("s.wav", _wav(), "audio/wav")}, headers=h
    ).json()["analysis_id"]
    _wait(c, aid)
    unlock = c.post(f"/v1/analyses/{aid}/mock-unlock-detail", headers=h).json()
    assert "/detail" in unlock["redirect"]
    assert "safety" not in unlock["redirect"]
    assert "diagnostic" not in unlock["redirect"]
    report = c.get(f"/v1/analyses/{aid}/detailed-report", headers=h)
    assert report.status_code == 200
    assert report.json()["report_kind"] == "song_detail"
    # Song detail must NOT unlock diagnostic session access by itself
    sid = c.post(
        "/v1/diagnostic-sessions", headers=h, params={"source_analysis_id": aid}
    ).json()["session_id"]
    assert c.post(
        f"/v1/diagnostic-sessions/{sid}/safety", headers=h, json={"answers": {}}
    ).status_code == 402


def test_flow_b_diagnostic_full_to_safety(client):
    """FLOW B: free → diagnostic full mock → safety allowed (+ song detail)."""
    c = client
    h = {"X-User-Id": "demo-user"}
    aid = c.post(
        "/v1/analyses", files={"file": ("s.wav", _wav(), "audio/wav")}, headers=h
    ).json()["analysis_id"]
    _wait(c, aid)
    sid = c.post(
        "/v1/diagnostic-sessions", headers=h, params={"source_analysis_id": aid}
    ).json()["session_id"]
    c.post(
        f"/v1/diagnostic-sessions/{sid}/mock-pay",
        headers=h,
        json={"product_id": "diagnostic_full"},
    )
    assert c.get(f"/v1/analyses/{aid}/detailed-report", headers=h).status_code == 200
    assert (
        c.post(
            f"/v1/diagnostic-sessions/{sid}/safety",
            headers=h,
            json={"answers": {"pain_on_phonation": False}},
        ).status_code
        == 200
    )


def test_flow_c_upgrade_after_song_detail(client):
    """FLOW C: song detail → upgrade → safety."""
    c = client
    h = {"X-User-Id": "demo-user"}
    aid = c.post(
        "/v1/analyses", files={"file": ("s.wav", _wav(), "audio/wav")}, headers=h
    ).json()["analysis_id"]
    _wait(c, aid)
    c.post(f"/v1/analyses/{aid}/mock-unlock-detail", headers=h)
    offers = c.get(f"/v1/products?analysis_id={aid}", headers=h).json()
    assert offers["offers"]["diagnostic"] == "diagnostic_upgrade"
    sid = c.post(
        "/v1/diagnostic-sessions", headers=h, params={"source_analysis_id": aid}
    ).json()["session_id"]
    c.post(
        f"/v1/diagnostic-sessions/{sid}/mock-pay",
        headers=h,
        json={"product_id": "diagnostic_upgrade"},
    )
    assert (
        c.post(
            f"/v1/diagnostic-sessions/{sid}/safety",
            headers=h,
            json={"answers": {}},
        ).status_code
        == 200
    )
    assert c.get(f"/v1/analyses/{aid}/detailed-report", headers=h).status_code == 200
