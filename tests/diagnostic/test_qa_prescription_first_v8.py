"""Prescription-First Coaching v8 + Focus/Practice Coherence Lock."""

from __future__ import annotations

from audio_analyzer.diagnostic.general_guidance import finalize_actionable_qa, public_answer_text
from audio_analyzer.diagnostic.goal_planner import plan_coaching_goal
from audio_analyzer.diagnostic.practice_library import FOCUS_TO_PRACTICE, practice_for_focus
from audio_analyzer.diagnostic.qa_coaching_depth import (
    contains_anatomy,
    is_abstract_only,
    ladder_cue,
)
from audio_analyzer.diagnostic.report_versions import QA_GUIDANCE_VERSION, REPORT_LOGIC_VERSION
from audio_analyzer.diagnostic.song_evidence import wrap_song_profile_with_snapshot


def _song(
    *,
    effort="LOW",
    contact="FIRM",
    register="PARTIAL",
    presence=0.5,
    brightness=0.32,
    breath="LOW",
    stability="STABLE",
    effort_conf="high",
):
    cont = {"FIRM": 0.72, "LIGHT": 0.28, "MID": 0.5}.get(contact, 0.5)
    return wrap_song_profile_with_snapshot(
        {
            "vocal_function_profile": {
                "effort_assessment": {
                    "severity": effort,
                    "status": effort,
                    "confidence_label": effort_conf,
                    "strength_eligible": effort == "LOW" and effort_conf in ("medium", "high"),
                },
                "dimensions": {
                    "vocal_effort_strain": {"status": effort, "confidence_label": effort_conf},
                    "glottal_contact_profile": {
                        "status": "OBSERVED",
                        "continuum_0_to_1": cont,
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
                    "axes": {
                        "presence": {"continuum": presence},
                        "brightness": {"continuum": brightness},
                    },
                },
            }
        }
    )


def _snap(**kwargs):
    return _song(**kwargs)["canonical_song_evidence"]


def _sample_evals():
    return [
        {
            "concern_id": "TIMBRE_DISSATISFIED",
            "primary_focus": "BRIGHTNESS",
            "guidance_level": "SAFE_GENERAL_GUIDANCE",
            "status": "CONTEXT_DEPENDENT",
        },
        {
            "concern_id": "VOICE_TOO_DARK_MUFFLED",
            "primary_focus": "BRIGHTNESS",
            "guidance_level": "SAFE_GENERAL_GUIDANCE",
            "status": "CONTEXT_DEPENDENT",
        },
        {
            "concern_id": "VOICE_TOO_NASAL_PERCEPT",
            "primary_focus": "TIMBRE",
            "guidance_level": "SAFE_GENERAL_GUIDANCE",
            "status": "CONTEXT_DEPENDENT",
        },
    ]


def test_versions_bumped_v8():
    assert QA_GUIDANCE_VERSION == "precision-qa-coaching-ux-v9"
    assert REPORT_LOGIC_VERSION == "precision-report-v10"


def test_user_qa_does_not_default_to_ab_comparison():
    out = finalize_actionable_qa(
        {
            "concern_id": "VOICE_TOO_DARK_MUFFLED",
            "question_type": "PERCEPTUAL_CAUSAL",
            "primary_focus": "BRIGHTNESS",
        },
        _snap(),
        timbre_goal={"id": "BRIGHT_CLEAR"},
    )
    text = public_answer_text(out)
    assert "비교해보기" not in text
    assert "①" not in text
    assert out.get("prescription")
    assert out.get("comparison")  # internal preserved


def test_perceptual_qa_has_direct_prescription():
    out = finalize_actionable_qa(
        {
            "concern_id": "VOICE_TOO_DARK_MUFFLED",
            "question_type": "PERCEPTUAL_CAUSAL",
            "primary_focus": "BRIGHTNESS",
        },
        _snap(),
    )
    rx = out["prescription"]
    assert rx["instruction"]
    assert not is_abstract_only(rx["instruction"])


def test_prescription_contains_how_not_only_goal_state():
    rx = finalize_actionable_qa(
        {
            "concern_id": "VOICE_TOO_NASAL_PERCEPT",
            "question_type": "PERCEPTUAL_CAUSAL",
            "primary_focus": "TIMBRE",
        },
        _snap(),
    )["prescription"]
    assert any(m in rx["instruction"] for m in ("자음", "모음", "음절", "음량"))


def test_prescription_has_repetition_or_clear_scope():
    rx = finalize_actionable_qa(
        {
            "concern_id": "VOICE_TOO_DARK_MUFFLED",
            "question_type": "PERCEPTUAL_CAUSAL",
            "primary_focus": "BRIGHTNESS",
        },
        _snap(),
    )["prescription"]
    assert rx.get("repetitions") or "2~3" in rx["instruction"] or "회" in rx["instruction"]


def test_prescription_has_success_cues():
    rx = finalize_actionable_qa(
        {
            "concern_id": "VOICE_TOO_DARK_MUFFLED",
            "question_type": "PERCEPTUAL_CAUSAL",
            "primary_focus": "BRIGHTNESS",
        },
        _snap(),
    )["prescription"]
    assert rx.get("success_cues")


def test_prescription_has_alternate_when_applicable():
    rx = finalize_actionable_qa(
        {
            "concern_id": "VOICE_TOO_DARK_MUFFLED",
            "question_type": "PERCEPTUAL_CAUSAL",
            "primary_focus": "BRIGHTNESS",
        },
        _snap(),
    )["prescription"]
    assert (rx.get("alternate") or {}).get("instruction")


def test_no_standalone_keep_center_instruction():
    assert is_abstract_only("소리 중심을 유지하세요.")


def test_no_standalone_smooth_connection_instruction():
    assert is_abstract_only("연결을 매끄럽게 하세요.")


def test_no_standalone_desired_feeling_instruction():
    assert is_abstract_only("원하는 느낌에 가깝게 불러보세요.")


def test_no_standalone_explore_expression_instruction():
    assert is_abstract_only("표현을 바꿔보세요.")


def test_descriptive_timbre_explains_profile_first():
    out = finalize_actionable_qa(
        {
            "concern_id": "TIMBRE_DISSATISFIED",
            "question_type": "DESCRIPTIVE_PROFILE",
            "primary_focus": "TIMBRE",
        },
        _snap(),
        timbre_goal={"id": "BRIGHT_CLEAR", "type": "TIMBRE"},
    )
    assert "음색" in out["interpretation"]
    assert out.get("comparison") in (None, {})


def test_descriptive_timbre_does_not_force_generic_ab():
    text = public_answer_text(
        finalize_actionable_qa(
            {
                "concern_id": "TIMBRE_DISSATISFIED",
                "question_type": "DESCRIPTIVE_PROFILE",
                "primary_focus": "TIMBRE",
            },
            _snap(),
            timbre_goal={"id": "BRIGHT_CLEAR"},
        )
    )
    assert "①" not in text and "비교해보기" not in text


def test_muffled_brightness_low_gets_articulation_vowel_prescription():
    out = finalize_actionable_qa(
        {
            "concern_id": "VOICE_TOO_DARK_MUFFLED",
            "question_type": "PERCEPTUAL_CAUSAL",
            "primary_focus": "BRIGHTNESS",
        },
        _snap(brightness=0.3),
    )
    what = out["prescription"]["instruction"]
    assert "자음" in what or "모음" in what


def test_muffled_prescription_has_alternate_vowel_cue():
    alt = (
        finalize_actionable_qa(
            {
                "concern_id": "VOICE_TOO_DARK_MUFFLED",
                "question_type": "PERCEPTUAL_CAUSAL",
                "primary_focus": "BRIGHTNESS",
            },
            _snap(),
        )["prescription"]
        .get("alternate")
        or {}
    ).get("instruction", "")
    assert "모음" in alt or "에" in alt or "이" in alt


def test_nasal_prescription_isolates_problem_syllable():
    what = finalize_actionable_qa(
        {
            "concern_id": "VOICE_TOO_NASAL_PERCEPT",
            "question_type": "PERCEPTUAL_CAUSAL",
            "primary_focus": "TIMBRE",
        },
        _snap(),
    )["prescription"]["instruction"]
    assert "음절" in what or "모음" in what


def test_nasal_prescription_has_consonant_vowel_cue():
    what = finalize_actionable_qa(
        {
            "concern_id": "VOICE_TOO_NASAL_PERCEPT",
            "question_type": "PERCEPTUAL_CAUSAL",
            "primary_focus": "TIMBRE",
        },
        _snap(),
    )["prescription"]["instruction"]
    assert "자음" in what and "모음" in what


def test_nasal_prescription_has_alternate_vowel_shape():
    alt = (
        finalize_actionable_qa(
            {
                "concern_id": "VOICE_TOO_NASAL_PERCEPT",
                "question_type": "PERCEPTUAL_CAUSAL",
                "primary_focus": "TIMBRE",
            },
            _snap(),
        )["prescription"]
        .get("alternate")
        or {}
    ).get("instruction", "")
    assert "모음" in alt


def test_nasal_prescription_transfers_to_phrase():
    rx = finalize_actionable_qa(
        {
            "concern_id": "VOICE_TOO_NASAL_PERCEPT",
            "question_type": "PERCEPTUAL_CAUSAL",
            "primary_focus": "TIMBRE",
        },
        _snap(),
    )["prescription"]
    assert "phrase" in (rx.get("song_transfer") or "").lower() or "가사" in (rx.get("song_transfer") or "")


def test_brightness_focus_cannot_emit_presence_main_practice():
    assert FOCUS_TO_PRACTICE["BRIGHTNESS"] != "PRESENCE_WITHOUT_PUSHING"
    p = practice_for_focus("BRIGHTNESS")
    assert p
    assert "PRESENCE" not in str(p.get("practice_id") or "")
    assert "존재감" not in str(p.get("title") or "")

    song = _song()
    goal = plan_coaching_goal(
        user_concerns=[{"id": "VOICE_TOO_DARK_MUFFLED"}],
        timbre_goal={"id": "BRIGHT_CLEAR", "type": "TIMBRE", "label": "밝고 선명하게"},
        concern_evaluations=_sample_evals(),
        song_profile=song,
    )
    # If focus lands on BRIGHTNESS, practice must not be presence
    if goal.get("primary_focus") == "BRIGHTNESS":
        practices = goal.get("practices") or []
        blob = " ".join(
            str(p.get("practice_id") or "") + str(p.get("title") or "") for p in practices
        )
        assert "PRESENCE" not in blob
        assert "존재감" not in blob


def test_register_focus_emits_register_protocol():
    song = _song(register="DISRUPTED", effort="LOW")
    goal = plan_coaching_goal(
        user_concerns=[{"id": "HIGH_NOTE_FLIPS"}],
        timbre_goal={"id": "BRIGHT_CLEAR", "type": "TIMBRE"},
        concern_evaluations=[
            {
                "concern_id": "HIGH_NOTE_FLIPS",
                "primary_focus": "REGISTER_CONNECTION",
                "guidance_level": "SONG_DIRECT",
                "status": "PARTIALLY_SUPPORTED",
                "counts_for_consensus": True,
            }
        ],
        song_profile=song,
    )
    assert goal["primary_focus"] == "REGISTER_CONNECTION"
    assert "REGISTER" in str((goal.get("coaching_protocol") or {}).get("protocol_id") or "")


def test_stability_focus_emits_stability_protocol():
    song = _song(register="CONNECTED", stability="UNSTABLE", effort="LOW")
    goal = plan_coaching_goal(
        user_concerns=[{"id": "PITCH_UNSTABLE"}],
        timbre_goal=None,
        concern_evaluations=[
            {
                "concern_id": "PITCH_UNSTABLE",
                "primary_focus": "STABILITY",
                "guidance_level": "SONG_DIRECT",
                "status": "PARTIALLY_SUPPORTED",
                "counts_for_consensus": True,
            }
        ],
        song_profile=song,
    )
    assert goal["primary_focus"] == "STABILITY"
    assert "STABILITY" in str((goal.get("coaching_protocol") or {}).get("protocol_id") or "")


def test_presence_focus_emits_presence_protocol():
    song = _song(presence=0.3, brightness=0.55, effort="LOW", register="CONNECTED")
    goal = plan_coaching_goal(
        user_concerns=[{"id": "VOICE_TOO_THIN"}],
        timbre_goal=None,
        concern_evaluations=[
            {
                "concern_id": "VOICE_TOO_THIN",
                "primary_focus": "PRESENCE",
                "guidance_level": "SONG_DIRECT",
                "status": "PARTIALLY_SUPPORTED",
                "counts_for_consensus": True,
            }
        ],
        song_profile=song,
    )
    assert goal["primary_focus"] == "PRESENCE"
    assert "PRESENCE" in str((goal.get("coaching_protocol") or {}).get("protocol_id") or "")


def test_goal_does_not_use_internal_planner_copy():
    song = _song()
    goal = plan_coaching_goal(
        user_concerns=[{"id": "VOICE_TOO_DARK_MUFFLED"}],
        timbre_goal={"id": "BRIGHT_CLEAR", "type": "TIMBRE", "label": "밝고 선명하게"},
        concern_evaluations=_sample_evals(),
        song_profile=song,
    )
    title = goal.get("goal_title") or ""
    assert "관련 있는 패턴부터 확인" not in title
    assert "원하는 방향에 가까워지도록" not in title


def test_brightness_goal_is_user_actionable():
    title, desc = None, None
    from audio_analyzer.diagnostic.goal_planner import _goal_copy

    title, desc = _goal_copy(
        {"id": "BRIGHT_CLEAR", "type": "TIMBRE", "label": "밝고 선명하게"},
        "BRIGHTNESS",
        _snap(),
        style=False,
        safety=False,
    )
    assert "선명" in title or "밝" in title
    assert "발음" in desc or "모음" in desc


def test_prescription_never_diagnoses_soft_palate():
    for fam in ("NASAL_PERCEPT", "MUFFLED", "BRIGHT_CLEAR"):
        assert not contains_anatomy(ladder_cue(fam, 0)["instruction"])


def test_prescription_never_instructs_larynx_position():
    assert "후두" not in ladder_cue("NASAL_PERCEPT", 0)["instruction"]


def test_prescription_never_instructs_forceful_vocal_fold_contact():
    assert "성대를 붙" not in ladder_cue("DENSE_SOLID", 0)["instruction"]


def test_pain_has_no_active_prescription():
    out = finalize_actionable_qa(
        {
            "concern_id": "PAIN_DISCOMFORT",
            "question_type": "SAFETY",
            "primary_focus": "SAFETY",
            "guidance_level": "SAFETY_ONLY",
        },
        _snap(),
    )
    assert out.get("prescription") in (None, {})
    assert out.get("comparison") is None
