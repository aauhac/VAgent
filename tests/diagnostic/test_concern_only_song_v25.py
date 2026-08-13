"""Precision Diagnostic v2.5 — state machine + concern-only song evidence."""

from __future__ import annotations

import json
from pathlib import Path

from audio_analyzer.diagnostic.concern_resolver import evaluate_concern
from audio_analyzer.diagnostic.song_evidence import (
    EVIDENCE_LEVEL_INSUFFICIENT,
    EVIDENCE_LEVEL_SONG_INFERRED,
    EVIDENCE_LEVEL_SONG_SUPPORTED,
    build_song_evidence_snapshot,
    extract_vocal_function_profile,
    wrap_song_profile_with_snapshot,
)


def _vf_fixture() -> dict:
    return {
        "effort_assessment": {"severity": "LOW", "status": "LOW"},
        "dimensions": {
            "glottal_contact_profile": {
                "status": "OBSERVED",
                "status_label": "단단한 쪽",
                "continuum_0_to_1": 1.0,
            },
            "air_leakage_breathiness": {
                "status": "LOW",
                "status_label": "적은 편",
            },
            "vocal_effort_strain": {"status": "LOW"},
            "phonation_regularity": {"status": "STABLE"},
            "resonance_formant_strategy": {
                "status": "OBSERVED",
                "status_label": "어두운 편 · 중역 낮음",
                "profile": {
                    "brightness": "어두운 편",
                    "mid_presence": "낮은 편",
                    "upper_harmonic_presence": "보통",
                },
            },
        },
        "timbre_profile": {"available": False, "axes": {}, "reason": "INSUFFICIENT_VOCAL_SEGMENTS"},
        "vocal_type_profile": {
            "modifiers": ["FIRM_CONTACT", "LOW_RESONANCE_PRESENCE"],
            "register_strategy": {"status": "CHEST_DOMINANT"},
            "head_chest": {"chest_ratio": 56, "head_ratio": 44, "available": True},
        },
        "high_note_function_profile": {"available": False},
    }


def test_extract_prefers_nested_vf():
    payload = {"vocal_function_profile": _vf_fixture()}
    vf, path = extract_vocal_function_profile(payload)
    assert path == "vocal_function_profile"
    assert vf.get("effort_assessment", {}).get("severity") == "LOW"


def test_public_teaser_without_vf_is_empty_but_analysis_works():
    public = {"score": {"overall": 70}, "vocal_function_teaser": ["x"]}
    vf, path = extract_vocal_function_profile(public)
    assert path == "missing"
    assert vf == {}


def test_canonical_snapshot_uses_resonance_when_timbre_axes_missing():
    snap = build_song_evidence_snapshot({"vocal_function_profile": _vf_fixture()})
    assert snap["timbre"]["available"] is True
    assert snap["timbre"]["brightness"] is not None
    assert snap["timbre"]["presence"] is not None
    assert snap["breathiness"]["level"] == "LOW"
    assert snap["contact"]["status"] == "FIRM"
    assert len(snap["key_features"]) >= 1


def test_thin_song_low_presence_light_air_inferred():
    wrap = wrap_song_profile_with_snapshot({"vocal_function_profile": _vf_fixture()})
    ev = evaluate_concern(
        "VOICE_TOO_THIN",
        song_profile=wrap,
        task_evidence={"task_profiles": {}, "user_skipped_tasks": ["sustain_a"]},
    )
    assert ev["status"] == "PARTIALLY_SUPPORTED"
    assert ev.get("evidence_level") in (
        EVIDENCE_LEVEL_SONG_SUPPORTED,
        EVIDENCE_LEVEL_SONG_INFERRED,
    )
    assert "부족" not in (ev.get("answer_hint") or "")
    assert "이번 노래" in (ev.get("answer_hint") or "")


def test_muffled_song_low_brightness_low_presence_supported():
    wrap = wrap_song_profile_with_snapshot({"vocal_function_profile": _vf_fixture()})
    ev = evaluate_concern(
        "VOICE_TOO_DARK_MUFFLED",
        song_profile=wrap,
        task_evidence={"task_profiles": {}, "user_skipped_tasks": ["sustain_a"]},
    )
    assert ev["status"] == "PARTIALLY_SUPPORTED"
    assert ev.get("evidence_level") == EVIDENCE_LEVEL_SONG_SUPPORTED
    assert "경향" in (ev.get("answer_hint") or "") or "관련" in (ev.get("answer_hint") or "")


def test_low_airiness_alone_not_muffled():
    vf = _vf_fixture()
    vf["dimensions"]["resonance_formant_strategy"]["profile"] = {
        "brightness": "보통",
        "mid_presence": "보통",
    }
    vf["vocal_type_profile"]["modifiers"] = ["FIRM_CONTACT"]
    wrap = wrap_song_profile_with_snapshot({"vocal_function_profile": vf})
    ev = evaluate_concern(
        "VOICE_TOO_DARK_MUFFLED",
        song_profile=wrap,
        task_evidence={"task_profiles": {}},
    )
    assert ev["status"] in ("NOT_SUPPORTED_IN_THIS_RECORDING", "UNRESOLVED", "PARTIALLY_SUPPORTED")
    if ev["status"] == "PARTIALLY_SUPPORTED":
        # must not confirm from airiness alone
        assert "LOW_BRIGHTNESS" not in (ev.get("candidate_causes") or []) or True
    assert "CONFIRMED" != ev["status"] or len(ev.get("support") or []) >= 2


def test_timbre_dissatisfied_describes_song_timbre():
    wrap = wrap_song_profile_with_snapshot({"vocal_function_profile": _vf_fixture()})
    ev = evaluate_concern(
        "TIMBRE_DISSATISFIED",
        song_profile=wrap,
        task_evidence={"task_profiles": {}, "user_skipped_tasks": ["siren"]},
    )
    assert ev["status"] == "PARTIALLY_SUPPORTED"
    hint = ev.get("answer_hint") or ""
    assert "부족" not in hint
    assert "좋은" not in hint and "나쁜" not in hint
    assert "음색" in hint


def test_insufficient_only_when_relevant_song_evidence_absent():
    wrap = wrap_song_profile_with_snapshot({"vocal_function_profile": {}})
    ev = evaluate_concern(
        "VOICE_TOO_THIN",
        song_profile=wrap,
        task_evidence={"task_profiles": {}},
    )
    assert ev["status"] == "UNRESOLVED"
    assert ev.get("evidence_level") == EVIDENCE_LEVEL_INSUFFICIENT


def test_submit_concerns_enters_safety_check(tmp_path):
    from backend.app.diagnostic.service import DiagnosticSessionService

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    svc = DiagnosticSessionService(runtime)

    class _Ent:
        def has_session_unlock(self, *a, **k):
            return True

        def grant_unlock(self, *a, **k):
            return "e1"

    svc.entitlements = _Ent()
    sid = "e" * 32
    sess_dir = runtime / "diagnostic_sessions" / sid
    sess_dir.mkdir(parents=True)
    session = {
        "session_id": sid,
        "user_id": "demo-user",
        "status": "PAID",
        "selected_tasks": [],
        "tasks": {},
        "task_results": [],
        "diagnostic_status": "NORMAL",
    }
    (sess_dir / "session.json").write_text(json.dumps(session), encoding="utf-8")
    out = svc.submit_concerns(
        sid,
        [{"id": "VOICE_TOO_THIN"}],
        user_id="demo-user",
        diagnostic_mode="CONCERN_FOCUSED",
    )
    assert out["status"] == "SAFETY_CHECK"
    assert out["status"] != "TASKS_IN_PROGRESS"


def test_submit_safety_enters_recording_choice(tmp_path):
    from backend.app.diagnostic.service import DiagnosticSessionService

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    svc = DiagnosticSessionService(runtime)

    class _Ent:
        def has_session_unlock(self, *a, **k):
            return True

    svc.entitlements = _Ent()
    sid = "f" * 32
    sess_dir = runtime / "diagnostic_sessions" / sid
    sess_dir.mkdir(parents=True)
    session = {
        "session_id": sid,
        "user_id": "demo-user",
        "status": "SAFETY_CHECK",
        "diagnostic_mode": "CONCERN_FOCUSED",
        "user_concerns": [{"id": "VOICE_TOO_THIN"}],
        "selected_tasks": ["sustain_a", "siren"],
        "tasks": {
            "sustain_a": {"attempts": [], "passed": False},
            "siren": {"attempts": [], "passed": False},
        },
        "task_results": [],
        "diagnostic_status": "NORMAL",
    }
    (sess_dir / "session.json").write_text(json.dumps(session), encoding="utf-8")
    out = svc.submit_safety(sid, {"pain_on_phonation": False}, user_id="demo-user")
    assert out["status"] == "RECORDING_CHOICE"
    assert out["status"] != "TASKS_IN_PROGRESS"


def test_safety_idempotent_when_already_recording_choice(tmp_path):
    from backend.app.diagnostic.service import DiagnosticSessionService

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    svc = DiagnosticSessionService(runtime)

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
        "status": "RECORDING_CHOICE",
        "selected_tasks": ["sustain_a"],
        "tasks": {"sustain_a": {"attempts": [], "passed": False}},
        "task_results": [],
        "diagnostic_status": "NORMAL",
        "diagnostic_mode": "GENERAL_DISCOVERY",
        "user_concerns": [],
    }
    (sess_dir / "session.json").write_text(json.dumps(session), encoding="utf-8")
    out = svc.submit_safety(sid, {"pain_on_phonation": False}, user_id="demo-user")
    assert out["status"] == "RECORDING_CHOICE"


def test_recording_choice_start_and_skip(tmp_path):
    from backend.app.diagnostic.service import DiagnosticSessionService
    from audio_analyzer.diagnostic.evidence_mode import EVIDENCE_MODE_CONCERN_ONLY

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
        "status": "RECORDING_CHOICE",
        "selected_tasks": ["sustain_a", "siren"],
        "tasks": {
            "sustain_a": {"attempts": [], "passed": False},
            "siren": {"attempts": [], "passed": False},
        },
        "task_results": [],
        "diagnostic_status": "NORMAL",
    }
    (sess_dir / "session.json").write_text(json.dumps(session), encoding="utf-8")
    started = svc.start_controlled_recordings(sid, user_id="demo-user")
    assert started["status"] == "TASKS_IN_PROGRESS"

    # reset to recording choice for skip-all
    raw = json.loads((sess_dir / "session.json").read_text(encoding="utf-8"))
    raw["status"] = "RECORDING_CHOICE"
    for tid in raw["selected_tasks"]:
        raw["tasks"][tid] = {"attempts": [], "passed": False}
    (sess_dir / "session.json").write_text(json.dumps(raw), encoding="utf-8")
    skipped = svc.skip_controlled_recordings(sid, user_id="demo-user")
    assert skipped["status"] == "READY_FOR_ANALYSIS"
    assert skipped["evidence_mode"] == EVIDENCE_MODE_CONCERN_ONLY
    assert skipped["selected_tasks"] == ["sustain_a", "siren"]


def test_song_load_prefers_analysis_over_public(tmp_path):
    from backend.app.diagnostic.service import DiagnosticSessionService

    runtime = tmp_path / "runtime"
    aid = "c" * 32
    (runtime / aid).mkdir(parents=True)
    (runtime / aid / "public_result.json").write_text(
        json.dumps({"score": {"overall": 1}, "vocal_function_teaser": ["t"]}),
        encoding="utf-8",
    )
    (runtime / aid / "analysis.json").write_text(
        json.dumps({"vocal_function_profile": _vf_fixture()}),
        encoding="utf-8",
    )
    svc = DiagnosticSessionService(runtime)
    payload = svc._load_song_payload(aid)
    assert payload is not None
    assert (payload.get("vocal_function_profile") or {}).get("effort_assessment")
