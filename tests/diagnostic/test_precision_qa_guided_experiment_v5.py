"""Precision QA Guided Experiment v5 — no epistemic meta, explicit A/B, consensus."""

from __future__ import annotations

from audio_analyzer.diagnostic.concern_resolver import evaluate_concern
from audio_analyzer.diagnostic.concerns import build_personalized_qa
from audio_analyzer.diagnostic.comparison_guidance import build_comparison_protocol
from audio_analyzer.diagnostic.goal_planner import plan_coaching_goal
from audio_analyzer.diagnostic.report_versions import QA_GUIDANCE_VERSION, REPORT_LOGIC_VERSION

EPISTEMIC = (
    "직접 확정할 음향 지표는 제한적이에요",
    "뚜렷한 음향 특징이 강하지 않아요",
    "한 원인으로 단정하지는 않아요",
    "특정 원인을 가정하기보다는",
    "하나로 좁히기 어려워요",
    "충분히 비교되지 않았어요",
    "판단하기 어려워요",
    "확인하기 어려워요",
)

UNDEFINED_TWO_WAYS = (
    "두 가지 방식으로 짧게 비교",
    "두 가지 방식으로 비교해보세요",
    "두 가지 방식으로 비교하세요",
)


def _song(
    *,
    effort="LOW",
    contact="FIRM",
    register="PARTIAL",
    presence=0.72,
    breath="LOW",
    stability="STABLE",
    high_note_available=False,
):
    cont = {"FIRM": 0.72, "LIGHT": 0.28, "MID": 0.5}.get(contact, 0.5)
    return {
        "vocal_function_profile": {
            "effort_assessment": {"severity": effort},
            "dimensions": {
                "vocal_effort_strain": {"status": effort},
                "glottal_contact_profile": {
                    "status": "OBSERVED",
                    "continuum_0_to_1": cont,
                    "status_label": "단단" if contact == "FIRM" else "중간",
                },
                "air_leakage_breathiness": {"status": breath},
                "phonation_regularity": {"status": stability},
            },
            "vocal_type_profile": {
                "register_strategy": {"status": register},
                "canonical_register": {"status": register},
            },
            "timbre_profile": {
                "available": True,
                "axes": {"presence": {"continuum": presence}, "airiness": {"continuum": 0.25}},
            },
            "high_note_function_profile": {
                "available": bool(high_note_available),
                "axes": {},
            },
        }
    }


def _skip():
    return {
        "task_profiles": {},
        "controlled_contrasts": {},
        "user_skipped_tasks": ["siren"],
        "task_evidence": {"user_skipped_tasks": ["siren"]},
    }


def _sample_qa():
    return build_personalized_qa(
        user_concerns=[
            {"id": "VOICE_TOO_NASAL_PERCEPT"},
            {"id": "VOICE_TOO_THIN"},
            {"id": "TIMBRE_CHANGES_HIGH"},
        ],
        song_profile=_song(),
        fused_profile=_skip(),
        timbre_goal={"id": "INTENSE_DISTINCT", "label": "강렬하고 개성 있게"},
    )


def test_report_versions_are_v6_qa_v7_report():
    assert QA_GUIDANCE_VERSION == "precision-qa-coaching-ux-v9"
    assert REPORT_LOGIC_VERSION == "precision-report-v10"


def test_non_safety_answer_hides_epistemic_disclaimer():
    qa = _sample_qa()
    blob = " ".join(q.get("answer") or "" for q in qa["questions"])
    for phrase in EPISTEMIC:
        assert phrase not in blob, phrase


def test_nasal_answer_does_not_show_limited_metric_copy():
    ev = evaluate_concern(
        "VOICE_TOO_NASAL_PERCEPT", song_profile=_song(), task_evidence=_skip()
    )
    assert "직접 확정할 음향 지표는 제한적" not in (ev.get("answer_hint") or "")


def test_thin_answer_does_not_show_no_clear_feature_copy():
    ev = evaluate_concern("VOICE_TOO_THIN", song_profile=_song(), task_evidence=_skip())
    assert "뚜렷한 음향 특징이 강하지 않" not in (ev.get("answer_hint") or "")


def test_high_timbre_answer_does_not_show_noncommittal_copy():
    ev = evaluate_concern(
        "TIMBRE_CHANGES_HIGH", song_profile=_song(), task_evidence=_skip()
    )
    assert "한 원인으로 단정" not in (ev.get("answer_hint") or "")


def test_guided_experiment_has_explicit_baseline_and_variant():
    proto = build_comparison_protocol("VOICE_TOO_NASAL_PERCEPT", snap=_song()["vocal_function_profile"] and None)
    # use song snapshot properly
    from audio_analyzer.diagnostic.song_evidence import get_canonical_snapshot

    snap = get_canonical_snapshot(_song())
    proto = build_comparison_protocol("VOICE_TOO_THIN", snap=snap, primary_focus="REGISTER_CONNECTION")
    assert proto.get("baseline_instruction")
    assert proto.get("variant_instruction")
    assert proto["baseline_instruction"] != proto["variant_instruction"]


def test_guided_experiment_never_says_two_ways_without_defining_them():
    qa = _sample_qa()
    for q in qa["questions"]:
        ans = q.get("answer") or ""
        for bad in UNDEFINED_TWO_WAYS:
            assert bad not in ans
        c = q.get("comparison") or {}
        assert c.get("baseline_instruction") or c.get("A")
        assert c.get("variant_instruction") or c.get("B")


def test_comparison_has_success_condition():
    qa = _sample_qa()
    for q in qa["questions"]:
        c = q.get("comparison") or {}
        assert c.get("success_condition") or c.get("success")


def test_comparison_has_if_better():
    qa = _sample_qa()
    for q in qa["questions"]:
        c = q.get("comparison") or {}
        assert c.get("if_better")


def test_nasal_partial_register_gets_explicit_comparison():
    ev = evaluate_concern(
        "VOICE_TOO_NASAL_PERCEPT",
        song_profile=_song(register="PARTIAL"),
        task_evidence=_skip(),
    )
    c = ev.get("comparison") or ev.get("comparison_protocol") or {}
    assert "비교해보기" not in (ev.get("answer_hint") or "")
    assert c.get("baseline_instruction") or (ev.get("prescription") or {}).get("instruction")
    assert c.get("variant_instruction") or (ev.get("prescription") or {}).get("instruction")
    blob = (c.get("variant_instruction") or "") + ((ev.get("prescription") or {}).get("instruction") or "")
    assert "음량" in blob or "모음" in blob or "자음" in blob or "연결" in blob


def test_nasal_never_claims_nasality_measured():
    ev = evaluate_concern(
        "VOICE_TOO_NASAL_PERCEPT", song_profile=_song(), task_evidence=_skip()
    )
    ans = ev.get("answer_hint") or ""
    assert "비강" not in ans
    assert "콧소리로 측정" not in ans
    assert "비음이 확인" not in ans


def test_thin_low_breath_uses_contra_evidence():
    ev = evaluate_concern(
        "VOICE_TOO_THIN",
        song_profile=_song(breath="LOW", presence=0.72, register="PARTIAL"),
        task_evidence=_skip(),
    )
    ans = ev.get("answer_hint") or ""
    assert "숨이 많이 새" in ans or "막는 방향은 우선" in ans


def test_thin_partial_register_gets_connection_experiment():
    ev = evaluate_concern(
        "VOICE_TOO_THIN",
        song_profile=_song(breath="LOW", register="PARTIAL"),
        task_evidence=_skip(),
    )
    assert ev.get("primary_focus") == "REGISTER_CONNECTION"
    c = ev.get("comparison") or {}
    assert c.get("baseline_instruction") and c.get("variant_instruction")


def test_thin_experiment_avoids_more_pressure():
    ev = evaluate_concern(
        "VOICE_TOO_THIN", song_profile=_song(), task_evidence=_skip()
    )
    blob = " ".join(
        [
            ev.get("answer_hint") or "",
            str((ev.get("comparison") or {}).get("variant_instruction") or ""),
            " ".join(ev.get("avoid") or []),
        ]
    )
    assert "세게 밀" in blob or "더 크게" in blob or "음량" in blob


def test_high_timbre_partial_register_gets_ab_comparison():
    ev = evaluate_concern(
        "TIMBRE_CHANGES_HIGH",
        song_profile=_song(register="PARTIAL", high_note_available=False),
        task_evidence=_skip(),
    )
    assert ev.get("primary_focus") == "REGISTER_CONNECTION"
    c = ev.get("comparison") or {}
    assert "중음" in (c.get("baseline_instruction") or "") or "평소" in (c.get("baseline_instruction") or "")
    assert "작은 강도" in (c.get("variant_instruction") or "") or "음량" in (c.get("variant_instruction") or "")


def test_high_timbre_success_requires_less_abrupt_change_without_more_effort():
    ev = evaluate_concern(
        "TIMBRE_CHANGES_HIGH", song_profile=_song(register="PARTIAL"), task_evidence=_skip()
    )
    success = str((ev.get("comparison") or {}).get("success_condition") or "")
    assert "갑작" in success or "변화" in success
    assert "힘" in success


def test_public_answer_does_not_raw_append_knowledge_support():
    ev = evaluate_concern(
        "TIMBRE_CHANGES_HIGH", song_profile=_song(), task_evidence=_skip()
    )
    ks = str(ev.get("knowledge_support") or "")
    ans = ev.get("answer_hint") or ""
    assert ks
    assert ks not in ans


def test_knowledge_support_still_available_in_internal_object():
    ev = evaluate_concern(
        "TIMBRE_CHANGES_HIGH", song_profile=_song(), task_evidence=_skip()
    )
    assert ev.get("knowledge_support")
    assert ev.get("knowledge_support_internal") is True


def test_two_or_more_evidence_backed_same_focus_can_override_style_goal():
    qa = _sample_qa()
    goal = plan_coaching_goal(
        user_concerns=[{"id": q["concern_id"]} for q in qa["questions"]],
        timbre_goal={"id": "INTENSE_DISTINCT", "label": "강렬하고 개성 있게"},
        concern_evaluations=qa.get("concern_evaluations") or [],
        song_profile=_song(),
    )
    assert goal.get("primary_focus") == "REGISTER_CONNECTION"
    assert goal.get("mode") != "STYLE"


def test_generic_fallback_does_not_count_as_consensus():
    from audio_analyzer.diagnostic.goal_planner import _majority_actionable_focus

    evs = [
        {
            "concern_id": "VOICE_ROUGH",
            "primary_focus": "REGISTER_CONNECTION",
            "guidance_level": "SAFE_GENERAL_GUIDANCE",
            "answer_mode": "GUIDED_EXPERIMENT",
            "evidence_used": [],
            "counts_for_consensus": False,
        },
        {
            "concern_id": "DYNAMICS_DIFFICULT",
            "primary_focus": "REGISTER_CONNECTION",
            "guidance_level": "SAFE_GENERAL_GUIDANCE",
            "evidence_used": [],
            "counts_for_consensus": False,
        },
        {
            "concern_id": "PHRASE_END_WEAK",
            "primary_focus": "REGISTER_CONNECTION",
            "guidance_level": "SAFE_GENERAL_GUIDANCE",
            "evidence_used": [],
            "counts_for_consensus": False,
        },
    ]
    assert _majority_actionable_focus(evs) is None


def test_target_timbre_remains_secondary_after_functional_consensus():
    qa = _sample_qa()
    goal = plan_coaching_goal(
        user_concerns=[{"id": q["concern_id"]} for q in qa["questions"]],
        timbre_goal={"id": "INTENSE_DISTINCT", "label": "강렬하고 개성 있게"},
        concern_evaluations=qa.get("concern_evaluations") or [],
        song_profile=_song(),
    )
    assert goal.get("primary_focus") == "REGISTER_CONNECTION"
    desired = goal.get("desired_outcome") or {}
    assert desired.get("id") == "INTENSE_DISTINCT" or "강렬" in str(desired.get("label") or "")
    assert "강렬" in (goal.get("goal_description") or "") or "개성" in (goal.get("goal_description") or "")


def test_safety_does_not_receive_guided_experiment():
    ev = evaluate_concern(
        "PAIN_WHILE_SINGING",
        song_profile=_song(),
        task_evidence=_skip(),
    )
    assert ev.get("primary_focus") == "SAFETY" or ev.get("guidance_level") == "SAFETY_ONLY"
    assert (ev.get("response_mode") or ev.get("answer_mode")) in ("SAFETY", "SAFETY_ONLY", None) or ev.get(
        "primary_focus"
    ) == "SAFETY"
    # No actionable singing comparison for pain
    c = ev.get("comparison") or {}
    if ev.get("primary_focus") == "SAFETY":
        assert not c.get("baseline_instruction") or ev.get("practice", {}).get("practice_id") in (
            "SAFETY_STOP",
            "SAFETY_FIRST",
            None,
        )


def test_pain_still_returns_safety_stop():
    ev = evaluate_concern(
        "PAIN_WHILE_SINGING",
        song_profile=_song(),
        task_evidence=_skip(),
    )
    assert ev.get("primary_focus") == "SAFETY" or ev.get("guidance_level") == "SAFETY_ONLY"
    pid = (ev.get("action") or {}).get("practice_id") or (ev.get("practice") or {}).get("practice_id")
    assert pid in ("SAFETY_STOP", "SAFETY_FIRST") or ev.get("primary_focus") == "SAFETY"


def test_no_user_answer_contains_limited_metric_disclaimer():
    qa = _sample_qa()
    for q in qa["questions"]:
        assert "직접 확정할 음향 지표는 제한적" not in (q.get("answer") or "")


def test_no_user_answer_contains_undefined_two_way_comparison():
    qa = _sample_qa()
    for q in qa["questions"]:
        ans = q.get("answer") or ""
        # Prescription-first: public answer should not lead with A/B comparison UI copy
        assert "비교해보기" not in ans
        if "두 가지 방식" in ans:
            assert q.get("comparison") or q.get("prescription")
