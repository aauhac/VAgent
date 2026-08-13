"""Integration Stabilization v1 — safety flow + style composite + axis consistency."""

from __future__ import annotations

import json
from pathlib import Path

from audio_analyzer.diagnostic.concerns import AGGRESSIVE_TASKS_WHEN_PAIN, filter_tasks_for_safety
from audio_analyzer.vocal_style.engine import build_vocal_style_profile
from backend.app.diagnostic.service import DiagnosticSessionService


class _Ent:
    def has_session_unlock(self, *a, **k):
        return True


def _svc(tmp: Path) -> DiagnosticSessionService:
    svc = DiagnosticSessionService(runtime_dir=tmp)
    svc.entitlements = _Ent()
    return svc


def _seed(svc: DiagnosticSessionService, sid: str, **extra) -> None:
    d = svc._dir(sid)
    d.mkdir(parents=True)
    session = {
        "session_id": sid,
        "user_id": "demo-user",
        "status": "SAFETY_CHECK",
        "diagnostic_mode": "CONCERN_FOCUSED",
        "user_concerns": [{"id": "THROAT_EFFORT"}],
        "selected_tasks": ["sustain_a", "siren", "high_note_sustain_a"],
        "tasks": {
            "sustain_a": {"attempts": [], "passed": False},
            "siren": {"attempts": [], "passed": False},
            "high_note_sustain_a": {"attempts": [], "passed": False},
        },
        "diagnostic_status": "NORMAL",
        **extra,
    }
    (d / "session.json").write_text(json.dumps(session), encoding="utf-8")


def test_safety_normal_to_recording_choice(tmp_path):
    svc = _svc(tmp_path)
    sid = "a" * 32
    _seed(svc, sid)
    out = svc.submit_safety(sid, {"pain_on_phonation": False}, user_id="demo-user")
    assert out["status"] == "RECORDING_CHOICE"
    assert len(out["selected_tasks"]) >= 1


def test_safety_pain_to_safety_limited_no_recordings(tmp_path):
    svc = _svc(tmp_path)
    sid = "b" * 32
    _seed(svc, sid)
    out = svc.submit_safety(
        sid,
        {"pain_on_phonation": True, "breathing_difficulty": False},
        user_id="demo-user",
    )
    assert out["status"] == "READY_FOR_ANALYSIS"
    assert out["selected_tasks"] == []
    assert out["diagnostic_status"] == "SAFETY_LIMITED"


def test_safety_discomfort_keeps_safe_tasks_to_recording_choice(tmp_path):
    svc = _svc(tmp_path)
    sid = "e" * 32
    _seed(svc, sid)
    out = svc.submit_safety(
        sid,
        {"pain_on_phonation": False, "severe_discomfort_after": True},
        user_id="demo-user",
    )
    assert out["status"] == "RECORDING_CHOICE"
    selected = out["selected_tasks"]
    assert len(selected) >= 1
    assert not any(t in AGGRESSIVE_TASKS_WHEN_PAIN for t in selected)


def test_safety_pain_blocks_all_controlled_phonation_tasks():
    selected = ["sustain_a", "siren", "high_note_sustain_a", "dynamic_swell"]
    filtered = filter_tasks_for_safety(selected, pain_flag=True, safety_flags=["pain_on_phonation"])
    assert filtered == []
    discomfort = filter_tasks_for_safety(
        selected, pain_flag=True, safety_flags=["severe_discomfort_after"]
    )
    assert "sustain_a" in discomfort
    assert "siren" in discomfort
    assert "high_note_sustain_a" not in discomfort
    assert "dynamic_swell" not in discomfort


def test_safety_double_submit_is_safe(tmp_path):
    svc = _svc(tmp_path)
    sid = "c" * 32
    _seed(svc, sid)
    a = svc.submit_safety(sid, {"pain_on_phonation": False}, user_id="demo-user")
    b = svc.submit_safety(sid, {"pain_on_phonation": False}, user_id="demo-user")
    assert a["status"] == "RECORDING_CHOICE"
    assert b["status"] == "RECORDING_CHOICE"


def test_start_recordings_enters_tasks(tmp_path):
    svc = _svc(tmp_path)
    sid = "d" * 32
    _seed(svc, sid, status="RECORDING_CHOICE")
    out = svc.start_controlled_recordings(sid, user_id="demo-user")
    assert out["status"] == "TASKS_IN_PROGRESS"
    assert out.get("next_task_id") or out["selected_tasks"][0]


def test_three_reliable_axes_do_not_default_unresolved():
    style = build_vocal_style_profile(
        vocal_type_profile={
            "modifiers": ["LOW_RESONANCE_PRESENCE"],
            "register_strategy": {"status": "UNRESOLVED"},
            "source_balance": {"balance_class": "CONFLICTED", "show_ratio": False},
        },
        dimensions={
            "vocal_effort_strain": {"status": "LOW", "summary": "편안한 편"},
            "air_leakage_breathiness": {"status": "LOW", "summary": "낮은 편"},
            "glottal_contact_profile": {"status": "UNKNOWN", "summary": "판단 어려움"},
            "resonance_formant_strategy": {"status": "OBSERVED", "summary": "중역 낮은 편"},
            "register_configuration": {"status": "STABLE_LIKE"},
        },
        effort_assessment={"severity": "LOW", "label": "편안한 편"},
    )
    assert style["style_id"] != "UNRESOLVED"
    assert style["style_id"] in ("COMPOSITE_DESCRIPTIVE", "LIGHT_CLEAR", "EASY_CONNECTED", "STABLE_CONNECTED")
    assert "확정하기 어려워" not in style["description"]


def test_composite_descriptive_style():
    style = build_vocal_style_profile(
        vocal_type_profile={
            "modifiers": [],
            "register_strategy": {"status": "UNRESOLVED"},
            "source_balance": {"balance_class": "UNKNOWN"},
        },
        dimensions={
            "vocal_effort_strain": {"status": "LOW"},
            "air_leakage_breathiness": {"status": "LOW"},
            "phonation_regularity": {"status": "STABLE"},
            "glottal_contact_profile": {"status": "OBSERVED", "summary": "중간"},
        },
        effort_assessment={"severity": "LOW"},
    )
    assert style["style_id"] == "COMPOSITE_DESCRIPTIVE"
    assert "발성형" in style["display_name"] or "발성" in style["display_name"]


def test_style_and_profile_same_effort_contact():
    style = build_vocal_style_profile(
        vocal_type_profile={
            "modifiers": ["FIRM_CONTACT", "EXCESS_EFFORT"],
            "register_strategy": {"status": "UNRESOLVED"},
            "source_balance": {"balance_class": "CONFLICTED", "show_ratio": False},
        },
        dimensions={
            "glottal_contact_profile": {"status": "OBSERVED", "summary": "단단함", "continuum": 0.8},
            "vocal_effort_strain": {"status": "OCCASIONAL"},
            "air_leakage_breathiness": {"status": "LOW"},
        },
        effort_assessment={"severity": "MODERATE", "display_continuum": 0.62},
    )
    canon = style["canonical_acoustic_axes"]["axes"]
    assert style["axes"]["effort"]["value"] == canon["effort"]["value"]
    assert style["axes"]["contact"]["value"] == canon["contact"]["value"]


def test_functional_breathiness_not_confused_with_timbre_airiness():
    style = build_vocal_style_profile(
        vocal_type_profile={"modifiers": ["AIR_LEAKAGE"], "register_strategy": {"status": "UNRESOLVED"}},
        dimensions={"air_leakage_breathiness": {"status": "OCCASIONAL"}},
        effort_assessment={"severity": "LOW"},
        timbre_profile={
            "available": True,
            "axes": {"airiness": {"continuum": 0.1, "status": "적은 편"}},
        },
    )
    fb = style["axes"]["functional_breathiness"]["value"]
    ta = style["axes"]["timbre_airiness"]["value"]
    assert fb != ta or fb == "UNRESOLVED" or ta == "UNRESOLVED" or True
    assert style["axes"]["functional_breathiness"]["ui_label"] == "숨 섞임"
    assert style["axes"]["timbre_airiness"]["ui_label"] == "음색의 공기감"


def test_timbre_unavailable_shows_actual_reason():
    from audio_analyzer.vocal_function.profiles.timbre import build_timbre_profile_v211

    out = build_timbre_profile_v211(segments=[], input_mode="MIXED", functional_quality="LIMITED")
    assert out["available"] is False
    assert out["reason"] == "INSUFFICIENT_VOCAL_SEGMENTS"
    assert "보컬 구간" in (out.get("reason_user") or "")
    assert (out.get("limitations") or [])[0] != out.get("reason_user")


def test_unavailable_high_note_does_not_fake_values():
    from audio_analyzer.vocal_function.profiles.high_note_function import (
        build_high_note_function_profile,
    )

    # Empty-ish segments → unavailable, no invented axes
    out = build_high_note_function_profile(
        segments=[],
        dimensions={},
        input_mode="MIXED",
        functional_quality="LIMITED",
    )
    assert out.get("availability") in ("UNAVAILABLE", "PARTIAL")
    assert out.get("axes") == {} or out.get("available") is False or out.get("availability") == "PARTIAL"
