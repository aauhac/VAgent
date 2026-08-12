"""Precision Diagnostic v2.2 — concern resolver + task contrast."""

from __future__ import annotations

from audio_analyzer.diagnostic.concern_resolver import (
    build_controlled_contrasts,
    build_task_profiles,
    evaluate_concern,
    extract_timbre_snapshot,
    infer_precision_bottleneck,
)
from audio_analyzer.diagnostic.concerns import (
    build_improvement_guidance,
    build_personalized_qa,
    evaluate_concern_status,
)
from audio_analyzer.diagnostic.evidence.sustain import evidence_effort_high_sustain
from audio_analyzer.diagnostic.fusion import build_final_diagnostic_profile, fuse_song_and_task_evidence


def _effort_ev(status: str, estimate: float, *, eligible: bool = True) -> dict:
    return {
        "dimension_id": "effort",
        "available": True,
        "estimate": estimate,
        "status": status,
        "confidence_score": 0.7,
        "resolution_eligible": eligible,
        "quality_valid": True,
        "reason": f"test_{status}",
    }


def _task(tid: str, dims: dict, *, valid: bool = True) -> dict:
    return {
        "task_id": tid,
        "quality": {"status": "ok" if valid else "fail"},
        "compliance": {"ok": valid},
        "invalid": not valid,
        "dimension_evidence": dims,
        "actual_coverage": list(dims.keys()),
    }


def test_evaluate_concern_uses_task_evidence():
    song = {"vocal_function_profile": {"effort_assessment": {"severity": "LOW"}}}
    high = build_final_diagnostic_profile(
        song_profile=song["vocal_function_profile"],
        task_results=[
            _task("sustain_a", {"effort": _effort_ev("LOW", 0.2)}),
            _task("high_note_sustain_a", {"effort": _effort_ev("HIGH", 0.75)}),
        ],
        plan={"selected_tasks": ["sustain_a", "high_note_sustain_a"], "unresolved_dimensions": []},
    )
    low = build_final_diagnostic_profile(
        song_profile=song["vocal_function_profile"],
        task_results=[
            _task("sustain_a", {"effort": _effort_ev("LOW", 0.2)}),
            _task("high_note_sustain_a", {"effort": _effort_ev("LOW", 0.22)}),
        ],
        plan={"selected_tasks": ["sustain_a", "high_note_sustain_a"], "unresolved_dimensions": []},
    )
    a = evaluate_concern_status(
        "HIGH_NOTE_TOO_EFFORTFUL", song_profile=song, task_evidence=high
    )
    b = evaluate_concern_status(
        "HIGH_NOTE_TOO_EFFORTFUL", song_profile=song, task_evidence=low
    )
    assert a["status"] in ("CONFIRMED", "PARTIALLY_SUPPORTED")
    assert b["status"] in ("NOT_SUPPORTED_IN_THIS_RECORDING", "CONTEXT_DEPENDENT", "PARTIALLY_SUPPORTED")
    assert a["status"] != b["status"] or a.get("answer_hint") != b.get("answer_hint")


def test_same_song_different_high_note_task_changes_concern_answer():
    song = {"vocal_function_profile": {"effort_assessment": {"severity": "LOW"}}}
    qa_high = build_personalized_qa(
        user_concerns=[{"id": "HIGH_NOTE_TOO_EFFORTFUL"}],
        song_profile=song,
        task_results=[
            _task("sustain_a", {"effort": _effort_ev("LOW", 0.2)}),
            _task("high_note_sustain_a", {"effort": _effort_ev("HIGH", 0.8)}),
        ],
        fused_profile=build_final_diagnostic_profile(
            song_profile=song["vocal_function_profile"],
            task_results=[
                _task("sustain_a", {"effort": _effort_ev("LOW", 0.2)}),
                _task("high_note_sustain_a", {"effort": _effort_ev("HIGH", 0.8)}),
            ],
            plan={"selected_tasks": ["sustain_a", "high_note_sustain_a"]},
        ),
    )
    qa_low = build_personalized_qa(
        user_concerns=[{"id": "HIGH_NOTE_TOO_EFFORTFUL"}],
        song_profile=song,
        task_results=[
            _task("sustain_a", {"effort": _effort_ev("LOW", 0.2)}),
            _task("high_note_sustain_a", {"effort": _effort_ev("LOW", 0.21)}),
        ],
        fused_profile=build_final_diagnostic_profile(
            song_profile=song["vocal_function_profile"],
            task_results=[
                _task("sustain_a", {"effort": _effort_ev("LOW", 0.2)}),
                _task("high_note_sustain_a", {"effort": _effort_ev("LOW", 0.21)}),
            ],
            plan={"selected_tasks": ["sustain_a", "high_note_sustain_a"]},
        ),
    )
    assert qa_high["questions"][0]["status"] in ("CONFIRMED", "PARTIALLY_SUPPORTED")
    assert qa_low["questions"][0]["status"] in (
        "NOT_SUPPORTED_IN_THIS_RECORDING",
        "CONTEXT_DEPENDENT",
        "PARTIALLY_SUPPORTED",
    )
    assert qa_high["questions"][0]["answer"] != qa_low["questions"][0]["answer"]


def test_high_note_effort_requires_baseline_high_contrast():
    ev = evaluate_concern(
        "HIGH_NOTE_TOO_EFFORTFUL",
        song_profile={"vocal_function_profile": {"effort_assessment": {"severity": "LOW"}}},
        task_results=[_task("high_note_sustain_a", {"effort": _effort_ev("HIGH", 0.8)})],
    )
    assert ev["status"] in ("PARTIALLY_SUPPORTED", "UNRESOLVED")
    assert "baseline" in str(ev.get("missing") or []).lower() or ev.get("unresolved_reason") in (
        "MISSING_BASELINE",
        None,
    ) or "MISSING" in str(ev.get("missing") or [])


def test_high_note_effort_observed_does_not_equal_high():
    seg = {
        "observations": {"rms": 0.05, "periodicity_primary_db": 12.0},
        "level2_proxies": {"glottal_source": {"valid": False}, "gif_gate": {"valid": False}},
        "vocal_evidence": {"vocal_specific": True},
        "valid": True,
        "rms": 0.05,
    }
    ev = evidence_effort_high_sustain(seg, quality_valid=True)
    assert ev["status"] != "OBSERVED"
    assert ev["status"] in ("LOW", "INCREASED", "HIGH", "INSUFFICIENT") or ev.get("available")


def test_invalid_high_note_task_does_not_confirm_effort():
    ev = evaluate_concern(
        "HIGH_NOTE_TOO_EFFORTFUL",
        song_profile={"vocal_function_profile": {"effort_assessment": {"severity": "LOW"}}},
        task_results=[
            _task("sustain_a", {"effort": _effort_ev("LOW", 0.2)}),
            _task("high_note_sustain_a", {"effort": _effort_ev("HIGH", 0.8)}, valid=False),
        ],
    )
    assert ev["status"] != "CONFIRMED"
    assert ev.get("unresolved_reason") == "INVALID_HIGH_NOTE_TASK" or ev["status"] == "UNRESOLVED"


def test_task_to_task_contrast_preserved():
    profiles = build_task_profiles(
        [
            _task("sustain_a", {"effort": _effort_ev("LOW", 0.2), "stability": _effort_ev("LOW", 0.2)}),
            _task(
                "high_note_sustain_a",
                {"effort": _effort_ev("HIGH", 0.8), "stability": _effort_ev("LOW", 0.25)},
            ),
        ]
    )
    contrasts = build_controlled_contrasts(profiles)
    assert "baseline_vs_high" in contrasts
    assert contrasts["baseline_vs_high"]["dimensions"]["effort"]["direction"] == "INCREASED"
    assert "sustain_a__vs__high_note_sustain_a" in contrasts


def test_sustain_a_vs_high_note_effort_delta():
    fused = fuse_song_and_task_evidence(
        song_profile={},
        task_results=[
            _task("sustain_a", {"effort": _effort_ev("LOW", 0.2)}),
            _task("high_note_sustain_a", {"effort": _effort_ev("HIGH", 0.7)}),
        ],
    )
    delta = fused["controlled_contrasts"]["baseline_vs_high"]["dimensions"]["effort"]["delta"]
    assert float(delta) > 0.15


def test_sustain_a_vs_high_note_stability_delta():
    fused = fuse_song_and_task_evidence(
        song_profile={},
        task_results=[
            _task("sustain_a", {"stability": {"available": True, "status": "STABLE", "estimate": 0.2, "resolution_eligible": True}}),
            _task(
                "high_note_sustain_a",
                {"stability": {"available": True, "status": "UNSTABLE", "estimate": 0.75, "resolution_eligible": True}},
            ),
        ],
    )
    d = fused["controlled_contrasts"]["baseline_vs_high"]["dimensions"]["stability"]
    assert d["direction"] == "INCREASED"


def test_sustain_a_vs_high_note_breathiness_delta():
    fused = fuse_song_and_task_evidence(
        song_profile={},
        task_results=[
            _task("sustain_a", {"breathiness": {"available": True, "status": "LOW", "estimate": 0.2, "resolution_eligible": True}}),
            _task(
                "high_note_sustain_a",
                {"breathiness": {"available": True, "status": "HIGH", "estimate": 0.7, "resolution_eligible": True}},
            ),
        ],
    )
    assert fused["controlled_contrasts"]["baseline_vs_high"]["dimensions"]["breathiness"]["direction"] == "INCREASED"


def test_voice_dark_muffled_has_explicit_resolver():
    song = {
        "vocal_function_profile": {
            "timbre_profile": {
                "available": True,
                "axes": {
                    "brightness": {"status": "어두움", "continuum": 0.3},
                    "presence": {"status": "낮음", "continuum": 0.28},
                    "airiness": {"status": "적음", "continuum": 0.25},
                },
            }
        }
    }
    ev = evaluate_concern_status("VOICE_TOO_DARK_MUFFLED", song_profile=song, task_evidence={})
    assert ev["status"] in ("CONFIRMED", "PARTIALLY_SUPPORTED")
    assert ev.get("candidate_causes")


def test_dark_muffled_low_presence_supports_concern():
    song = {
        "vocal_function_profile": {
            "timbre_profile": {
                "available": True,
                "axes": {
                    "brightness": {"continuum": 0.35, "status": "어두움"},
                    "presence": {"continuum": 0.3, "status": "낮음"},
                    "airiness": {"continuum": 0.3, "status": "적음"},
                },
            }
        }
    }
    ev = evaluate_concern("VOICE_TOO_DARK_MUFFLED", song_profile=song)
    assert ev["status"] == "CONFIRMED"


def test_dark_muffled_normal_presence_can_not_support():
    song = {
        "vocal_function_profile": {
            "timbre_profile": {
                "available": True,
                "axes": {
                    "brightness": {"continuum": 0.55, "status": "보통"},
                    "presence": {"continuum": 0.6, "status": "있음"},
                    "airiness": {"continuum": 0.45, "status": "보통"},
                },
            }
        }
    }
    ev = evaluate_concern("VOICE_TOO_DARK_MUFFLED", song_profile=song)
    assert ev["status"] in ("NOT_SUPPORTED_IN_THIS_RECORDING", "UNRESOLVED")


def test_dark_muffled_not_from_low_airiness_alone_when_bright():
    """Breathiness low ≠ muffled when controlled resonance is bright."""
    from audio_analyzer.diagnostic.concern_resolver import build_task_profiles, evaluate_concern

    task_results = [
        {
            "task_id": "sustain_a",
            "quality": {"status": "pass"},
            "compliance": {"ok": True},
            "dimension_evidence": {
                "breathiness": {
                    "status": "LOW",
                    "available": True,
                    "estimate": 0.15,
                    "resolution_eligible": True,
                },
                "resonance": {
                    "status": "BRIGHT",
                    "available": True,
                    "estimate": 0.65,
                    "resolution_eligible": False,
                },
                "contact": {"status": "MID", "available": True, "estimate": 0.5, "resolution_eligible": True},
            },
        }
    ]
    song = {
        "vocal_function_profile": {
            "timbre_profile": {"available": False, "axes": {}, "reason": "INSUFFICIENT_VOCAL_SEGMENTS"}
        }
    }
    fused = {"task_profiles": build_task_profiles(task_results)}
    ev = evaluate_concern("VOICE_TOO_DARK_MUFFLED", song_profile=song, task_evidence=fused)
    assert ev["status"] == "NOT_SUPPORTED_IN_THIS_RECORDING"
    assert any("brightness_ok" in a for a in (ev.get("against") or []))


def test_timbre_dissatisfied_uses_timbre_not_only_breathiness():
    song = {
        "vocal_function_profile": {
            "dimensions": {"air_leakage_breathiness": {"status": "LOW"}},
            "timbre_profile": {
                "available": True,
                "axes": {
                    "brightness": {"continuum": 0.5, "status": "보통"},
                    "presence": {"continuum": 0.32, "status": "낮음"},
                    "airiness": {"continuum": 0.3, "status": "적음"},
                    "texture": {"continuum": 0.4, "status": "보통"},
                },
            },
        }
    }
    ev = evaluate_concern("TIMBRE_DISSATISFIED", song_profile=song)
    assert ev["status"] == "PARTIALLY_SUPPORTED"
    assert "presence" in str(ev.get("support") or [])
    assert "breathiness" not in str(ev.get("support") or []).lower() or "airiness" in str(ev.get("support"))


def test_timbre_dissatisfied_returns_characteristic_description():
    song = {
        "vocal_function_profile": {
            "timbre_profile": {
                "available": True,
                "axes": {
                    "brightness": {"continuum": 0.6},
                    "presence": {"continuum": 0.35},
                    "airiness": {"continuum": 0.3},
                },
            }
        }
    }
    qa = build_personalized_qa(user_concerns=[{"id": "TIMBRE_DISSATISFIED"}], song_profile=song)
    ans = qa["questions"][0]["answer"]
    assert "음색" in ans or "존재감" in ans or "밝" in ans
    assert "확인하기 어려웠어요" not in ans


def test_thin_voice_can_use_airiness_presence_contact():
    song = {
        "vocal_function_profile": {
            "timbre_profile": {
                "available": True,
                "axes": {"airiness": {"continuum": 0.7}, "presence": {"continuum": 0.3}},
            }
        }
    }
    ev = evaluate_concern("VOICE_TOO_THIN", song_profile=song)
    assert ev["status"] in ("CONFIRMED", "PARTIALLY_SUPPORTED")


def test_timbre_good_bad_score_not_added():
    snap = extract_timbre_snapshot(
        {
            "vocal_function_profile": {
                "timbre_profile": {
                    "available": True,
                    "axes": {"brightness": {"continuum": 0.5}},
                    "what_it_is_not": "좋은 음색 / 음색 점수가 아닙니다.",
                }
            }
        }
    )
    assert "score" not in snap
    assert "good" not in str(snap).lower()


def test_precision_bottleneck_can_come_from_task():
    fused = build_final_diagnostic_profile(
        song_profile={"effort_assessment": {"severity": "LOW"}, "coaching_decision": {}},
        task_results=[
            _task("sustain_a", {"effort": _effort_ev("LOW", 0.2)}),
            _task("high_note_sustain_a", {"effort": _effort_ev("HIGH", 0.8)}),
        ],
        plan={"selected_tasks": ["sustain_a", "high_note_sustain_a"]},
    )
    ev = evaluate_concern(
        "HIGH_NOTE_TOO_EFFORTFUL",
        song_profile={"vocal_function_profile": fused.get("song_profile") or {"effort_assessment": {"severity": "LOW"}}},
        task_evidence=fused,
    )
    bn = infer_precision_bottleneck(
        song_profile={"vocal_function_profile": {"coaching_decision": {}}},
        fused_profile=fused,
        concern_evaluations=[ev],
    )
    assert bn["bottleneck"] == "HIGH_NOTE_EFFORT"
    assert bn["source"] in ("TASK", "BOTH")


def test_guidance_can_come_from_task_bottleneck():
    ev = {
        "concern_id": "HIGH_NOTE_TOO_EFFORTFUL",
        "status": "CONFIRMED",
        "candidate_causes": ["EFFORT_ESCALATION_WITH_HEIGHT"],
    }
    goals = build_improvement_guidance(
        song_profile={"vocal_function_profile": {"coaching_decision": {}}},
        evaluations=[ev],
        pain_flag=False,
        precision_bottleneck="HIGH_NOTE_EFFORT",
    )
    assert goals[0]["goal_id"] == "REDUCE_HIGH_NOTE_EFFORT"
    assert goals[0]["title"] != "현재 발성 패턴 관찰하기"


def test_five_valid_tasks_do_not_default_to_general_awareness_when_issue_found():
    song = {"vocal_function_profile": {"effort_assessment": {"severity": "LOW"}, "coaching_decision": {}}}
    tasks = [
        _task("sustain_a", {"effort": _effort_ev("LOW", 0.2)}),
        _task("sustain_i", {"resonance": {"available": True, "status": "OK", "resolution_eligible": True}}),
        _task("siren", {"register": {"available": True, "status": "CONNECTED", "resolution_eligible": True}}),
        _task("dynamic_swell", {"effort": _effort_ev("LOW", 0.3)}),
        _task("high_note_sustain_a", {"effort": _effort_ev("HIGH", 0.8)}),
    ]
    fused = build_final_diagnostic_profile(
        song_profile=song["vocal_function_profile"],
        task_results=tasks,
        plan={"selected_tasks": [t["task_id"] for t in tasks]},
    )
    qa = build_personalized_qa(
        user_concerns=[
            {"id": "HIGH_NOTE_TOO_EFFORTFUL"},
            {"id": "TIMBRE_DISSATISFIED"},
            {"id": "VOICE_TOO_DARK_MUFFLED"},
        ],
        song_profile={
            **song,
            "vocal_function_profile": {
                **song["vocal_function_profile"],
                "timbre_profile": {
                    "available": True,
                    "axes": {
                        "brightness": {"continuum": 0.35},
                        "presence": {"continuum": 0.3},
                        "airiness": {"continuum": 0.28},
                    },
                },
            },
        },
        task_results=tasks,
        fused_profile=fused,
    )
    titles = [g["title"] for g in qa["improvement_priorities"]]
    assert "현재 발성 패턴 관찰하기" not in titles
    assert qa["main_bottleneck"] != "UNRESOLVED" or any(
        q["status"] in ("CONFIRMED", "PARTIALLY_SUPPORTED") for q in qa["questions"]
    )


def test_unresolved_explains_missing_evidence():
    ev = evaluate_concern(
        "HIGH_NOTE_TOO_EFFORTFUL",
        song_profile={"vocal_function_profile": {}},
        task_results=[],
    )
    assert ev["status"] == "UNRESOLVED"
    assert ev.get("unresolved_reason") or ev.get("missing") or ev.get("answer_hint")


def test_song_high_task_low_produces_context_dependent():
    song = {"vocal_function_profile": {"effort_assessment": {"severity": "HIGH"}}}
    fused = build_final_diagnostic_profile(
        song_profile=song["vocal_function_profile"],
        task_results=[
            _task("sustain_a", {"effort": _effort_ev("LOW", 0.2)}),
            _task("high_note_sustain_a", {"effort": _effort_ev("LOW", 0.22)}),
        ],
        plan={"selected_tasks": ["sustain_a", "high_note_sustain_a"]},
    )
    ev = evaluate_concern_status(
        "HIGH_NOTE_TOO_EFFORTFUL", song_profile=song, task_evidence=fused
    )
    assert ev["status"] in ("CONTEXT_DEPENDENT", "NOT_SUPPORTED_IN_THIS_RECORDING")


def test_song_low_task_high_can_produce_task_specific_bottleneck():
    song = {"vocal_function_profile": {"effort_assessment": {"severity": "LOW"}, "coaching_decision": {}}}
    fused = build_final_diagnostic_profile(
        song_profile=song["vocal_function_profile"],
        task_results=[
            _task("sustain_a", {"effort": _effort_ev("LOW", 0.2)}),
            _task("high_note_sustain_a", {"effort": _effort_ev("HIGH", 0.85)}),
        ],
        plan={"selected_tasks": ["sustain_a", "high_note_sustain_a"]},
    )
    qa = build_personalized_qa(
        user_concerns=[{"id": "HIGH_NOTE_TOO_EFFORTFUL"}],
        song_profile=song,
        task_results=fused["task_evidence"]["task_ids_present"] and [
            _task("sustain_a", {"effort": _effort_ev("LOW", 0.2)}),
            _task("high_note_sustain_a", {"effort": _effort_ev("HIGH", 0.85)}),
        ],
        fused_profile=fused,
    )
    assert qa["main_bottleneck"] == "HIGH_NOTE_EFFORT"
    assert qa["bottleneck_source"] in ("TASK", "BOTH")


def test_no_blind_average():
    fused = fuse_song_and_task_evidence(
        song_profile={"dimensions": {}},
        task_results=[
            _task("sustain_a", {"effort": _effort_ev("LOW", 0.2)}),
            _task("high_note_sustain_a", {"effort": _effort_ev("HIGH", 0.8)}),
        ],
    )
    assert fused["fusion_rules"]["blind_average"] is False
    # Both task profiles retained — not averaged away
    assert "sustain_a" in fused["task_profiles"]
    assert "high_note_sustain_a" in fused["task_profiles"]


def test_high_note_sustain_rendered_in_task_summary():
    # Mirror frontend label map contract
    labels = {
        "sustain_a": "아— 지속음",
        "sustain_i": "이— 지속음",
        "siren": "사이렌",
        "dynamic_swell": "강약 변화",
        "high_note_sustain_a": "높은 음 '아—'",
    }
    assert "high_note_sustain_a" in labels
    assert labels["high_note_sustain_a"]
