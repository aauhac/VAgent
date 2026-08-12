"""Diagnostic session API + entitlement isolation tests."""

from __future__ import annotations

import io
from pathlib import Path

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
    return TestClient(app), diag, runtime


def _wav(duration=4.0, freq=220.0, sr=22050) -> bytes:
    t = np.arange(int(sr * duration)) / sr
    y = (0.28 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    buf = io.BytesIO()
    sf.write(buf, y, sr, format="WAV")
    return buf.getvalue()


def test_protocol_endpoint(client):
    c, _, _ = client
    r = c.get("/v1/diagnostic/protocol")
    assert r.status_code == 200
    body = r.json()
    assert body["protocol_version"] == "diagnostic-protocol-v1.3"
    assert body.get("adaptive") is True
    assert len(body["tasks"]) >= 5
    ids = {t["task_id"] for t in body["tasks"]}
    assert "high_note_sustain_a" in ids
    assert "sustain_a" in ids
    assert "siren" in ids


def test_unpaid_report_locked(client):
    c, _, _ = client
    r = c.post("/v1/diagnostic-sessions", headers={"X-User-Id": "u1"})
    assert r.status_code == 200
    sid = r.json()["session_id"]
    locked = c.get(f"/v1/diagnostic-sessions/{sid}/report", headers={"X-User-Id": "u1"})
    assert locked.status_code == 402
    assert locked.json()["detail"] == "REPORT_LOCKED"


def test_mock_pay_safety_tasks_analyze(client):
    c, _, _ = client
    headers = {"X-User-Id": "demo-user"}
    r = c.post("/v1/diagnostic-sessions", headers=headers)
    sid = r.json()["session_id"]
    assert c.post(f"/v1/diagnostic-sessions/{sid}/mock-pay", headers=headers).status_code == 200
    planned = c.post(
        f"/v1/diagnostic-sessions/{sid}/concerns",
        headers=headers,
        json={"diagnostic_mode": "GENERAL_DISCOVERY", "user_concerns": []},
    )
    assert planned.status_code == 200
    selected = list(planned.json().get("selected_tasks") or [])
    assert len(selected) >= 1
    assert (
        c.post(
            f"/v1/diagnostic-sessions/{sid}/safety",
            headers=headers,
            json={"answers": {"pain_on_phonation": False}},
        ).status_code
        == 200
    )
    session = c.get(f"/v1/diagnostic-sessions/{sid}", headers=headers).json()
    selected = list(session.get("selected_tasks") or [])
    durations = {
        "sustain_a": 4.0,
        "sustain_i": 4.0,
        "siren": 5.0,
        "dynamic_swell": 4.5,
        "high_note_sustain_a": 4.0,
    }
    for task_id in selected:
        data = _wav(duration=durations.get(task_id, 4.0))
        up = c.post(
            f"/v1/diagnostic-sessions/{sid}/tasks/{task_id}",
            headers=headers,
            files={"file": ("t.wav", data, "audio/wav")},
        )
        assert up.status_code == 200, up.text
        assert up.json()["attempt"]["passed"] is True

    report = c.post(f"/v1/diagnostic-sessions/{sid}/analyze", headers=headers)
    assert report.status_code == 200
    body = report.json()
    assert "sections" in body
    assert body["sections"]["B_reliable"]["items"]
    assert body["sections"]["B_needs_more"]["items"]
    assert "scientific_debug" not in body
    assert body["inference_version"] == "physiology-inference-v1.3"

    again = c.get(f"/v1/diagnostic-sessions/{sid}/report", headers=headers)
    assert again.status_code == 200

    # other user cannot access (ownership → 404, not unlock leak)
    other = c.get(f"/v1/diagnostic-sessions/{sid}/report", headers={"X-User-Id": "other"})
    assert other.status_code == 404


def test_task_quality_fail_retries_same_task(client):
    c, _, _ = client
    headers = {"X-User-Id": "u2"}
    sid = c.post("/v1/diagnostic-sessions", headers=headers).json()["session_id"]
    c.post(f"/v1/diagnostic-sessions/{sid}/mock-pay", headers=headers)
    c.post(
        f"/v1/diagnostic-sessions/{sid}/concerns",
        headers=headers,
        json={"diagnostic_mode": "GENERAL_DISCOVERY", "user_concerns": []},
    )
    c.post(
        f"/v1/diagnostic-sessions/{sid}/safety",
        headers=headers,
        json={"answers": {}},
    )
    short = _wav(duration=0.4)
    fail = c.post(
        f"/v1/diagnostic-sessions/{sid}/tasks/sustain_a",
        headers=headers,
        files={"file": ("short.wav", short, "audio/wav")},
    )
    assert fail.status_code == 200
    assert fail.json()["attempt"]["passed"] is False
    assert fail.json()["retry_allowed"] is True
    ok = c.post(
        f"/v1/diagnostic-sessions/{sid}/tasks/sustain_a",
        headers=headers,
        files={"file": ("ok.wav", _wav(4.0), "audio/wav")},
    )
    assert ok.json()["attempt"]["passed"] is True


def test_mock_pay_disabled_in_production(client, monkeypatch):
    c, _, _ = client
    monkeypatch.setenv("VAGENT_ENV", "production")
    # re-bind allow_dev_bypass by reloading check — service reads env each call
    headers = {"X-User-Id": "u3"}
    sid = c.post("/v1/diagnostic-sessions", headers=headers).json()["session_id"]
    r = c.post(f"/v1/diagnostic-sessions/{sid}/mock-pay", headers=headers)
    assert r.status_code == 403
