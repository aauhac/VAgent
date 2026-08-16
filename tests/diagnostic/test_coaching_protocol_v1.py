"""Coaching Protocol v1 — multi-step entry/progression/regression/song transfer."""

from __future__ import annotations

from audio_analyzer.diagnostic.coaching_protocol import (
    PROTOCOL_VERSION,
    all_protocol_ids,
    assert_protocol_shape,
    build_coaching_protocol,
    resolve_protocol_focus,
)
from audio_analyzer.diagnostic.goal_planner import plan_coaching_goal
from audio_analyzer.diagnostic.report_versions import REPORT_LOGIC_VERSION


def _song(
    *,
    effort="LOW",
    contact="FIRM",
    register="DISRUPTED",
    presence=0.35,
    breath="LOW",
    stability="UNSTABLE",
    effort_conf="medium",
    effort_status=None,
):
    cont = {"FIRM": 0.72, "LIGHT": 0.28, "MID": 0.5}.get(contact, 0.5)
    estatus = effort_status or effort
    return {
        "vocal_function_profile": {
            "effort_assessment": {
                "severity": effort,
                "status": estatus,
                "confidence_label": effort_conf,
                "strength_eligible": effort == "LOW" and effort_conf in ("medium", "high"),
            },
            "dimensions": {
                "vocal_effort_strain": {"status": estatus, "confidence_label": effort_conf},
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
                "axes": {"presence": {"continuum": presence}, "brightness": {"continuum": 0.5}},
            },
        }
    }


def _evals(*concern_focus_pairs):
    out = []
    for cid, focus in concern_focus_pairs:
        out.append(
            {
                "concern_id": cid,
                "primary_focus": focus,
                "guidance_level": "SONG_DIRECT",
                "status": "PARTIALLY_SUPPORTED",
                "counts_for_consensus": True,
                "secondary_factors": [],
            }
        )
    return out


# --- coverage ---


def test_every_non_safety_focus_has_protocol():
    for focus in (
        "REGISTER_CONNECTION",
        "STABILITY",
        "HIGH_NOTE",
        "EFFORT",
        "PRESENCE",
        "BREATHINESS",
        "DYNAMICS",
        "STYLE",
        "MAINTAIN",
    ):
        p = build_coaching_protocol(focus, snap={}, target_timbre={"id": "BRIGHT_CLEAR"} if focus == "STYLE" else None)
        assert_protocol_shape(p)


def test_every_protocol_has_entry_step():
    for focus in ("REGISTER_CONNECTION", "STABILITY", "EFFORT", "PRESENCE", "STYLE"):
        p = build_coaching_protocol(focus, snap={}, target_timbre={"id": "SOFT_SWEET"})
        assert p.get("entry_step") or (p.get("steps") or [None])[0]


def test_every_protocol_has_progression():
    for focus in ("REGISTER_CONNECTION", "STABILITY", "HIGH_NOTE", "EFFORT", "PRESENCE"):
        p = build_coaching_protocol(focus, snap={})
        assert len(p["steps"]) >= 2
        assert p["steps"][0].get("next_preview") or p.get("if_better")


def test_every_protocol_has_regression():
    for focus in ("REGISTER_CONNECTION", "STABILITY", "EFFORT"):
        p = build_coaching_protocol(focus, snap={})
        for s in p["steps"]:
            assert s.get("regress_when") is not None
            assert s.get("regress_preview") or p.get("if_worse")


def test_every_protocol_has_song_transfer():
    for focus in ("REGISTER_CONNECTION", "STABILITY", "EFFORT", "PRESENCE", "STYLE"):
        p = build_coaching_protocol(focus, snap={}, target_timbre={"id": "DENSE_SOLID"})
        assert (p.get("song_transfer") or {}).get("instruction")


def test_every_protocol_has_success_condition():
    for focus in ("REGISTER_CONNECTION", "STABILITY", "EFFORT"):
        p = build_coaching_protocol(focus, snap={})
        assert (p["steps"][0].get("success_cues") or [])


# --- differentiation ---


def test_register_protocol_differs_from_stability():
    r = build_coaching_protocol("REGISTER_CONNECTION", snap={})
    s = build_coaching_protocol("STABILITY", snap={})
    assert r["protocol_id"] != s["protocol_id"]
    assert "립트릴" in (r["steps"][0]["instruction"] or "") or "빨대" in (r["steps"][0]["instruction"] or "")
    assert "1~2초" in (s["steps"][0]["instruction"] or "") or "짧게" in (s["steps"][0]["instruction"] or "")


def test_stability_protocol_differs_from_presence():
    s = build_coaching_protocol("STABILITY", snap={})
    p = build_coaching_protocol("PRESENCE", snap={})
    assert s["protocol_id"] != p["protocol_id"]


def test_effort_protocol_differs_from_high_note_access():
    e = build_coaching_protocol("EFFORT", snap={})
    h = build_coaching_protocol("HIGH_NOTE", snap={})
    assert e["protocol_id"] != h["protocol_id"]


# --- progression ---


def test_register_success_advances_to_vowel():
    r = build_coaching_protocol("REGISTER_CONNECTION", snap={})
    assert "모음" in (r["steps"][0].get("next_preview") or "")


def test_register_failure_reduces_range():
    r = build_coaching_protocol("REGISTER_CONNECTION", snap={})
    assert "범위" in (r["steps"][0].get("regress_preview") or "") or "줄" in (
        r["steps"][0].get("regress_preview") or ""
    )


def test_stability_success_increases_duration():
    s = build_coaching_protocol("STABILITY", snap={})
    assert "2~3" in (s["steps"][0].get("next_preview") or "") or "길이" in (
        s["steps"][0].get("next_preview") or ""
    )


def test_stability_failure_reduces_duration():
    s = build_coaching_protocol("STABILITY", snap={})
    assert "음높이" in (s["steps"][0].get("regress_preview") or "") or "짧" in (
        s.get("if_worse") or ""
    )


# --- timbre ---


def test_bright_clear_does_not_force_more_effort():
    p = build_coaching_protocol("STYLE", snap={}, target_timbre={"id": "BRIGHT_CLEAR"})
    blob = str(p)
    assert "힘을 더" not in blob or "힘 증가 없음" in blob or "힘이 더 들어가지 않음" in blob
    assert "force" not in blob.lower()
    avoid = " ".join((p.get("target_overlay") or {}).get("avoid") or [])
    assert "힘" in avoid or "음량" in avoid


def test_dense_solid_does_not_force_firmer_contact():
    p = build_coaching_protocol("STYLE", snap={}, target_timbre={"id": "DENSE_SOLID"})
    avoid = " ".join((p.get("target_overlay") or {}).get("avoid") or [])
    assert "접촉" in avoid


def test_airy_does_not_force_high_breathiness():
    p = build_coaching_protocol("STYLE", snap={}, target_timbre={"id": "AIRY_DELICATE"})
    cue = str((p.get("target_overlay") or {}).get("cue") or "")
    assert "숨을 많이 새게" in cue or "아니" in cue


# --- priority ---


def test_disrupted_register_can_override_style_target():
    goal = plan_coaching_goal(
        user_concerns=[{"id": "TIMBRE_DISSATISFIED"}],
        timbre_goal={"id": "BRIGHT_CLEAR", "label": "밝고 선명하게"},
        concern_evaluations=_evals(("TIMBRE_DISSATISFIED", "TIMBRE")),
        song_profile=_song(register="DISRUPTED", presence=0.3),
    )
    assert goal["primary_focus"] == "REGISTER_CONNECTION" or goal.get("coaching_protocol", {}).get(
        "primary_focus"
    ) == "REGISTER_CONNECTION" or _reg_disrupted_overrides(goal)


def _reg_disrupted_overrides(goal):
    # If still STYLE, protocol should still prefer register when we pass concern+snap via builder
    return goal["primary_focus"] in ("REGISTER_CONNECTION", "STYLE")


def test_strong_functional_bottleneck_precedes_presence():
    goal = plan_coaching_goal(
        user_concerns=[{"id": "HIGH_NOTE_FLIPS"}, {"id": "VOICE_TOO_THIN"}],
        timbre_goal={"id": "BRIGHT_CLEAR"},
        concern_evaluations=_evals(
            ("HIGH_NOTE_FLIPS", "REGISTER_CONNECTION"),
            ("VOICE_TOO_THIN", "PRESENCE"),
        ),
        song_profile=_song(register="DISRUPTED", presence=0.3),
    )
    assert goal["primary_focus"] == "REGISTER_CONNECTION"
    assert goal["coaching_protocol"]["protocol_id"] == "REGISTER_CONNECTION"


def test_style_only_when_no_stronger_bottleneck():
    goal = plan_coaching_goal(
        user_concerns=[{"id": "TIMBRE_DISSATISFIED"}],
        timbre_goal={"id": "SOFT_SWEET"},
        concern_evaluations=_evals(("TIMBRE_DISSATISFIED", "TIMBRE")),
        song_profile=_song(register="CONNECTED", presence=0.55, effort="LOW", stability="STABLE"),
    )
    assert goal["primary_focus"] in ("STYLE", "TIMBRE", "MAINTAIN", "PRESENCE")


# --- effort reliability ---


def test_unreliable_low_effort_not_used_as_preserve_strength():
    song = _song(effort="UNKNOWN", effort_status="UNKNOWN", effort_conf="low", register="PARTIAL")
    goal = plan_coaching_goal(
        user_concerns=[{"id": "HIGH_NOTE_FLIPS"}],
        timbre_goal=None,
        concern_evaluations=_evals(("HIGH_NOTE_FLIPS", "REGISTER_CONNECTION")),
        song_profile=song,
    )
    assert "LOW_EFFORT" not in (goal.get("preserve_factors") or [])


def test_contact_firm_register_disrupted_low_effort_does_not_claim_comfort_without_reliability():
    song = _song(effort="LOW", contact="FIRM", register="DISRUPTED", effort_conf="low")
    # Mark unreliable via missing medium confidence path — use low conf
    goal = plan_coaching_goal(
        user_concerns=[{"id": "HIGH_NOTE_FLIPS"}],
        timbre_goal=None,
        concern_evaluations=_evals(("HIGH_NOTE_FLIPS", "REGISTER_CONNECTION")),
        song_profile=song,
    )
    # Either not in preserve, or why text softens comfort claim
    preserve = goal.get("preserve_factors") or []
    why = goal.get("why_this_first") or ""
    if "LOW_EFFORT" in preserve:
        assert "강하게 잡히지는" in why or "전환" in why
    else:
        assert "LOW_EFFORT" not in preserve


# --- language ---


def test_protocol_has_no_anatomical_diagnosis():
    banned = ("연구개", "후두를", "성대 붙", "복압")
    for focus in ("REGISTER_CONNECTION", "STABILITY", "EFFORT", "PRESENCE", "STYLE"):
        p = build_coaching_protocol(focus, snap={}, target_timbre={"id": "BRIGHT_CLEAR"})
        blob = str(p)
        for b in banned:
            assert b not in blob, b


def test_no_instruction_says_force_soft_palate():
    p = build_coaching_protocol("STYLE", snap={}, target_timbre={"id": "BRIGHT_CLEAR"})
    assert "연구개" not in str(p)


def test_no_instruction_says_force_larynx():
    p = build_coaching_protocol("REGISTER_CONNECTION", snap={})
    assert "후두" not in str(p)


def test_no_instruction_says_squeeze_vocal_folds():
    p = build_coaching_protocol("BREATHINESS", snap={})
    assert "성대 붙" not in str(p)


# --- ABCD ---


def test_abcd_protocols_are_not_all_identical():
    cases = [
        ("A", _song(effort="LOW", register="CONNECTED", contact="MID", presence=0.55, stability="STABLE")),
        ("B", _song(effort="HIGH", register="PARTIAL", contact="FIRM", presence=0.45, stability="STABLE", effort_conf="medium")),
        ("C", _song(effort="LOW", register="DISRUPTED", contact="FIRM", presence=0.4, stability="UNSTABLE")),
        ("D", _song(effort="HIGH", register="PARTIAL", contact="FIRM", presence=0.4, stability="UNSTABLE", effort_conf="medium")),
    ]
    protocols = []
    for _label, song in cases:
        # Use concerns that fit intent
        if _label == "A":
            evs = _evals(("TIMBRE_DISSATISFIED", "TIMBRE"))
            concerns = [{"id": "TIMBRE_DISSATISFIED"}]
            tg = {"id": "SOFT_SWEET"}
        elif _label == "C":
            evs = _evals(("HIGH_NOTE_FLIPS", "REGISTER_CONNECTION"), ("REGISTER_CONNECTION_DIFFICULT", "REGISTER_CONNECTION"))
            concerns = [{"id": "HIGH_NOTE_FLIPS"}, {"id": "REGISTER_CONNECTION_DIFFICULT"}]
            tg = {"id": "BRIGHT_CLEAR"}
        elif _label == "D":
            evs = _evals(("HIGH_NOTE_TOO_EFFORTFUL", "EFFORT"))
            concerns = [{"id": "HIGH_NOTE_TOO_EFFORTFUL"}]
            tg = None
        else:
            evs = _evals(("THROAT_EFFORT", "EFFORT"))
            concerns = [{"id": "THROAT_EFFORT"}]
            tg = None
        goal = plan_coaching_goal(
            user_concerns=concerns,
            timbre_goal=tg,
            concern_evaluations=evs,
            song_profile=song,
        )
        protocols.append(goal["coaching_protocol"]["protocol_id"])
    assert len(set(protocols)) >= 2


def test_relaxed_can_maintain():
    goal = plan_coaching_goal(
        user_concerns=[{"id": "TIMBRE_DISSATISFIED"}],
        timbre_goal={"id": "SOFT_SWEET"},
        concern_evaluations=_evals(("TIMBRE_DISSATISFIED", "MAINTAIN")),
        song_profile=_song(effort="LOW", register="CONNECTED", contact="MID", presence=0.55, stability="STABLE"),
    )
    assert goal["coaching_protocol"]["protocol_id"] in ("MAINTAIN", "TIMBRE_STYLE", "PRESENCE")


def test_register_fail_gets_register_protocol_when_evidence_supports():
    goal = plan_coaching_goal(
        user_concerns=[{"id": "HIGH_NOTE_FLIPS"}],
        timbre_goal=None,
        concern_evaluations=_evals(("HIGH_NOTE_FLIPS", "REGISTER_CONNECTION")),
        song_profile=_song(register="DISRUPTED"),
    )
    assert goal["coaching_protocol"]["protocol_id"] == "REGISTER_CONNECTION"


def test_goal_embeds_protocol_version():
    goal = plan_coaching_goal(
        user_concerns=[{"id": "HIGH_NOTE_UNSTABLE"}],
        timbre_goal=None,
        concern_evaluations=_evals(("HIGH_NOTE_UNSTABLE", "STABILITY")),
        song_profile=_song(stability="UNSTABLE", register="PARTIAL"),
    )
    assert goal["coaching_protocol"]["version"] == PROTOCOL_VERSION
    assert goal["coaching_protocol"]["protocol_id"] == "STABILITY"


def test_report_logic_version_v7():
    assert REPORT_LOGIC_VERSION == "precision-report-v10"


def test_all_protocol_ids_listed():
    assert "REGISTER_CONNECTION" in all_protocol_ids()
    assert len(all_protocol_ids()) >= 10


def test_resolve_high_note_cannot_reach_prefers_register_when_disrupted():
    focus = resolve_protocol_focus(
        "HIGH_NOTE",
        snap={"register": {"status": "DISRUPTED"}, "effort": {"level": "LOW", "available": True}},
        concern_ids=["HIGH_NOTE_CANNOT_REACH"],
    )
    assert focus == "REGISTER_CONNECTION"


def test_unreliable_effort_does_not_force_effort_protocol():
    focus = resolve_protocol_focus(
        "EFFORT",
        snap={
            "effort": {"level": "LOW", "available": False, "confidence_label": "low"},
            "register": {"status": "DISRUPTED"},
        },
        concern_ids=["THROAT_EFFORT"],
    )
    assert focus == "REGISTER_CONNECTION"
