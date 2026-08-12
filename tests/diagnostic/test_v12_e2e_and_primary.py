"""Primary rejection trace + diagnostic E2E session flows."""

from __future__ import annotations

import io

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from audio_analyzer.coaching.bottleneck.ranker import select_primary
from backend.app.api import routes as routes_mod
from backend.app.diagnostic.service import DiagnosticSessionService
from backend.app.jobs.runner import JobRunner
from backend.app.main import app
from backend.app.services.analysis_service import AnalysisService


def test_select_primary_keeps_rejection_trace_when_none():
    hyps = [
        {
            "id": "GENERAL_EXCESS_EFFORT",
            "confidence_label": "low",
            "supporting_episode_ids": ["e1"],
            "supporting_evidence": [{"x": 1}],
        },
        {
            "id": "EXCESS_EFFORT_HIGH_NOTE",
            "confidence_label": "medium",
            "supporting_episode_ids": [],
            "supporting_evidence": [{"x": 1}],
        },
    ]
    primary, secondary, trace = select_primary(hyps, criteria_matrix=None)
    assert primary is None
    assert secondary == []
    assert any(r["reason"] == "confidence_below_medium" for r in trace)
    assert any(r["reason"] == "no_supporting_episode" for r in trace)


def test_criteria_reject_reason_retained():
    hyps = [
        {
            "id": "GENERAL_EXCESS_EFFORT",
            "confidence_label": "medium",
            "supporting_episode_ids": ["e1"],
            "supporting_evidence": [{"x": 1}],
        }
    ]
    matrix = [
        {
            "dimension_id": "vocal_effort_strain",
            "coaching_eligibility": "NO",
            "measurement_sufficiency": "INSUFFICIENT",
            "required_satisfied": 0,
            "required_total": 2,
            "criteria": [],
        }
    ]
    # BOTTLENECK_DIMENSION must map GENERAL_EXCESS_EFFORT → vocal_effort_strain
    from audio_analyzer.vocal_function.criteria_registry import BOTTLENECK_DIMENSION

    dim = BOTTLENECK_DIMENSION.get("GENERAL_EXCESS_EFFORT")
    if dim:
        matrix[0]["dimension_id"] = dim
    primary, _, trace = select_primary(hyps, criteria_matrix=matrix)
    assert primary is None
    assert any(
        r["reason"] in ("criteria_not_coaching_eligible", "required_criteria_below_minimum")
        for r in trace
    )


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


def test_e2e_safety_limited_zero_task_flow(client):
    """Only SAFETY_LIMITED may finish Precision with zero controlled recordings."""
    c, diag, runtime = client
    headers = {"X-User-Id": "demo-user"}
    r = c.post("/v1/diagnostic-sessions", headers=headers)
    sid = r.json()["session_id"]
    assert c.post(f"/v1/diagnostic-sessions/{sid}/mock-pay", headers=headers).status_code == 200
    assert (
        c.post(
            f"/v1/diagnostic-sessions/{sid}/concerns",
            headers=headers,
            json={
                "diagnostic_mode": "CONCERN_FOCUSED",
                "user_concerns": [{"id": "PAIN_WHILE_SINGING"}],
            },
        ).status_code
        == 200
    )
    safety = c.post(
        f"/v1/diagnostic-sessions/{sid}/safety",
        headers=headers,
        json={"answers": {"pain_on_phonation": True}},
    )
    assert safety.status_code == 200
    body = safety.json()
    assert body["status"] == "READY_FOR_ANALYSIS"
    assert body["selected_tasks"] == []
    assert body.get("diagnostic_status") == "SAFETY_LIMITED"
    assert c.post(f"/v1/diagnostic-sessions/{sid}/analyze", headers=headers).status_code == 200


def test_e2e_normal_flow_never_zero_tasks(client):
    c, _, _ = client
    headers = {"X-User-Id": "demo-user-normal"}
    r = c.post("/v1/diagnostic-sessions", headers=headers)
    sid = r.json()["session_id"]
    assert c.post(f"/v1/diagnostic-sessions/{sid}/mock-pay", headers=headers).status_code == 200
    concerns = c.post(
        f"/v1/diagnostic-sessions/{sid}/concerns",
        headers=headers,
        json={"diagnostic_mode": "GENERAL_DISCOVERY", "user_concerns": []},
    )
    assert concerns.status_code == 200
    assert len(concerns.json().get("selected_tasks") or []) >= 1
    safety = c.post(
        f"/v1/diagnostic-sessions/{sid}/safety",
        headers=headers,
        json={"answers": {"pain_on_phonation": False}},
    )
    assert safety.status_code == 200
    body = safety.json()
    assert body["status"] == "TASKS_IN_PROGRESS"
    assert len(body["selected_tasks"]) >= 1


def test_e2e_one_task_siren_flow(client):
    c, diag, _ = client
    headers = {"X-User-Id": "demo-user"}
    r = c.post("/v1/diagnostic-sessions", headers=headers)
    sid = r.json()["session_id"]
    assert c.post(f"/v1/diagnostic-sessions/{sid}/mock-pay", headers=headers).status_code == 200
    assert (
        c.post(
            f"/v1/diagnostic-sessions/{sid}/concerns",
            headers=headers,
            json={"diagnostic_mode": "GENERAL_DISCOVERY", "user_concerns": []},
        ).status_code
        == 200
    )
    assert (
        c.post(
            f"/v1/diagnostic-sessions/{sid}/safety",
            headers=headers,
            json={"answers": {}},
        ).status_code
        == 200
    )
    # Force single siren upload path for this e2e (planner may select a larger core set)
    session = diag._load(sid)
    session["selected_tasks"] = ["siren"]
    session["core_tasks"] = ["siren"]
    session["adaptive_tasks"] = []
    session["tasks"] = {"siren": {"attempts": [], "passed": False}}
    session["current_task_index"] = 0
    session["status"] = "TASKS_IN_PROGRESS"
    session["unresolved_dimensions"] = ["register"]
    diag._save(session)
    # glide-ish chirp
    sr = 22050
    t = np.arange(int(sr * 5.0)) / sr
    f = 180 + 180 * (t / 5.0)
    phase = 2 * np.pi * np.cumsum(f) / sr
    y = (0.28 * np.sin(phase)).astype(np.float32)
    buf = io.BytesIO()
    sf.write(buf, y, sr, format="WAV")
    files = {"file": ("siren.wav", buf.getvalue(), "audio/wav")}
    up = c.post(
        f"/v1/diagnostic-sessions/{sid}/tasks/siren",
        headers=headers,
        files=files,
    )
    assert up.status_code == 200
    assert up.json()["session"]["status"] in ("READY_FOR_ANALYSIS", "TASKS_IN_PROGRESS")
    if up.json()["attempt"]["passed"]:
        assert c.post(f"/v1/diagnostic-sessions/{sid}/analyze", headers=headers).status_code == 200


def test_e2e_standalone_full_battery_default(client):
    c, _, _ = client
    headers = {"X-User-Id": "demo-user"}
    r = c.post("/v1/diagnostic-sessions", headers=headers)
    body = r.json()
    # Create keeps provisional empty until concern/general intake
    assert body.get("selected_tasks") == [] or body.get("planned_task_count") is None
    sid = body["session_id"]
    assert c.post(f"/v1/diagnostic-sessions/{sid}/mock-pay", headers=headers).status_code == 200
    planned = c.post(
        f"/v1/diagnostic-sessions/{sid}/concerns",
        headers=headers,
        json={"diagnostic_mode": "GENERAL_DISCOVERY", "user_concerns": []},
    )
    assert planned.status_code == 200
    tasks = planned.json().get("selected_tasks") or []
    assert len(tasks) >= 1
    assert "sustain_a" in tasks
