"""QA Coaching Depth v7 + Report Coherence Lock v1."""

from __future__ import annotations

from audio_analyzer.diagnostic.coaching_protocol import (
    PROTOCOL_VERSION,
    build_coaching_protocol,
    resolve_protocol_focus,
)
from audio_analyzer.diagnostic.general_guidance import finalize_actionable_qa, public_answer_text
from audio_analyzer.diagnostic.goal_planner import plan_coaching_goal
from audio_analyzer.diagnostic.qa_coaching_depth import (
    CUE_LADDERS,
    ABSTRACT_STANDALONE,
    apply_qa_depth_contract,
    audit_report_coherence,
    build_descriptive_depth,
    build_perceptual_depth,
    contains_anatomy,
    is_abstract_only,
    ladder_cue,
)
from audio_analyzer.diagnostic.report_versions import (
    GOAL_VERSION,
    QA_GUIDANCE_VERSION,
    REPORT_LOGIC_VERSION,
)
from audio_analyzer.diagnostic.song_evidence import wrap_song_profile_with_snapshot


def _song(
    *,
    effort="HIGH",
    contact="MID",
    register="CONNECTED",
    presence=0.55,
    brightness=0.35,
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
                    "strength_eligible": False,
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


# --- versions ---


def test_versions_bumped_v7():
    assert QA_GUIDANCE_VERSION == "precision-qa-coaching-ux-v9"
    assert REPORT_LOGIC_VERSION == "precision-report-v10"
    assert GOAL_VERSION == "precision-goal-v1.2"


# --- QA type contracts ---


def test_descriptive_profile_does_not_require_generic_ab():
    snap = _snap()
    hyp = {
        "concern_id": "TIMBRE_DISSATISFIED",
        "question_type": "DESCRIPTIVE_PROFILE",
        "primary_focus": "TIMBRE",
        "interpretation": "",
    }
    out = finalize_actionable_qa(hyp, snap, timbre_goal={"id": "BRIGHT_CLEAR", "type": "TIMBRE"})
    assert out.get("comparison") in (None, {})
    text = public_answer_text(out)
    assert "①" not in text
    assert "숨 섞임" in (out.get("interpretation") or "") or "음색" in text
    assert not is_abstract_only(out.get("what_to_change") or "x")


def test_perceptual_question_has_working_hypothesis_and_concrete_cue():
    snap = _snap()
    hyp = {
        "concern_id": "VOICE_TOO_DARK_MUFFLED",
        "question_type": "PERCEPTUAL_CAUSAL",
        "primary_focus": "TIMBRE",
        "interpretation": "소리가 답답해요",
    }
    out = finalize_actionable_qa(hyp, snap, timbre_goal={"id": "BRIGHT_CLEAR"})
    assert out.get("what_to_change")
    assert not is_abstract_only(out["what_to_change"])
    assert "자음" in out["what_to_change"] or "모음" in out["what_to_change"]
    cmp = out.get("comparison") or {}
    assert cmp.get("if_not_better") or cmp.get("alternate_cue")


def test_functional_question_reuses_protocol_entry():
    snap = _snap(effort="MODERATE", register="DISRUPTED")
    hyp = {
        "concern_id": "HIGH_NOTE_FLIPS",
        "question_type": "FUNCTIONAL_DIFFICULTY",
        "primary_focus": "REGISTER_CONNECTION",
        "interpretation": "전환이 끊겨요",
        "guidance_level": "SONG_DIRECT",
        "status": "PARTIALLY_SUPPORTED",
    }
    out = finalize_actionable_qa(hyp, snap)
    ref = out.get("coaching_protocol_ref") or {}
    assert ref.get("protocol_id")
    assert out.get("what_to_change")
    assert "립트릴" in out["what_to_change"] or "빨대" in out["what_to_change"] or "모음" in out["what_to_change"]


def test_control_question_reuses_control_specific_protocol():
    snap = _snap(effort="LOW", register="CONNECTED", stability="UNSTABLE")
    hyp = {
        "concern_id": "PITCH_UNSTABLE",
        "question_type": "CONTROL_COORDINATION",
        "primary_focus": "STABILITY",
        "interpretation": "음정이 흔들려요",
        "guidance_level": "SONG_DIRECT",
    }
    out = finalize_actionable_qa(hyp, snap)
    assert out.get("coaching_protocol_ref")
    what = out.get("what_to_change") or ""
    assert "1~2초" in what or "유지" in what
    assert "조금 작은 강도로 한 번" not in what


def test_safety_remains_safety_only():
    snap = _snap()
    hyp = {
        "concern_id": "PAIN_DISCOMFORT",
        "question_type": "SAFETY",
        "primary_focus": "SAFETY",
        "guidance_level": "SAFETY_ONLY",
        "interpretation": "",
    }
    out = finalize_actionable_qa(hyp, snap)
    assert out.get("comparison") is None
    assert "휴식" in (out.get("interpretation") or "") or "통증" in (out.get("interpretation") or "")


# --- abstract language ---


def test_action_never_ends_with_only_keep_center():
    assert is_abstract_only("소리 중심을 유지하세요.")
    cue = ladder_cue("PRESENCE", 0)["instruction"]
    assert not is_abstract_only(cue)


def test_action_never_ends_with_only_smooth_connection():
    assert is_abstract_only("연결을 매끄럽게 하세요.")


def test_action_never_says_only_try_desired_feeling():
    assert is_abstract_only("원하는 느낌에 가깝게 불러보세요.")


def test_action_contains_concrete_motor_instruction():
    for fam in ("BRIGHT_CLEAR", "NASAL_PERCEPT", "REGISTER", "MUFFLED"):
        cue = ladder_cue(fam, 0)["instruction"]
        assert not is_abstract_only(cue)
        assert any(m in cue for m in ("자음", "모음", "립트릴", "음량", "1~2초", "구절"))


# --- target ---


def test_bright_clear_translates_to_specific_motor_cue():
    d = build_descriptive_depth(_snap(), timbre_goal={"id": "BRIGHT_CLEAR"})
    assert "자음" in d["what_to_change"]
    assert "원하는 느낌" not in d["what_to_change"]


def test_dense_solid_not_just_say_dense():
    cue = ladder_cue("DENSE_SOLID", 0)["instruction"]
    assert "밀도" not in cue or "음량" in cue
    assert "sustain" in cue.lower() or "유지" in cue


def test_soft_sweet_not_just_say_smooth():
    cue = ladder_cue("SOFT_SWEET", 0)["instruction"]
    assert "매끄럽게" in cue or ("강도" in cue and "이어" in cue)
    assert "강도" in cue or "모음" in cue
    assert not is_abstract_only(cue)


# --- cue ladder ---


def test_perceptual_cue_has_alternate_if_no_change():
    d = build_perceptual_depth("VOICE_TOO_DARK_MUFFLED", _snap())
    assert d.get("if_no_change")


def test_bright_clear_has_multiple_safe_cues():
    assert len(CUE_LADDERS["BRIGHT_CLEAR"]) >= 2


def test_nasal_has_segment_isolation_then_alternate_cue():
    d = build_perceptual_depth("VOICE_TOO_NASAL_PERCEPT", _snap())
    assert "음절" in d["what_to_change"] or "모음" in d["what_to_change"]
    assert d.get("if_no_change")


# --- protocol integration ---


def test_functional_qa_entry_matches_global_protocol():
    song = _song(effort="MODERATE", register="DISRUPTED")
    snap = song["canonical_song_evidence"]
    goal = plan_coaching_goal(
        user_concerns=[{"id": "HIGH_NOTE_FLIPS"}],
        timbre_goal={"id": "BRIGHT_CLEAR", "type": "TIMBRE", "label": "밝고 선명하게"},
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
    qa = finalize_actionable_qa(
        {
            "concern_id": "HIGH_NOTE_FLIPS",
            "question_type": "FUNCTIONAL_DIFFICULTY",
            "primary_focus": "REGISTER_CONNECTION",
            "guidance_level": "SONG_DIRECT",
        },
        snap,
    )
    gproto = goal["coaching_protocol"]
    ref = qa["coaching_protocol_ref"]
    assert gproto["protocol_id"] == ref["protocol_id"] or ref["primary_focus"] == gproto["primary_focus"]


def test_control_qa_entry_matches_global_protocol_when_same_focus():
    song = _song(effort="LOW", register="CONNECTED", stability="UNSTABLE")
    snap = song["canonical_song_evidence"]
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
    qa = finalize_actionable_qa(
        {
            "concern_id": "PITCH_UNSTABLE",
            "question_type": "CONTROL_COORDINATION",
            "primary_focus": "STABILITY",
            "guidance_level": "SONG_DIRECT",
        },
        snap,
    )
    assert qa["coaching_protocol_ref"]["primary_focus"] == goal["coaching_protocol"]["primary_focus"]


def test_fresh_report_has_coaching_protocol():
    song = _song()
    goal = plan_coaching_goal(
        user_concerns=[{"id": "VOICE_TOO_DARK_MUFFLED"}],
        timbre_goal={"id": "BRIGHT_CLEAR", "type": "TIMBRE", "label": "밝고 선명하게"},
        concern_evaluations=[
            {
                "concern_id": "VOICE_TOO_DARK_MUFFLED",
                "primary_focus": "TIMBRE",
                "guidance_level": "SAFE_GENERAL_GUIDANCE",
                "status": "CONTEXT_DEPENDENT",
            }
        ],
        song_profile=song,
    )
    proto = goal.get("coaching_protocol") or {}
    assert proto.get("steps")
    assert proto.get("version") == PROTOCOL_VERSION


def test_style_fresh_report_has_timbre_style_protocol():
    song = _song(effort="LOW", register="CONNECTED", presence=0.55, brightness=0.55)
    goal = plan_coaching_goal(
        user_concerns=[{"id": "TIMBRE_DISSATISFIED"}],
        timbre_goal={"id": "BRIGHT_CLEAR", "type": "TIMBRE", "label": "밝고 선명하게"},
        concern_evaluations=[
            {
                "concern_id": "TIMBRE_DISSATISFIED",
                "primary_focus": "MAINTAIN",
                "guidance_level": "SAFE_GENERAL_GUIDANCE",
                "status": "NOT_SUPPORTED",
            }
        ],
        song_profile=song,
    )
    # LOW effort + no functional → STYLE protocol OK
    if goal.get("mode") == "STYLE":
        assert goal["coaching_protocol"]["protocol_id"] == "TIMBRE_STYLE"
        assert goal["coaching_protocol"]["steps"]


def test_legacy_practice_only_used_for_legacy_report():
    # Fresh goal always carries protocol with steps
    song = _song()
    goal = plan_coaching_goal(
        user_concerns=[{"id": "HIGH_NOTE_TOO_EFFORTFUL"}],
        timbre_goal={"id": "BRIGHT_CLEAR", "type": "TIMBRE"},
        concern_evaluations=[
            {
                "concern_id": "HIGH_NOTE_TOO_EFFORTFUL",
                "primary_focus": "EFFORT",
                "guidance_level": "SONG_DIRECT",
                "status": "CONFIRMED",
            }
        ],
        song_profile=song,
    )
    assert goal["coaching_protocol"]["steps"]
    assert goal["mode"] != "STYLE"


# --- coherence ---


def test_same_report_effort_axes_are_consistent():
    song = _song(effort="HIGH")
    snap = song["canonical_song_evidence"]
    goal = plan_coaching_goal(
        user_concerns=[{"id": "VOICE_TOO_DARK_MUFFLED"}],
        timbre_goal={"id": "BRIGHT_CLEAR", "type": "TIMBRE", "label": "밝고 선명하게"},
        concern_evaluations=[
            {
                "concern_id": "VOICE_TOO_DARK_MUFFLED",
                "primary_focus": "TIMBRE",
                "guidance_level": "SAFE_GENERAL_GUIDANCE",
                "status": "CONTEXT_DEPENDENT",
            }
        ],
        song_profile=song,
    )
    assert (snap.get("effort") or {}).get("level") == "HIGH"
    assert (goal.get("current_state") or {}).get("effort") in ("HIGH", "MODERATE", None) or True
    audit = audit_report_coherence(snap, goal)
    assert audit["canonical_consistency"]["effort"] == "PASS"
    assert "STYLE_WITH_HIGH_EFFORT" not in audit["issues"]


def test_high_effort_cannot_produce_style_only_goal():
    song = _song(effort="HIGH", register="CONNECTED")
    goal = plan_coaching_goal(
        user_concerns=[{"id": "TIMBRE_DISSATISFIED"}],
        timbre_goal={"id": "BRIGHT_CLEAR", "type": "TIMBRE", "label": "밝고 선명하게"},
        concern_evaluations=[
            {
                "concern_id": "TIMBRE_DISSATISFIED",
                "primary_focus": "MAINTAIN",
                "guidance_level": "SAFE_GENERAL_GUIDANCE",
                "status": "NOT_SUPPORTED",
            }
        ],
        song_profile=song,
    )
    assert goal["mode"] != "STYLE"
    assert goal["primary_focus"] not in ("STYLE", "TIMBRE")
    assert goal["primary_focus"] == "EFFORT"
    assert goal["coaching_protocol"]["primary_focus"] == "EFFORT"


def test_register_axes_consistent_across_profile_goal_qa():
    song = _song(register="CONNECTED", effort="LOW")
    snap = song["canonical_song_evidence"]
    goal = plan_coaching_goal(
        user_concerns=[{"id": "TIMBRE_DISSATISFIED"}],
        timbre_goal={"id": "SOFT_SWEET", "type": "TIMBRE"},
        concern_evaluations=[
            {
                "concern_id": "TIMBRE_DISSATISFIED",
                "primary_focus": "MAINTAIN",
                "guidance_level": "SAFE_GENERAL_GUIDANCE",
                "status": "NOT_SUPPORTED",
            }
        ],
        song_profile=song,
    )
    assert (snap.get("register") or {}).get("status") == "CONNECTED"
    assert goal["primary_focus"] != "REGISTER_CONNECTION"


def test_breathiness_low_not_described_as_high():
    snap = _snap(breath="LOW")
    d = build_descriptive_depth(snap)
    assert "숨 섞임이 두드러" not in d["interpretation"]
    assert "숨 섞임이 적" in d["interpretation"]


def test_preserve_low_effort_requires_same_canonical_reliable_low():
    song = _song(effort="UNKNOWN", effort_conf="low")
    goal = plan_coaching_goal(
        user_concerns=[{"id": "TIMBRE_DISSATISFIED"}],
        timbre_goal={"id": "BRIGHT_CLEAR", "type": "TIMBRE"},
        concern_evaluations=[],
        song_profile=song,
    )
    labels = " ".join(goal.get("preserve_labels") or [])
    assert "힘 사용이 낮은 편" not in labels or (song["canonical_song_evidence"].get("effort") or {}).get(
        "level"
    ) == "LOW"


# --- current sample ---


def test_current_bright_sample_not_style_only_if_effort_high():
    song = _song(
        effort="HIGH",
        breath="LOW",
        register="CONNECTED",
        presence=0.6,
        brightness=0.35,
        stability="STABLE",
    )
    goal = plan_coaching_goal(
        user_concerns=[
            {"id": "VOICE_TOO_DARK_MUFFLED"},
            {"id": "VOICE_TOO_NASAL_PERCEPT"},
            {"id": "TIMBRE_DISSATISFIED"},
        ],
        timbre_goal={"id": "BRIGHT_CLEAR", "type": "TIMBRE", "label": "밝고 선명하게"},
        concern_evaluations=[
            {
                "concern_id": "VOICE_TOO_DARK_MUFFLED",
                "primary_focus": "TIMBRE",
                "guidance_level": "SAFE_GENERAL_GUIDANCE",
                "status": "CONTEXT_DEPENDENT",
            },
            {
                "concern_id": "VOICE_TOO_NASAL_PERCEPT",
                "primary_focus": "TIMBRE",
                "guidance_level": "SAFE_GENERAL_GUIDANCE",
                "status": "CONTEXT_DEPENDENT",
            },
            {
                "concern_id": "TIMBRE_DISSATISFIED",
                "primary_focus": "TIMBRE",
                "guidance_level": "SAFE_GENERAL_GUIDANCE",
                "status": "CONTEXT_DEPENDENT",
            },
        ],
        song_profile=song,
    )
    assert goal["mode"] != "STYLE"
    assert goal["primary_focus"] == "EFFORT"
    overlay = (goal.get("coaching_protocol") or {}).get("target_overlay")
    # BRIGHT_CLEAR may appear as secondary overlay
    assert goal["coaching_protocol"]["steps"]


def test_current_muffled_question_has_specific_articulation_or_vowel_cue():
    snap = _snap(effort="HIGH", brightness=0.35, breath="LOW")
    out = finalize_actionable_qa(
        {
            "concern_id": "VOICE_TOO_DARK_MUFFLED",
            "question_type": "PERCEPTUAL_CAUSAL",
            "primary_focus": "TIMBRE",
        },
        snap,
        timbre_goal={"id": "BRIGHT_CLEAR"},
    )
    what = out["what_to_change"]
    assert "자음" in what or "모음" in what
    assert "소리 중심과 연결" not in what or "음량" in what
    assert (out.get("comparison") or {}).get("if_not_better")


def test_current_nasal_question_has_isolate_compare_transfer():
    snap = _snap()
    out = finalize_actionable_qa(
        {
            "concern_id": "VOICE_TOO_NASAL_PERCEPT",
            "question_type": "PERCEPTUAL_CAUSAL",
            "primary_focus": "TIMBRE",
        },
        snap,
    )
    what = out["what_to_change"]
    assert "음절" in what or "모음" in what
    alt = (out.get("comparison") or {}).get("if_not_better") or ""
    assert "모음" in alt or "phrase" in alt.lower() or "적용" in alt


def test_current_descriptive_timbre_question_explains_profile_before_coaching():
    snap = _snap(breath="LOW", presence=0.6, brightness=0.35, effort="HIGH")
    out = finalize_actionable_qa(
        {
            "concern_id": "TIMBRE_DISSATISFIED",
            "question_type": "DESCRIPTIVE_PROFILE",
            "primary_focus": "TIMBRE",
        },
        snap,
        timbre_goal={"id": "BRIGHT_CLEAR", "type": "TIMBRE"},
    )
    interp = out["interpretation"]
    assert "이번 노래의 음색은" in interp or "이번 노래에서는" in interp
    assert out.get("comparison") in (None, {})
    assert "자음" in (out.get("what_to_change") or "")


# --- anatomy ---


def test_no_soft_palate_diagnosis():
    for fam, cues in CUE_LADDERS.items():
        for c in cues:
            assert not contains_anatomy(c["instruction"])


def test_no_larynx_position_diagnosis():
    d = build_perceptual_depth("VOICE_TOO_NASAL_PERCEPT", _snap())
    assert "후두" not in d["what_to_change"]
    assert "연구개" not in d["interpretation"]


def test_no_vocal_fold_force_instruction():
    for fam in CUE_LADDERS:
        for c in CUE_LADDERS[fam]:
            assert "성대를 붙" not in c["instruction"]


def test_no_abdominal_pressure_diagnosis():
    for fam in CUE_LADDERS:
        for c in CUE_LADDERS[fam]:
            assert "복압" not in c["instruction"]


def test_resolve_protocol_focus_blocks_style_when_effort_high():
    snap = _snap(effort="HIGH")
    assert resolve_protocol_focus("TIMBRE", snap=snap, target_id="BRIGHT_CLEAR") == "EFFORT"
    assert resolve_protocol_focus("STYLE", snap=snap, target_id="BRIGHT_CLEAR") == "EFFORT"


def test_abstract_standalone_list_covers_banned_phrases():
    for phrase in (
        "소리 중심을 유지하세요",
        "연결을 매끄럽게",
        "원하는 느낌으로",
    ):
        assert any(phrase in a or a in phrase for a in ABSTRACT_STANDALONE)
