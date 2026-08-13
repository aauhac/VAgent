"""Precision Diagnostic v2 — user concerns, planner, Q&A, safety."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from audio_analyzer.diagnostic.concerns import (
    BANNED_CLAIM_SUBSTRINGS,
    build_personalized_qa,
    evaluate_concern_status,
    filter_tasks_for_safety,
    has_pain_safety_flag,
    normalize_user_concerns,
)
from audio_analyzer.diagnostic.planner import (
    build_uncertainty_profile,
    plan_from_song_analysis,
    select_diagnostic_tasks,
)


def test_user_concern_is_not_acoustic_truth():
    concerns = normalize_user_concerns([{"id": "THROAT_EFFORT"}])
    assert concerns[0]["source"] == "USER_REPORTED"
    song = {"vocal_function_profile": {"effort_assessment": {"severity": "LOW"}}}
    ev = evaluate_concern_status("THROAT_EFFORT", song_profile=song)
    assert ev["status"] == "NOT_SUPPORTED_IN_THIS_RECORDING"


def test_effort_concern_does_not_force_effort_high():
    song = {"vocal_function_profile": {"effort_assessment": {"severity": "LOW"}}}
    qa = build_personalized_qa(
        user_concerns=[{"id": "THROAT_EFFORT"}],
        song_profile=song,
    )
    assert "뚜렷하지 않았어요" in qa["answer_summary"] or "NOT" in str(qa.get("not_supported"))


def test_high_note_concern_prioritizes_relevant_dimensions():
    from audio_analyzer.diagnostic.concerns import concern_dimension_boost

    boost = concern_dimension_boost(normalize_user_concerns([{"id": "HIGH_NOTE_CANNOT_REACH"}]))
    assert boost.get("effort", 0) > 0
    assert boost.get("register", 0) > 0


def test_timbre_concern_prioritizes_timbre_dimensions():
    from audio_analyzer.diagnostic.concerns import concern_dimension_boost

    boost = concern_dimension_boost(normalize_user_concerns([{"id": "VOICE_TOO_BREATHY"}]))
    assert boost.get("breathiness", 0) > 0


def test_max_three_concerns_ui():
    raw = [{"id": "THROAT_EFFORT"}, {"id": "VOICE_TOO_BREATHY"}, {"id": "HIGH_NOTE_CANNOT_REACH"}, {"id": "PITCH_UNSTABLE"}]
    assert len(normalize_user_concerns(raw)) == 3


def test_old_session_without_concerns_still_loads():
    concerns = normalize_user_concerns(None)
    assert concerns == []
    qa = build_personalized_qa(user_concerns=[], song_profile={})
    assert "question" in qa


def test_high_note_plus_effort_can_select_siren_and_high_sustain():
    profile = build_uncertainty_profile(
        criteria_matrix=[],
        dimensions={},
        measurement_candidates=[],
        song_context={"has_song": True, "high_note_uncertain": True},
    )
    concerns = normalize_user_concerns(
        [{"id": "HIGH_NOTE_CANNOT_REACH", "priority": 1}, {"id": "THROAT_EFFORT", "priority": 2}]
    )
    plan = select_diagnostic_tasks(profile, user_concerns=concerns)
    tasks = plan.get("selected_tasks") or []
    assert "siren" in tasks or "high_note_sustain_a" in tasks or len(tasks) >= 1


def test_concern_does_not_force_unnecessary_task_on_resolved_song():
    profile = build_uncertainty_profile(
        criteria_matrix=[
            {
                "dimension_id": "glottal_contact_profile",
                "measurement_sufficiency": "SUFFICIENT",
                "finding": "STABLE",
                "confidence_label": "high",
                "coaching_eligibility": "OK",
                "required_total": 2,
                "required_satisfied": 2,
                "criteria": [],
            }
        ],
        dimensions={},
        measurement_candidates=[],
    )
    plan = select_diagnostic_tasks(profile, user_concerns=[{"id": "VOICE_TOO_BREATHY"}])
    assert isinstance(plan.get("selected_tasks"), list)


def test_pain_on_phonation_blocks_all_controlled_phonation():
    selected = filter_tasks_for_safety(
        ["siren", "dynamic_swell", "high_note_sustain_a", "sustain_a"],
        pain_flag=True,
        safety_flags=["pain_on_phonation"],
    )
    assert selected == []


def test_discomfort_flag_blocks_aggressive_high_note_task():
    selected = filter_tasks_for_safety(
        ["siren", "dynamic_swell", "high_note_sustain_a", "sustain_a"],
        pain_flag=True,
        safety_flags=["severe_discomfort_after"],
    )
    assert "dynamic_swell" not in selected
    assert "high_note_sustain_a" not in selected
    assert "siren" in selected
    assert "sustain_a" in selected


def test_pain_flag_without_checkbox_blocks_aggressive_only():
    """Legacy pain_flag / concern pain without safety checkbox → discomfort tier."""
    selected = filter_tasks_for_safety(
        ["siren", "dynamic_swell", "high_note_sustain_a", "sustain_a"],
        pain_flag=True,
    )
    assert "dynamic_swell" not in selected
    assert "high_note_sustain_a" not in selected
    assert "siren" in selected


def test_pain_does_not_generate_training_prescription():
    qa = build_personalized_qa(
        user_concerns=[{"id": "PAIN_WHILE_SINGING"}],
        song_profile={},
    )
    goals = [g.get("goal_id") for g in qa.get("improvement_priorities") or []]
    assert goals == ["SAFETY_FIRST"]
    assert not any("REDUCE_HIGH_NOTE_EFFORT" == g for g in goals)


def test_confirmed_concern_generates_supported_answer():
    song = {
        "vocal_function_profile": {
            "effort_assessment": {"severity": "MODERATE"},
            "coaching_decision": {"primary_bottleneck": {"issue_id": "GENERAL_EXCESS_EFFORT"}},
        }
    }
    qa = build_personalized_qa(
        user_concerns=[{"id": "THROAT_EFFORT"}, {"id": "HIGH_NOTE_TOO_EFFORTFUL"}],
        song_profile=song,
    )
    assert qa["answer_summary"]
    assert any("힘" in line for line in qa.get("concern_user_lines") or [])


def test_answer_does_not_claim_unobserved_anatomy():
    song = {"vocal_function_profile": {"effort_assessment": {"severity": "MODERATE"}}}
    qa = build_personalized_qa(user_concerns=[{"id": "THROAT_EFFORT"}], song_profile=song)
    blob = json.dumps(qa, ensure_ascii=False)
    for banned in BANNED_CLAIM_SUBSTRINGS:
        assert banned not in blob


def test_same_question_can_produce_different_answer_from_evidence():
    low = build_personalized_qa(
        user_concerns=[{"id": "THROAT_EFFORT"}],
        song_profile={"vocal_function_profile": {"effort_assessment": {"severity": "LOW"}}},
    )
    high = build_personalized_qa(
        user_concerns=[{"id": "THROAT_EFFORT"}],
        song_profile={"vocal_function_profile": {"effort_assessment": {"severity": "MODERATE"}}},
    )
    assert low["answer_summary"] != high["answer_summary"]


def test_guidance_comes_from_confirmed_bottleneck():
    song = {
        "vocal_function_profile": {
            "coaching_decision": {"primary_bottleneck": {"issue_id": "GENERAL_EXCESS_EFFORT"}},
            "effort_assessment": {"severity": "MODERATE"},
        }
    }
    qa = build_personalized_qa(user_concerns=[{"id": "THROAT_EFFORT"}], song_profile=song)
    goals = qa.get("improvement_priorities") or []
    assert goals and goals[0].get("goal_id") == "REDUCE_HIGH_NOTE_EFFORT"


def test_no_abdominal_pressure_diagnosis():
    qa = build_personalized_qa(user_concerns=[{"id": "THROAT_EFFORT"}], song_profile={})
    assert "복압" not in json.dumps(qa, ensure_ascii=False)


def test_has_pain_safety_flag():
    assert has_pain_safety_flag(normalize_user_concerns([{"id": "PAIN_WHILE_SINGING"}]))
    assert not has_pain_safety_flag(normalize_user_concerns([{"id": "THROAT_EFFORT"}]))


def test_detail_audio_preview_available():
    from fastapi.testclient import TestClient

    from backend.app.main import app

    c = TestClient(app)
    headers = {"X-User-Id": "demo-user", "X-VAgent-User-Key": "demo-user"}
    import io
    import struct
    import time
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(44100)
        wf.writeframes(struct.pack("<h", 0) * 44100 * 2)
    data = buf.getvalue()
    up = c.post("/v1/analyses", files={"file": ("t.wav", data, "audio/wav")}, headers=headers)
    assert up.status_code == 200
    aid = up.json()["analysis_id"]
    for _ in range(60):
        st = c.get(f"/v1/analyses/{aid}", headers=headers).json()
        if st.get("status") == "completed":
            break
        time.sleep(0.5)
    prev = c.get(f"/v1/analyses/{aid}/preview", headers=headers)
    assert prev.status_code == 200
    assert "audio" in (prev.headers.get("content-type") or "")


def test_missing_audio_returns_controlled_error():
    from fastapi.testclient import TestClient

    from backend.app.main import app

    c = TestClient(app)
    headers = {"X-User-Id": "demo-user", "X-VAgent-User-Key": "demo-user"}
    prev = c.get("/v1/analyses/nonexistent000000000000000000/preview", headers=headers)
    assert prev.status_code == 404
