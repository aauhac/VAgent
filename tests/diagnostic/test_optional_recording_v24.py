"""Precision Diagnostic v2.4 — optional controlled recording / skip / evidence_mode."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from audio_analyzer.diagnostic.coaching import derive_precision_strengths
from audio_analyzer.diagnostic.concern_resolver import evaluate_concern
from audio_analyzer.diagnostic.evidence_mode import (
    EVIDENCE_MODE_CONCERN_ONLY,
    EVIDENCE_MODE_FULL,
    EVIDENCE_MODE_PARTIAL,
    derive_evidence_mode,
    mark_task_user_skipped,
    sync_skip_provenance,
)
from audio_analyzer.diagnostic.fusion import build_final_diagnostic_profile


def _session_skeleton(selected: list[str]) -> dict:
    return {
        "selected_tasks": list(selected),
        "tasks": {t: {"attempts": [], "passed": False} for t in selected},
        "task_results": [],
        "diagnostic_status": "NORMAL",
    }


def test_full_precision_mode():
    s = _session_skeleton(["sustain_a", "high_note_sustain_a"])
    s["tasks"]["sustain_a"]["passed"] = True
    s["tasks"]["high_note_sustain_a"]["passed"] = True
    s["task_results"] = [{"task_id": "sustain_a"}, {"task_id": "high_note_sustain_a"}]
    sync_skip_provenance(s)
    assert s["evidence_mode"] == EVIDENCE_MODE_FULL


def test_partial_precision_mode():
    s = _session_skeleton(["sustain_a", "siren", "high_note_sustain_a"])
    s["tasks"]["sustain_a"]["passed"] = True
    s["tasks"]["siren"] = mark_task_user_skipped(s["tasks"]["siren"])
    s["tasks"]["high_note_sustain_a"]["passed"] = True
    s["task_results"] = [{"task_id": "sustain_a"}, {"task_id": "high_note_sustain_a"}]
    sync_skip_provenance(s)
    assert s["evidence_mode"] == EVIDENCE_MODE_PARTIAL
    assert "siren" in s["user_skipped_tasks"]
    assert "siren" not in s["completed_tasks"]


def test_concern_only_mode():
    s = _session_skeleton(["sustain_a", "siren"])
    for tid in s["selected_tasks"]:
        s["tasks"][tid] = mark_task_user_skipped(s["tasks"][tid])
    sync_skip_provenance(s)
    assert s["evidence_mode"] == EVIDENCE_MODE_CONCERN_ONLY
    assert s["selected_tasks"] == ["sustain_a", "siren"]  # preserved


def test_user_skip_is_not_quality_fail():
    st = mark_task_user_skipped({"attempts": [], "passed": False})
    assert st.get("skipped") is True
    assert st.get("skip_reason") == "USER_CHOICE"
    assert st.get("passed") is False
    assert not st.get("quality_fail")


def test_safety_limited_is_not_concern_only_label_path():
    # evidence_mode may share no-task outcome for empty plan; diagnostic_status stays separate
    s = {
        "selected_tasks": [],
        "tasks": {},
        "task_results": [],
        "diagnostic_status": "SAFETY_LIMITED",
    }
    mode = derive_evidence_mode(s)
    # Empty legacy plan → FULL-era default; status still SAFETY_LIMITED
    assert mode == EVIDENCE_MODE_FULL
    assert s["diagnostic_status"] == "SAFETY_LIMITED"
    # Safety-blocked planned tasks are not USER_SKIPPED
    s2 = {
        "selected_tasks": ["high_note_sustain_a"],
        "tasks": {
            "high_note_sustain_a": {
                "attempts": [],
                "passed": False,
                "safety_blocked": True,
            }
        },
        "task_results": [],
        "diagnostic_status": "SAFETY_LIMITED",
    }
    assert derive_evidence_mode(s2) == EVIDENCE_MODE_CONCERN_ONLY
    from audio_analyzer.diagnostic.evidence_mode import list_user_skipped_tasks

    assert list_user_skipped_tasks(s2) == []


def test_skipped_high_note_does_not_confirm_high_note_effort():
    fused = {
        "task_profiles": {
            "sustain_a": {
                "task_id": "sustain_a",
                "valid": True,
                "dimensions": {"effort": {"status": "LOW", "available": True, "estimate": 0.3}},
            }
        },
        "controlled_contrasts": {},
        "task_evidence": {"user_skipped_tasks": ["high_note_sustain_a"]},
        "user_skipped_tasks": ["high_note_sustain_a"],
    }
    song = {"vocal_function_profile": {"effort_assessment": {"severity": "LOW"}}}
    ev = evaluate_concern("HIGH_NOTE_TOO_EFFORTFUL", song_profile=song, task_evidence=fused)
    assert ev["status"] != "CONFIRMED"
    assert ev.get("unresolved_reason") == "USER_SKIPPED_RELEVANT_TASK"


def test_skipped_high_note_does_not_create_high_note_strength():
    fused = {
        "task_profiles": {},
        "controlled_contrasts": {
            "baseline_vs_high": {
                "dimensions": {
                    "effort": {
                        "available": True,
                        "direction": "SIMILAR",
                        "baseline": "LOW",
                        "high": "LOW",
                    }
                }
            }
        },
        "task_evidence": {"user_skipped_tasks": ["high_note_sustain_a"]},
        "user_skipped_tasks": ["high_note_sustain_a"],
    }
    strengths = derive_precision_strengths(concern_evaluations=[], fused_profile=fused)
    assert not any(s["id"] == "LOW_EFFORT_HIGH_NOTE_MAINTAINED" for s in strengths)


def test_skipped_siren_does_not_create_register_strength():
    fused = {
        "task_profiles": {
            "siren": {
                "task_id": "siren",
                "valid": True,
                "dimensions": {"register": {"status": "CONNECTED", "available": True}},
            }
        },
        "controlled_contrasts": {},
        "user_skipped_tasks": ["siren"],
        "task_evidence": {"user_skipped_tasks": ["siren"]},
    }
    # Even if stale profile present, skip guard blocks strength
    strengths = derive_precision_strengths(concern_evaluations=[], fused_profile=fused)
    assert not any(s["id"] == "REGISTER_CONNECTION_MAINTAINED" for s in strengths)


def test_concern_is_not_truth_when_all_tasks_skipped():
    fused = {
        "task_profiles": {},
        "controlled_contrasts": {},
        "user_skipped_tasks": ["sustain_a", "high_note_sustain_a"],
        "task_evidence": {"user_skipped_tasks": ["sustain_a", "high_note_sustain_a"]},
    }
    song = {"vocal_function_profile": {"effort_assessment": {"severity": "LOW"}}}
    ev = evaluate_concern("HIGH_NOTE_TOO_EFFORTFUL", song_profile=song, task_evidence=fused)
    assert ev["status"] != "CONFIRMED"


def test_concern_only_uses_song_evidence_only():
    final = build_final_diagnostic_profile(
        song_profile={"dimensions": {}},
        task_results=[],
        plan={
            "selected_tasks": ["sustain_a", "siren"],
            "user_skipped_tasks": ["sustain_a", "siren"],
            "completed_tasks": [],
        },
    )
    assert final.get("evidence_mode") == EVIDENCE_MODE_CONCERN_ONLY
    assert (final.get("task_evidence") or {}).get("task_ids_present") == []


def test_skip_all_does_not_delete_selected_tasks_api(tmp_path, monkeypatch):
    from backend.app.diagnostic.service import DiagnosticSessionService

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    svc = DiagnosticSessionService(runtime)
    # Bypass entitlements
    class _Ent:
        def has_session_unlock(self, *a, **k):
            return True

    svc.entitlements = _Ent()
    sid = "a" * 32
    sess_dir = runtime / "diagnostic_sessions" / sid
    sess_dir.mkdir(parents=True)
    session = {
        "session_id": sid,
        "user_id": "demo-user",
        "status": "TASKS_IN_PROGRESS",
        "selected_tasks": ["sustain_a", "siren", "high_note_sustain_a"],
        "tasks": {
            "sustain_a": {"attempts": [], "passed": False},
            "siren": {"attempts": [], "passed": False},
            "high_note_sustain_a": {"attempts": [], "passed": False},
        },
        "task_results": [],
        "diagnostic_status": "NORMAL",
        "diagnostic_mode": "CONCERN_FOCUSED",
        "user_concerns": [{"id": "HIGH_NOTE_TOO_EFFORTFUL"}],
    }
    (sess_dir / "session.json").write_text(json.dumps(session), encoding="utf-8")
    out = svc.skip_controlled_recordings(sid, user_id="demo-user")
    assert out["selected_tasks"] == ["sustain_a", "siren", "high_note_sustain_a"]
    assert out["status"] == "READY_FOR_ANALYSIS"
    assert out["evidence_mode"] == EVIDENCE_MODE_CONCERN_ONLY
    assert set(out["user_skipped_tasks"]) == set(out["selected_tasks"])
    # no fake results
    reloaded = json.loads((sess_dir / "session.json").read_text(encoding="utf-8"))
    assert reloaded.get("task_results") == []


def test_skip_single_task_persists_and_advances(tmp_path):
    from backend.app.diagnostic.service import DiagnosticSessionService

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    svc = DiagnosticSessionService(runtime)

    class _Ent:
        def has_session_unlock(self, *a, **k):
            return True

    svc.entitlements = _Ent()
    sid = "b" * 32
    sess_dir = runtime / "diagnostic_sessions" / sid
    sess_dir.mkdir(parents=True)
    session = {
        "session_id": sid,
        "user_id": "demo-user",
        "status": "TASKS_IN_PROGRESS",
        "selected_tasks": ["sustain_a", "sustain_i", "siren"],
        "tasks": {
            "sustain_a": {"attempts": [], "passed": False},
            "sustain_i": {"attempts": [], "passed": False},
            "siren": {"attempts": [], "passed": False},
        },
        "task_results": [],
        "current_task_index": 0,
        "diagnostic_status": "NORMAL",
    }
    (sess_dir / "session.json").write_text(json.dumps(session), encoding="utf-8")
    out = svc.skip_task(sid, "sustain_a", user_id="demo-user")
    assert out["next_task_id"] == "sustain_i"
    assert out["tasks"]["sustain_a"]["skipped"] is True
    reloaded = json.loads((sess_dir / "session.json").read_text(encoding="utf-8"))
    assert reloaded["tasks"]["sustain_a"]["skipped"] is True
    assert reloaded.get("task_results") == []


def test_skip_task_does_not_create_task_result(tmp_path):
    from backend.app.diagnostic.service import DiagnosticSessionService

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    svc = DiagnosticSessionService(runtime)

    class _Ent:
        def has_session_unlock(self, *a, **k):
            return True

    svc.entitlements = _Ent()
    sid = "c" * 32
    sess_dir = runtime / "diagnostic_sessions" / sid
    sess_dir.mkdir(parents=True)
    session = {
        "session_id": sid,
        "user_id": "demo-user",
        "status": "TASKS_IN_PROGRESS",
        "selected_tasks": ["sustain_a"],
        "tasks": {"sustain_a": {"attempts": [], "passed": False}},
        "task_results": [],
        "diagnostic_status": "NORMAL",
    }
    (sess_dir / "session.json").write_text(json.dumps(session), encoding="utf-8")
    svc.skip_task(sid, "sustain_a", user_id="demo-user")
    reloaded = json.loads((sess_dir / "session.json").read_text(encoding="utf-8"))
    assert reloaded["task_results"] == []
    assert reloaded["status"] == "READY_FOR_ANALYSIS"


def test_partial_after_some_completed_then_skip_rest(tmp_path):
    from backend.app.diagnostic.service import DiagnosticSessionService

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    svc = DiagnosticSessionService(runtime)

    class _Ent:
        def has_session_unlock(self, *a, **k):
            return True

    svc.entitlements = _Ent()
    sid = "d" * 32
    sess_dir = runtime / "diagnostic_sessions" / sid
    sess_dir.mkdir(parents=True)
    session = {
        "session_id": sid,
        "user_id": "demo-user",
        "status": "TASKS_IN_PROGRESS",
        "selected_tasks": ["sustain_a", "siren", "high_note_sustain_a"],
        "tasks": {
            "sustain_a": {"attempts": [{"passed": True}], "passed": True},
            "siren": {"attempts": [], "passed": False},
            "high_note_sustain_a": {"attempts": [], "passed": False},
        },
        "task_results": [{"task_id": "sustain_a", "valid": True}],
        "diagnostic_status": "NORMAL",
    }
    (sess_dir / "session.json").write_text(json.dumps(session), encoding="utf-8")
    out = svc.skip_controlled_recordings(sid, user_id="demo-user", remaining_only=True)
    assert out["evidence_mode"] == EVIDENCE_MODE_PARTIAL
    assert "sustain_a" in out["completed_tasks"]
    assert set(out["user_skipped_tasks"]) == {"siren", "high_note_sustain_a"}
    assert out["selected_tasks"] == ["sustain_a", "siren", "high_note_sustain_a"]
    assert out["status"] == "READY_FOR_ANALYSIS"


def test_song_grounded_strength_survives_task_skip():
    """Song-based strengths may still appear; controlled-only must not."""
    fused = {
        "task_profiles": {},
        "controlled_contrasts": {},
        "user_skipped_tasks": ["high_note_sustain_a", "siren"],
        "task_evidence": {"user_skipped_tasks": ["high_note_sustain_a", "siren"]},
        "dimensions": {},
    }
    song = {
        "vocal_function_profile": {
            "effort_assessment": {"severity": "LOW"},
            "breathiness": {"level": "LOW"},
        }
    }
    strengths = derive_precision_strengths(
        concern_evaluations=[], fused_profile=fused, song_profile=song
    )
    assert not any("HIGH_NOTE" in s["id"] for s in strengths)
    assert not any("REGISTER" in s["id"] for s in strengths)
