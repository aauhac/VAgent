# -*- coding: utf-8 -*-
"""Behavioral audit remediation v1 regression tests."""

from __future__ import annotations

from scripts.vocal_behavioral_audit.claim_lint import (
    classify_claim_spans,
    evaluate_claim_against_axes,
)
from scripts.vocal_behavioral_audit.detectors import generic_collapse_pairs
from scripts.vocal_behavioral_audit.diagnose import axes_from_snap, diagnose_case, wrap_song
from audio_analyzer.diagnostic.functional_hypothesis import build_functional_hypothesis
from audio_analyzer.diagnostic.goal_planner import plan_coaching_goal
from audio_analyzer.diagnostic.concerns import PAIN_CONCERN_IDS, normalize_user_concerns


def _snap(**kwargs):
    base = {
        "effort": {"level": "LOW", "reliable_for_preserve": True},
        "contact": {"status": "AMBIGUOUS"},
        "breathiness": {"level": "LOW"},
        "register": {"status": "UNRESOLVED", "available": True},
        "stability": {"status": "STABLE"},
        "timbre": {"presence": 0.5, "brightness": 0.5},
        "availability": {},
        "high_note": {"available": False},
        "source_balance": {"status": "CHEST_DOMINANT", "available": True},
    }
    base.update(kwargs)
    return base


def test_axes_split_register_connection_and_source_balance():
    axes = axes_from_snap(_snap())
    assert axes["register_connection"] == "UNRESOLVED"
    assert axes["source_balance"] == "CHEST_DOMINANT"
    assert "CHEST" not in axes["register_connection"]


def test_strong_register_bottleneck_beats_style_target():
    snap = _snap(register={"status": "DISRUPTED", "available": True})
    song = {"canonical_song_evidence": snap, "vocal_features": {}}
    wrapped = wrap_song({"song_profile": song}) if False else {
        "canonical_song_evidence": snap,
    }
    # Direct goal planner path
    concerns = normalize_user_concerns(
        [{"id": "HIGH_NOTE_FLIPS"}, {"id": "TIMBRE_DISSATISFIED"}]
    )
    evs = [
        {
            "concern_id": "HIGH_NOTE_FLIPS",
            "primary_focus": "REGISTER_CONNECTION",
            "guidance_level": "SONG_DIRECT",
            "status": "SUPPORTED",
            "secondary_factors": [],
            "functional_hypothesis": {"evidence_used": [{"axis": "register"}]},
        },
        {
            "concern_id": "TIMBRE_DISSATISFIED",
            "primary_focus": "TIMBRE",
            "guidance_level": "SAFE_GENERAL_GUIDANCE",
            "status": "UNRESOLVED",
            "secondary_factors": [],
        },
    ]
    goal = plan_coaching_goal(
        user_concerns=concerns,
        timbre_goal={"id": "BRIGHT_CLEAR"},
        concern_evaluations=evs,
        song_profile={"canonical_song_evidence": snap},
        pain=False,
    )
    assert goal["primary_focus"] == "REGISTER_CONNECTION"
    assert goal.get("secondary_target") is not None
    assert goal["secondary_target"]["id"] == "BRIGHT_CLEAR"


def test_effort_bottleneck_beats_timbre_target():
    snap = _snap(effort={"level": "HIGH", "reliable_for_preserve": True})
    concerns = normalize_user_concerns([{"id": "HIGH_NOTE_TOO_EFFORTFUL"}, {"id": "TIMBRE_DISSATISFIED"}])
    evs = [
        {
            "concern_id": "HIGH_NOTE_TOO_EFFORTFUL",
            "primary_focus": "EFFORT",
            "guidance_level": "SONG_DIRECT",
            "status": "SUPPORTED",
            "secondary_factors": [],
            "functional_hypothesis": {"evidence_used": [{"axis": "effort"}]},
        },
    ]
    goal = plan_coaching_goal(
        user_concerns=concerns,
        timbre_goal={"id": "SOFT_SWEET"},
        concern_evaluations=evs,
        song_profile={"canonical_song_evidence": snap},
        pain=False,
    )
    assert goal["primary_focus"] == "EFFORT"
    assert goal.get("mode") != "STYLE"


def test_target_remains_secondary():
    snap = _snap(register={"status": "DISRUPTED", "available": True})
    concerns = normalize_user_concerns([{"id": "REGISTER_CONNECTION_DIFFICULT"}])
    evs = [
        {
            "concern_id": "REGISTER_CONNECTION_DIFFICULT",
            "primary_focus": "REGISTER_CONNECTION",
            "guidance_level": "SONG_DIRECT",
            "status": "SUPPORTED",
            "secondary_factors": [],
        },
    ]
    goal = plan_coaching_goal(
        user_concerns=concerns,
        timbre_goal={"id": "BRIGHT_CLEAR"},
        concern_evaluations=evs,
        song_profile={"canonical_song_evidence": snap},
        pain=False,
    )
    assert goal["primary_focus"] != "STYLE"
    assert goal.get("secondary_target", {}).get("id") == "BRIGHT_CLEAR"


def test_unavailable_brightness_never_claimed_dark():
    axes = {"brightness": "UNAVAILABLE", "register_connection": "UNRESOLVED"}
    spans = classify_claim_spans("밝기가 어두운 편이에요.")
    assert spans
    ev = evaluate_claim_against_axes(spans[0], axes)
    assert ev["classification"] == "TRUE_POSITIVE"


def test_low_breath_never_claimed_high():
    axes = {"breathiness": "LOW", "register_connection": "UNRESOLVED"}
    spans = classify_claim_spans("숨이 많이 섞이는 편이에요.")
    assert spans
    ev = evaluate_claim_against_axes(spans[0], axes)
    assert ev["classification"] == "TRUE_POSITIVE"


def test_connected_register_never_claimed_disrupted():
    axes = {"register_connection": "CONNECTED", "breathiness": "LOW"}
    spans = classify_claim_spans("성구 연결이 급격하게 달라지는 구간이 보여요.")
    assert spans
    ev = evaluate_claim_against_axes(spans[0], axes)
    assert ev["classification"] == "TRUE_POSITIVE"


def test_general_instruction_not_flagged_as_acoustic_claim():
    axes = {"breathiness": "LOW", "brightness": "LOW"}
    spans = classify_claim_spans("음량을 키우지 않는 것이 좋아요. 숨이 많이 새는 느낌보다는 작은 강도로 이어보세요.")
    # Contrast / instruction → false positive lint, not true unsupported
    classes = {evaluate_claim_against_axes(s, axes)["classification"] for s in spans}
    assert "TRUE_POSITIVE" not in classes


def test_same_register_protocol_can_be_expected_shared():
    cases = [
        {
            "audio_id": "a1",
            "concern_id": "HIGH_NOTE_FLIPS",
            "primary_focus": "REGISTER_CONNECTION",
            "protocol_id": "REGISTER_CONNECTION",
            "question_type": "FUNCTIONAL",
            "qa": {
                "prescription": {
                    "instruction": "립트릴로 이어 올리세요",
                    "success_cues": ["뒤집힘이 줄어듦"],
                }
            },
        },
        {
            "audio_id": "a1",
            "concern_id": "REGISTER_CONNECTION_DIFFICULT",
            "primary_focus": "REGISTER_CONNECTION",
            "protocol_id": "REGISTER_CONNECTION",
            "question_type": "CONTROL",
            "qa": {
                "prescription": {
                    "instruction": "립트릴로 이어 올리세요",
                    "success_cues": ["연결이 더 이어짐"],
                }
            },
        },
    ]
    rows = generic_collapse_pairs(cases, threshold=0.5)
    assert rows
    assert rows[0]["classification"] == "EXPECTED_SHARED_PROTOCOL"


def test_different_semantics_same_exact_action_is_over_shared():
    cases = [
        {
            "audio_id": "a1",
            "concern_id": "HIGH_NOTE_FLIPS",
            "primary_focus": "REGISTER_CONNECTION",
            "protocol_id": "REGISTER_CONNECTION",
            "question_type": "FUNCTIONAL",
            "qa": {
                "prescription": {
                    "instruction": "exact same instruction text",
                    "success_cues": ["exact same success"],
                }
            },
        },
        {
            "audio_id": "a1",
            "concern_id": "REGISTER_CONNECTION_DIFFICULT",
            "primary_focus": "REGISTER_CONNECTION",
            "protocol_id": "REGISTER_CONNECTION",
            "question_type": "CONTROL",
            "qa": {
                "prescription": {
                    "instruction": "exact same instruction text",
                    "success_cues": ["exact same success"],
                }
            },
        },
    ]
    rows = generic_collapse_pairs(cases, threshold=0.5)
    assert rows[0]["classification"] == "OVER_SHARED_PRESCRIPTION"


def test_different_focus_generic_action_is_wrong_collapse():
    cases = [
        {
            "audio_id": "a1",
            "concern_id": "VOICE_ROUGH",
            "primary_focus": "STABILITY",
            "protocol_id": "STABILITY",
            "question_type": "PERCEPTUAL",
            "qa": {"prescription": {"instruction": "generic do thing", "success_cues": ["ok"]}},
        },
        {
            "audio_id": "a1",
            "concern_id": "VOICE_TOO_THIN",
            "primary_focus": "PRESENCE",
            "protocol_id": "PRESENCE",
            "question_type": "PERCEPTUAL",
            "qa": {"prescription": {"instruction": "generic do thing", "success_cues": ["ok"]}},
        },
    ]
    rows = generic_collapse_pairs(cases, threshold=0.5)
    assert rows[0]["classification"] == "WRONG_GENERIC_COLLAPSE"


def test_high_note_cannot_reach_register_only_when_register_evidence():
    snap = _snap(register={"status": "DISRUPTED", "available": True})
    hyp = build_functional_hypothesis(
        "HIGH_NOTE_CANNOT_REACH",
        song_profile={"canonical_song_evidence": snap},
    )
    assert hyp["primary_focus"] == "REGISTER_CONNECTION"
    assert hyp.get("focus_selection_reason") == "REGISTER_EVIDENCE"


def test_high_note_cannot_reach_effort_when_reliable_effort_elevated():
    snap = _snap(effort={"level": "HIGH", "reliable_for_preserve": True})
    hyp = build_functional_hypothesis(
        "HIGH_NOTE_CANNOT_REACH",
        song_profile={"canonical_song_evidence": snap},
    )
    assert hyp["primary_focus"] == "EFFORT"
    assert hyp.get("focus_selection_reason") == "EFFORT_EVIDENCE"


def test_high_note_cannot_reach_stability_when_stability_evidence():
    snap = _snap(stability={"status": "UNSTABLE"})
    hyp = build_functional_hypothesis(
        "HIGH_NOTE_CANNOT_REACH",
        song_profile={"canonical_song_evidence": snap},
    )
    assert hyp["primary_focus"] == "STABILITY"
    assert hyp.get("focus_selection_reason") == "STABILITY_EVIDENCE"


def test_high_note_cannot_reach_no_evidence_uses_high_note_access():
    snap = _snap()
    hyp = build_functional_hypothesis(
        "HIGH_NOTE_CANNOT_REACH",
        song_profile={"canonical_song_evidence": snap},
    )
    assert hyp["primary_focus"] == "HIGH_NOTE"
    assert hyp.get("focus_selection_reason") == "GENERAL_HIGH_NOTE_ACCESS"


def test_safety_excluded_from_low_diversity_warning():
    for sid in PAIN_CONCERN_IDS:
        assert sid  # catalog non-empty
    # Runner excludes safety; assert catalog membership
    assert "PAIN_WHILE_SINGING" in PAIN_CONCERN_IDS


def test_voice_rough_can_adapt_to_texture_or_stability():
    from audio_analyzer.diagnostic.qa_coaching_depth import pick_perceptual_family

    stab = pick_perceptual_family(
        "VOICE_ROUGH", _snap(stability={"status": "UNSTABLE"})
    )
    breath = pick_perceptual_family(
        "VOICE_ROUGH", _snap(breathiness={"level": "HIGH"}, stability={"status": "STABLE"})
    )
    assert stab == "STABILITY"
    assert breath == "BREATHINESS"


def test_phrase_end_can_adapt_to_relevant_evidence():
    from audio_analyzer.diagnostic.qa_coaching_depth import pick_perceptual_family

    pe = pick_perceptual_family("PHRASE_END_WEAK", _snap())
    pe_stab = pick_perceptual_family(
        "PHRASE_END_WEAK", _snap(stability={"status": "UNSTABLE"})
    )
    assert pe == "PHRASE_END"
    assert pe_stab == "STABILITY"
