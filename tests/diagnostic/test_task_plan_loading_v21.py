"""Precision v2.1 — task plan persistence + protocol catalog + empty≠loading."""

from __future__ import annotations

import io
import struct
import wave

import pytest
from fastapi.testclient import TestClient

from audio_analyzer.diagnostic.planner import build_uncertainty_profile, plan_precision_protocol
from audio_analyzer.diagnostic.protocol import TASKS, get_task, tasks_for_ids, unresolved_task_ids
from audio_analyzer.diagnostic.task_registry import TASK_REGISTRY
from backend.app.main import app


def _wav(seconds: float = 2.0) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(44100)
        wf.writeframes(struct.pack("<h", 1200) * int(44100 * seconds))
    return buf.getvalue()


def _headers(user: str = "plan-persist") -> dict[str, str]:
    return {"X-User-Id": user, "X-VAgent-User-Key": user}


def test_general_discovery_planner_never_returns_zero_normal_tasks():
    profile = build_uncertainty_profile(criteria_matrix=[])
    plan = plan_precision_protocol(profile, diagnostic_mode="GENERAL_DISCOVERY")
    assert len(plan["selected_tasks"]) >= 1
    assert plan["diagnostic_status"] != "SAFETY_LIMITED" or plan["selected_tasks"]


def test_concern_focused_planner_never_returns_zero_normal_tasks():
    profile = build_uncertainty_profile(criteria_matrix=[])
    plan = plan_precision_protocol(
        profile,
        diagnostic_mode="CONCERN_FOCUSED",
        user_concerns=[{"id": "HIGH_NOTE_CANNOT_REACH"}, {"id": "THROAT_EFFORT"}],
    )
    assert len(plan["selected_tasks"]) >= 1


def test_safety_pain_on_phonation_zero_tasks():
    profile = build_uncertainty_profile(criteria_matrix=[])
    plan = plan_precision_protocol(
        profile,
        diagnostic_mode="CONCERN_FOCUSED",
        user_concerns=[{"id": "PAIN_WHILE_SINGING"}],
        pain_safety_flag=True,
        safety_flags=["pain_on_phonation"],
    )
    assert plan["selected_tasks"] == []
    assert plan["diagnostic_status"] == "SAFETY_LIMITED"


def test_safety_discomfort_keeps_safe_tasks():
    profile = build_uncertainty_profile(criteria_matrix=[])
    plan = plan_precision_protocol(
        profile,
        diagnostic_mode="CONCERN_FOCUSED",
        user_concerns=[{"id": "VOCAL_FATIGUE"}],
        pain_safety_flag=True,
        safety_flags=["severe_discomfort_after"],
    )
    assert len(plan["selected_tasks"]) >= 1
    assert "high_note_sustain_a" not in plan["selected_tasks"]
    assert plan["diagnostic_status"] == "NORMAL"


def test_task_ids_exist_in_protocol():
    catalog = {t["task_id"] for t in TASKS}
    for tid in TASK_REGISTRY:
        assert tid in catalog, tid
        assert get_task(tid)["task_id"] == tid
    plan = plan_precision_protocol(
        build_uncertainty_profile(criteria_matrix=[]),
        diagnostic_mode="CONCERN_FOCUSED",
        user_concerns=[{"id": "HIGH_NOTE_CANNOT_REACH"}],
    )
    assert unresolved_task_ids(plan["selected_tasks"]) == []
    assert len(tasks_for_ids(plan["selected_tasks"])) == len(plan["selected_tasks"])
    assert "high_note_sustain_a" in catalog


def test_planned_tasks_are_persisted(tmp_path, monkeypatch):
    from backend.app.api import routes as routes_mod
    from backend.app.diagnostic.service import DiagnosticSessionService
    from backend.app.jobs.runner import JobRunner
    from backend.app.services.analysis_service import AnalysisService

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.setenv("VAGENT_ENV", "development")
    monkeypatch.setenv("ALLOW_MOCK_PREMIUM", "true")
    # Prefer file path for this unit by clearing DB if set in shell
    monkeypatch.delenv("DATABASE_URL", raising=False)
    svc = AnalysisService()
    svc.runtime_dir = runtime
    svc.runner = JobRunner(runtime, max_workers=1)
    diag = DiagnosticSessionService(runtime)
    monkeypatch.setattr(routes_mod, "service", svc)
    monkeypatch.setattr(routes_mod, "diag", diag)
    c = TestClient(app)
    h = _headers("persist-user")
    sid = c.post("/v1/diagnostic-sessions", headers=h).json()["session_id"]
    assert c.post(f"/v1/diagnostic-sessions/{sid}/mock-pay", headers=h).status_code == 200
    out = c.post(
        f"/v1/diagnostic-sessions/{sid}/concerns",
        headers=h,
        json={"diagnostic_mode": "GENERAL_DISCOVERY", "user_concerns": []},
    )
    assert out.status_code == 200
    selected = out.json()["selected_tasks"]
    assert len(selected) >= 1
    raw = diag._load(sid)
    assert raw["selected_tasks"] == selected
    assert raw.get("core_tasks")


def test_session_get_returns_planned_tasks(tmp_path, monkeypatch):
    from backend.app.api import routes as routes_mod
    from backend.app.diagnostic.service import DiagnosticSessionService
    from backend.app.jobs.runner import JobRunner
    from backend.app.services.analysis_service import AnalysisService

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.setenv("VAGENT_ENV", "development")
    monkeypatch.setenv("ALLOW_MOCK_PREMIUM", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    svc = AnalysisService()
    svc.runtime_dir = runtime
    svc.runner = JobRunner(runtime, max_workers=1)
    diag = DiagnosticSessionService(runtime)
    monkeypatch.setattr(routes_mod, "service", svc)
    monkeypatch.setattr(routes_mod, "diag", diag)
    c = TestClient(app)
    h = _headers("get-plan-user")
    sid = c.post("/v1/diagnostic-sessions", headers=h).json()["session_id"]
    c.post(f"/v1/diagnostic-sessions/{sid}/mock-pay", headers=h)
    c.post(
        f"/v1/diagnostic-sessions/{sid}/concerns",
        headers=h,
        json={
            "diagnostic_mode": "CONCERN_FOCUSED",
            "user_concerns": [{"id": "HIGH_NOTE_CANNOT_REACH"}, {"id": "THROAT_EFFORT"}],
        },
    )
    c.post(
        f"/v1/diagnostic-sessions/{sid}/safety",
        headers=h,
        json={"answers": {"pain_on_phonation": False}},
    )
    got = c.get(f"/v1/diagnostic-sessions/{sid}", headers=h).json()
    assert len(got["selected_tasks"]) >= 1
    assert len(got["task_plan"]) == len(got["selected_tasks"])
    assert {t["task_id"] for t in got["task_plan"]} == set(got["selected_tasks"])
    assert all(t.get("title") for t in got["task_plan"])


def test_existing_empty_plan_session_can_replan(tmp_path, monkeypatch):
    from backend.app.api import routes as routes_mod
    from backend.app.diagnostic.service import DiagnosticSessionService
    from backend.app.jobs.runner import JobRunner
    from backend.app.services.analysis_service import AnalysisService

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.setenv("VAGENT_ENV", "development")
    monkeypatch.setenv("ALLOW_MOCK_PREMIUM", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    svc = AnalysisService()
    svc.runtime_dir = runtime
    svc.runner = JobRunner(runtime, max_workers=1)
    diag = DiagnosticSessionService(runtime)
    monkeypatch.setattr(routes_mod, "service", svc)
    monkeypatch.setattr(routes_mod, "diag", diag)
    c = TestClient(app)
    h = _headers("replan-user")
    sid = c.post("/v1/diagnostic-sessions", headers=h).json()["session_id"]
    c.post(f"/v1/diagnostic-sessions/{sid}/mock-pay", headers=h)
    c.post(
        f"/v1/diagnostic-sessions/{sid}/concerns",
        headers=h,
        json={"diagnostic_mode": "GENERAL_DISCOVERY", "user_concerns": []},
    )
    # Corrupt plan as if older bug wiped tasks
    sess = diag._load(sid)
    sess["selected_tasks"] = []
    sess["core_tasks"] = []
    sess["adaptive_tasks"] = []
    sess["tasks"] = {}
    sess["diagnostic_status"] = "NORMAL"
    diag._save(sess)
    fixed = c.post(f"/v1/diagnostic-sessions/{sid}/ensure-plan", headers=h)
    assert fixed.status_code == 200
    body = fixed.json()
    assert len(body["selected_tasks"]) >= 1
    assert body["session_id"] == sid


def test_completed_task_resume_uses_next_task(tmp_path, monkeypatch):
    from backend.app.api import routes as routes_mod
    from backend.app.diagnostic.service import DiagnosticSessionService
    from backend.app.jobs.runner import JobRunner
    from backend.app.services.analysis_service import AnalysisService

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.setenv("VAGENT_ENV", "development")
    monkeypatch.setenv("ALLOW_MOCK_PREMIUM", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    svc = AnalysisService()
    svc.runtime_dir = runtime
    svc.runner = JobRunner(runtime, max_workers=1)
    diag = DiagnosticSessionService(runtime)
    monkeypatch.setattr(routes_mod, "service", svc)
    monkeypatch.setattr(routes_mod, "diag", diag)
    c = TestClient(app)
    h = _headers("resume-user")
    sid = c.post("/v1/diagnostic-sessions", headers=h).json()["session_id"]
    c.post(f"/v1/diagnostic-sessions/{sid}/mock-pay", headers=h)
    c.post(
        f"/v1/diagnostic-sessions/{sid}/concerns",
        headers=h,
        json={"diagnostic_mode": "GENERAL_DISCOVERY", "user_concerns": []},
    )
    c.post(f"/v1/diagnostic-sessions/{sid}/safety", headers=h, json={"answers": {}})
    sess = diag._load(sid)
    first, second = sess["selected_tasks"][0], sess["selected_tasks"][1]
    sess["tasks"][first] = {"attempts": [{"passed": True}], "passed": True}
    sess["current_task_index"] = 0  # stale index
    sess["status"] = "TASKS_IN_PROGRESS"
    diag._save(sess)
    got = c.get(f"/v1/diagnostic-sessions/{sid}", headers=h).json()
    assert got["next_task_id"] == second


def test_task_plan_survives_backend_restart_or_reloadable_store(tmp_path, monkeypatch):
    from backend.app.diagnostic.service import DiagnosticSessionService

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    a = DiagnosticSessionService(runtime)
    session = a.create(user_id="restart-user")
    sid = session["session_id"]
    a.mock_pay(sid, user_id="restart-user")
    a.submit_concerns(sid, [], user_id="restart-user", diagnostic_mode="GENERAL_DISCOVERY")
    planned = a._load(sid)["selected_tasks"]
    assert planned
    b = DiagnosticSessionService(runtime)
    loaded = b.get_session(sid, user_id="restart-user")
    assert loaded["selected_tasks"] == planned


def test_localstorage_not_required_for_task_resume(tmp_path, monkeypatch):
    """Session id in URL + GET is enough — no client storage."""
    from backend.app.api import routes as routes_mod
    from backend.app.diagnostic.service import DiagnosticSessionService
    from backend.app.jobs.runner import JobRunner
    from backend.app.services.analysis_service import AnalysisService

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.setenv("VAGENT_ENV", "development")
    monkeypatch.setenv("ALLOW_MOCK_PREMIUM", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    svc = AnalysisService()
    svc.runtime_dir = runtime
    svc.runner = JobRunner(runtime, max_workers=1)
    diag = DiagnosticSessionService(runtime)
    monkeypatch.setattr(routes_mod, "service", svc)
    monkeypatch.setattr(routes_mod, "diag", diag)
    c = TestClient(app)
    h = _headers("no-ls-user")
    sid = c.post("/v1/diagnostic-sessions", headers=h).json()["session_id"]
    c.post(f"/v1/diagnostic-sessions/{sid}/mock-pay", headers=h)
    c.post(
        f"/v1/diagnostic-sessions/{sid}/concerns",
        headers=h,
        json={"diagnostic_mode": "GENERAL_DISCOVERY", "user_concerns": []},
    )
    c.post(f"/v1/diagnostic-sessions/{sid}/safety", headers=h, json={"answers": {}})
    # Simulate refresh with only session id + headers
    got = c.get(f"/v1/diagnostic-sessions/{sid}", headers=h)
    assert got.status_code == 200
    assert got.json()["next_task_id"]
    assert got.json()["task_plan"]
