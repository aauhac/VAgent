"""Precision Diagnostic v2.1 — product distinction, modes, core recording invariant."""

from __future__ import annotations

from audio_analyzer.diagnostic.concerns import (
    build_personalized_qa,
    normalize_diagnostic_mode,
    normalize_user_concerns,
)
from audio_analyzer.diagnostic.planner import (
    build_uncertainty_profile,
    explain_task_selection,
    plan_precision_protocol,
    select_diagnostic_tasks,
)
from audio_analyzer.diagnostic.task_registry import PRECISION_CORE_GENERAL


def _resolved_profile():
    matrix = [
        {
            "dimension_id": d,
            "measurement_sufficiency": "SUFFICIENT",
            "confidence_label": "high",
            "finding": "NOT_PROMINENT",
            "required_satisfied": 2,
            "required_total": 2,
            "criteria": [],
            "coaching_eligibility": "ELIGIBLE",
        }
        for d in (
            "glottal_contact_profile",
            "air_leakage_breathiness",
            "vocal_effort_strain",
            "register_configuration",
            "phonation_regularity",
            "resonance_formant_strategy",
            "onset_offset_coordination",
            "respiratory_phonatory_coordination",
        )
    ]
    return build_uncertainty_profile(criteria_matrix=matrix)


def test_detail_report_requires_no_new_recording():
    """Detail is song-only; provisional offer is not a Precision protocol."""
    profile = _resolved_profile()
    provisional = select_diagnostic_tasks(profile)
    assert provisional["selected_tasks"] == []
    # Song offer never claims precision recording is skipped
    offer = explain_task_selection(provisional)["diagnostic_offer"]
    assert offer["required"] is True
    assert offer["precision_requires_recording"] is True


def test_precision_general_mode_requires_controlled_recording():
    plan = plan_precision_protocol(_resolved_profile(), diagnostic_mode="GENERAL_DISCOVERY")
    assert plan["diagnostic_mode"] == "GENERAL_DISCOVERY"
    assert len(plan["selected_tasks"]) >= 1
    assert set(PRECISION_CORE_GENERAL).issubset(set(plan["core_tasks"]) | set(plan["selected_tasks"]))


def test_precision_concern_mode_requires_controlled_recording():
    plan = plan_precision_protocol(
        _resolved_profile(),
        diagnostic_mode="CONCERN_FOCUSED",
        user_concerns=[{"id": "HIGH_NOTE_CANNOT_REACH"}, {"id": "THROAT_EFFORT"}],
    )
    assert plan["diagnostic_mode"] == "CONCERN_FOCUSED"
    assert len(plan["selected_tasks"]) >= 1


def test_precision_normal_flow_never_finishes_with_zero_tasks():
    for mode, concerns in (
        ("GENERAL_DISCOVERY", []),
        ("CONCERN_FOCUSED", [{"id": "TIMBRE_DISSATISFIED"}]),
    ):
        plan = plan_precision_protocol(
            _resolved_profile(),
            diagnostic_mode=mode,
            user_concerns=concerns,
        )
        assert len(plan["selected_tasks"]) >= 1, mode
        assert plan["diagnostic_status"] != "SAFETY_LIMITED" or plan["selected_tasks"]


def test_precision_pain_on_phonation_blocks_all_controlled_tasks():
    """Explicit pain_on_phonation → no controlled phonation (incl. siren)."""
    plan = plan_precision_protocol(
        _resolved_profile(),
        diagnostic_mode="CONCERN_FOCUSED",
        user_concerns=[{"id": "THROAT_EFFORT"}],
        pain_safety_flag=True,
        safety_flags=["pain_on_phonation"],
    )
    assert plan["selected_tasks"] == []
    assert plan["diagnostic_status"] == "SAFETY_LIMITED"


def test_precision_discomfort_keeps_safe_tasks_not_wipe_all():
    """severe_discomfort_after blocks only AGGRESSIVE tasks."""
    plan = plan_precision_protocol(
        _resolved_profile(),
        diagnostic_mode="CONCERN_FOCUSED",
        user_concerns=[{"id": "VOCAL_FATIGUE"}],
        pain_safety_flag=True,
        safety_flags=["severe_discomfort_after"],
    )
    assert len(plan["selected_tasks"]) >= 1
    assert "high_note_sustain_a" not in plan["selected_tasks"]
    assert "dynamic_swell" not in plan["selected_tasks"]
    assert plan["diagnostic_status"] == "NORMAL"


def test_safety_limited_only_when_no_safe_tasks_remain():
    from audio_analyzer.diagnostic.concerns import filter_tasks_for_safety

    only_aggressive = ["high_note_sustain_a", "dynamic_swell"]
    filtered = filter_tasks_for_safety(
        only_aggressive, pain_flag=True, safety_flags=["pain_on_phonation"]
    )
    assert filtered == []


def test_song_only_sufficiency_does_not_skip_precision_recording():
    provisional = select_diagnostic_tasks(_resolved_profile())
    assert provisional["selected_tasks"] == []
    precision = plan_precision_protocol(_resolved_profile(), diagnostic_mode="GENERAL_DISCOVERY")
    assert len(precision["selected_tasks"]) >= 1


def test_no_concern_option_creates_general_discovery_mode():
    assert normalize_diagnostic_mode("GENERAL_DISCOVERY", []) == "GENERAL_DISCOVERY"
    assert normalize_diagnostic_mode(None, []) == "GENERAL_DISCOVERY"


def test_general_discovery_has_empty_user_concerns():
    plan = plan_precision_protocol(
        _resolved_profile(),
        diagnostic_mode="GENERAL_DISCOVERY",
        user_concerns=[{"id": "THROAT_EFFORT"}],  # ignored in general mode
    )
    assert plan["diagnostic_mode"] == "GENERAL_DISCOVERY"
    assert plan["rationale"]["user_concern_ids"] == []


def test_general_discovery_gets_core_tasks():
    plan = plan_precision_protocol(_resolved_profile(), diagnostic_mode="GENERAL_DISCOVERY")
    assert plan["core_tasks"] == list(PRECISION_CORE_GENERAL)
    assert plan["planned_task_count"] >= 2


def test_general_discovery_report_has_no_fake_qna():
    qa = build_personalized_qa(
        user_concerns=[],
        song_profile={},
        diagnostic_mode="GENERAL_DISCOVERY",
    )
    assert qa["show_qa_section"] is False
    assert qa["questions"] == []
    assert qa.get("question") is None


def test_general_discovery_report_shows_discovered_characteristics():
    qa = build_personalized_qa(
        user_concerns=[],
        song_profile={},
        diagnostic_mode="GENERAL_DISCOVERY",
    )
    assert qa["discovered_features"]
    assert "정밀" not in (qa.get("question") or "")


def test_concern_mode_requires_one_to_three_concerns():
    mode = normalize_diagnostic_mode("CONCERN_FOCUSED", [{"id": "THROAT_EFFORT"}])
    assert mode == "CONCERN_FOCUSED"
    many = normalize_user_concerns(
        [
            {"id": "THROAT_EFFORT"},
            {"id": "HIGH_NOTE_CANNOT_REACH"},
            {"id": "VOICE_TOO_BREATHY"},
            {"id": "PITCH_UNSTABLE"},
            {"id": "TIMBRE_DISSATISFIED"},
        ]
    )
    assert len(many) == 3


def test_concern_mode_replans_tasks():
    plan = plan_precision_protocol(
        _resolved_profile(),
        diagnostic_mode="CONCERN_FOCUSED",
        user_concerns=[{"id": "HIGH_NOTE_CANNOT_REACH"}, {"id": "THROAT_EFFORT"}],
    )
    assert "sustain_a" in plan["selected_tasks"]
    assert "high_note_sustain_a" in plan["selected_tasks"] or "siren" in plan["selected_tasks"]
    assert plan["core_tasks"]
    assert "adaptive_tasks" in plan


def test_concern_mode_generates_concern_qna():
    qa = build_personalized_qa(
        user_concerns=[{"id": "THROAT_EFFORT"}],
        song_profile={"vocal_function_profile": {"effort_assessment": {"severity": "MODERATE"}}},
        diagnostic_mode="CONCERN_FOCUSED",
    )
    assert qa["show_qa_section"] is True
    assert qa["questions"]
    assert "목에 힘" in qa["questions"][0]["question"]


def test_multiple_concerns_generate_separate_questions():
    qa = build_personalized_qa(
        user_concerns=[{"id": "HIGH_NOTE_CANNOT_REACH"}, {"id": "THROAT_EFFORT"}],
        song_profile={"vocal_function_profile": {"effort_assessment": {"severity": "MODERATE"}}},
        diagnostic_mode="CONCERN_FOCUSED",
    )
    assert len(qa["questions"]) == 2
    qs = " ".join(q["question"] for q in qa["questions"])
    assert "고음" in qs and "목에 힘" in qs
    assert "들어가을까요" not in qs


def test_concern_answer_requires_evidence():
    low = build_personalized_qa(
        user_concerns=[{"id": "THROAT_EFFORT"}],
        song_profile={"vocal_function_profile": {"effort_assessment": {"severity": "LOW"}}},
    )
    high = build_personalized_qa(
        user_concerns=[{"id": "THROAT_EFFORT"}],
        song_profile={"vocal_function_profile": {"effort_assessment": {"severity": "HIGH"}}},
    )
    assert low["questions"][0]["answer"] != high["questions"][0]["answer"]
