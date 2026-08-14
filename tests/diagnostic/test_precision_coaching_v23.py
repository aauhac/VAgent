"""Precision Diagnostic v2.3 — actionable coaching layer tests."""

from __future__ import annotations

from audio_analyzer.diagnostic.coaching import (
    banned_observation_fallback,
    build_concern_coaching,
    build_precision_coaching_plan,
    derive_precision_strengths,
    map_evidence_list,
    user_facing_evidence_token,
)
from audio_analyzer.diagnostic.concerns import build_personalized_qa, evaluate_concern_status
from audio_analyzer.diagnostic.concern_resolver import (
    build_controlled_contrasts,
    build_task_profiles,
    evaluate_concern,
)


def _task(tid: str, dims: dict) -> dict:
    return {
        "task_id": tid,
        "quality": {"status": "pass"},
        "compliance": {"ok": True},
        "dimension_evidence": {
            k: {
                "available": True,
                "resolution_eligible": True,
                **v,
            }
            for k, v in dims.items()
        },
    }


def _fused(tasks: list[dict]) -> dict:
    profiles = build_task_profiles(tasks)
    return {
        "task_profiles": profiles,
        "controlled_contrasts": build_controlled_contrasts(profiles),
    }


def test_not_supported_high_note_produces_maintain_coaching():
    tasks = [
        _task("sustain_a", {"effort": {"status": "LOW", "estimate": 0.3}}),
        _task("high_note_sustain_a", {"effort": {"status": "LOW", "estimate": 0.4}}),
    ]
    fused = _fused(tasks)
    song = {"vocal_function_profile": {"effort_assessment": {"severity": "LOW"}}}
    ev = evaluate_concern(
        "HIGH_NOTE_TOO_EFFORTFUL", song_profile=song, task_evidence=fused
    )
    assert ev["status"] == "NOT_SUPPORTED_IN_THIS_RECORDING"
    coach = build_concern_coaching(ev, fused_profile=fused)
    assert coach["coaching_mode"] == "MAINTAIN"
    title = (coach.get("practice_direction") or {}).get("title") or ""
    blob = title + (coach.get("takeaway") or "") + str(coach.get("practice_direction"))
    assert "고음" in blob or "편안" in blob
    assert not banned_observation_fallback(blob)


def test_confirmed_high_note_produces_correct_coaching():
    tasks = [
        _task("sustain_a", {"effort": {"status": "LOW", "estimate": 0.25}}),
        _task("high_note_sustain_a", {"effort": {"status": "HIGH", "estimate": 0.8}}),
    ]
    fused = _fused(tasks)
    song = {"vocal_function_profile": {"effort_assessment": {"severity": "LOW"}}}
    ev = evaluate_concern(
        "HIGH_NOTE_TOO_EFFORTFUL", song_profile=song, task_evidence=fused
    )
    assert ev["status"] in ("CONFIRMED", "PARTIALLY_SUPPORTED")
    coach = build_concern_coaching(ev, fused_profile=fused)
    assert coach["coaching_mode"] in ("CORRECT", "REFINE")
    assert "힘" in ((coach.get("practice_direction") or {}).get("title") or "")


def test_context_dependent_produces_transfer_coaching():
    tasks = [
        _task("sustain_a", {"effort": {"status": "LOW", "estimate": 0.3}}),
        _task("high_note_sustain_a", {"effort": {"status": "LOW", "estimate": 0.35}}),
    ]
    fused = _fused(tasks)
    song = {"vocal_function_profile": {"effort_assessment": {"severity": "HIGH"}}}
    ev = evaluate_concern(
        "HIGH_NOTE_TOO_EFFORTFUL", song_profile=song, task_evidence=fused
    )
    assert ev["status"] == "CONTEXT_DEPENDENT"
    coach = build_concern_coaching(ev, fused_profile=fused)
    assert coach["coaching_mode"] == "TRANSFER"
    blob = (coach.get("takeaway") or "") + str(coach.get("practice_direction"))
    assert "노래" in blob or "옮" in blob or "연결" in blob


def test_not_supported_is_not_unresolved():
    tasks = [
        _task("sustain_a", {"effort": {"status": "LOW", "estimate": 0.3}}),
        _task("high_note_sustain_a", {"effort": {"status": "LOW", "estimate": 0.35}}),
    ]
    fused = _fused(tasks)
    ev = evaluate_concern(
        "HIGH_NOTE_TOO_EFFORTFUL",
        song_profile={"vocal_function_profile": {"effort_assessment": {"severity": "LOW"}}},
        task_evidence=fused,
    )
    assert ev["status"] != "UNRESOLVED"
    assert ev["status"] == "NOT_SUPPORTED_IN_THIS_RECORDING"


def test_unresolved_does_not_claim_strength_without_evidence():
    fused = {
        "task_profiles": {
            "high_note_sustain_a": {"task_id": "high_note_sustain_a", "valid": False, "dimensions": {}}
        },
        "controlled_contrasts": {},
    }
    ev = {
        "concern_id": "HIGH_NOTE_TOO_EFFORTFUL",
        "status": "UNRESOLVED",
        "unresolved_reason": "INVALID_HIGH_NOTE_TASK",
        "support": [],
        "against": [],
        "missing": ["VALID_HIGH_NOTE_TASK"],
    }
    strengths = derive_precision_strengths(concern_evaluations=[ev], fused_profile=fused)
    blob = " ".join(s["description"] for s in strengths)
    assert "잘하고" not in blob
    coach = build_concern_coaching(ev, fused_profile=fused)
    assert coach["coaching_mode"] in ("GUIDE", "PRESERVE_ONLY")
    # May attach safe guidance practice, but must not invent "you're doing well" strength
    assert "잘하고" not in str(coach.get("takeaway") or "")
    assert coach.get("practice_direction") is None or "잘하고" not in str(coach)


def test_low_effort_high_note_can_be_strength():
    tasks = [
        _task("sustain_a", {"effort": {"status": "LOW", "estimate": 0.3}}),
        _task("high_note_sustain_a", {"effort": {"status": "LOW", "estimate": 0.4}}),
    ]
    fused = _fused(tasks)
    ev = evaluate_concern(
        "HIGH_NOTE_TOO_EFFORTFUL",
        song_profile={"vocal_function_profile": {"effort_assessment": {"severity": "LOW"}}},
        task_evidence=fused,
    )
    strengths = derive_precision_strengths(concern_evaluations=[ev], fused_profile=fused)
    assert any(s["id"] == "LOW_EFFORT_HIGH_NOTE_MAINTAINED" for s in strengths)


def test_stable_high_note_can_be_strength():
    tasks = [
        _task("sustain_a", {"stability": {"status": "STEADY", "estimate": 0.2}}),
        _task("high_note_sustain_a", {"stability": {"status": "STEADY", "estimate": 0.2}}),
    ]
    fused = _fused(tasks)
    strengths = derive_precision_strengths(concern_evaluations=[], fused_profile=fused)
    assert any(s["id"] == "HIGH_NOTE_STABILITY_MAINTAINED" for s in strengths)


def test_continuous_siren_can_be_strength():
    tasks = [_task("siren", {"register": {"status": "CONNECTED", "estimate": 0.8}})]
    fused = _fused(tasks)
    strengths = derive_precision_strengths(concern_evaluations=[], fused_profile=fused)
    assert any(s["id"] == "REGISTER_CONNECTION_MAINTAINED" for s in strengths)


def test_brightness_presence_ok_can_be_timbre_strength():
    ev = {
        "concern_id": "VOICE_TOO_DARK_MUFFLED",
        "status": "NOT_SUPPORTED_IN_THIS_RECORDING",
        "against": ["brightness_ok=0.65", "presence_ok=0.58"],
        "support": [],
    }
    strengths = derive_precision_strengths(concern_evaluations=[ev], fused_profile={})
    assert any(s["id"] == "TIMBRE_CLARITY_MAINTAINED" for s in strengths)


def test_strength_requires_positive_evidence():
    strengths = derive_precision_strengths(
        concern_evaluations=[
            {
                "concern_id": "HIGH_NOTE_TOO_EFFORTFUL",
                "status": "UNRESOLVED",
                "support": [],
                "against": [],
            }
        ],
        fused_profile={"task_profiles": {}, "controlled_contrasts": {}},
    )
    assert strengths == []


def test_timbre_dissatisfied_does_not_become_bad_timbre():
    ev = {
        "concern_id": "TIMBRE_DISSATISFIED",
        "status": "PARTIALLY_SUPPORTED",
        "support": ["brightness=0.65", "presence=0.58", "airiness=0.25"],
        "against": [],
    }
    coach = build_concern_coaching(ev)
    blob = (coach.get("takeaway") or "") + str(coach.get("practice_direction"))
    assert "나쁜" not in blob and "이상" not in blob and "정상 음색" not in blob


def test_timbre_followup_personalizes_coaching_not_diagnosis():
    song = {
        "vocal_function_profile": {
            "timbre_profile": {
                "available": True,
                "axes": {
                    "brightness": {"continuum": 0.65},
                    "presence": {"continuum": 0.58},
                    "airiness": {"continuum": 0.25},
                },
            }
        }
    }
    concerns = [{"id": "TIMBRE_DISSATISFIED", "follow_up": "MUFFLED"}]
    ev = evaluate_concern_status("TIMBRE_DISSATISFIED", song_profile=song)
    # Diagnosis must not invent muffled just because of follow_up
    assert ev["status"] == "PARTIALLY_SUPPORTED"
    assert "LOW_PRESENCE" not in (ev.get("candidate_causes") or [])
    coach = build_concern_coaching(ev, user_concerns=concerns)
    assert "선명" in (coach.get("takeaway") or "") or "유지" in (coach.get("takeaway") or "")


def test_muffled_not_supported_preserves_brightness_presence():
    ev = {
        "concern_id": "VOICE_TOO_DARK_MUFFLED",
        "status": "NOT_SUPPORTED_IN_THIS_RECORDING",
        "against": ["brightness_ok=0.65", "presence_ok=0.58"],
        "support": [],
    }
    coach = build_concern_coaching(ev)
    assert coach["coaching_mode"] == "MAINTAIN"
    assert "선명" in (coach.get("takeaway") or "") or "존재감" in (coach.get("takeaway") or "")


def test_muffled_confirmed_generates_refine_direction():
    ev = {
        "concern_id": "VOICE_TOO_DARK_MUFFLED",
        "status": "CONFIRMED",
        "support": ["low_brightness=0.3", "low_presence=0.28"],
        "against": [],
        "candidate_causes": ["LOW_BRIGHTNESS", "LOW_PRESENCE"],
    }
    coach = build_concern_coaching(ev)
    assert coach["coaching_mode"] == "CORRECT"
    assert coach.get("practice_direction")


def test_no_anatomical_timbre_claim():
    plan = build_precision_coaching_plan(
        user_concerns=[{"id": "VOICE_TOO_DARK_MUFFLED"}],
        concern_evaluations=[
            {
                "concern_id": "VOICE_TOO_DARK_MUFFLED",
                "status": "CONFIRMED",
                "support": ["low_presence=0.3"],
                "against": [],
            }
        ],
        fused_profile={},
    )
    blob = str(plan)
    for banned in ("후두", "성대", "복압", "횡격막", "연구개", "TA_WEAK", "CT_WEAK", "LCA"):
        assert banned not in blob


def test_public_report_does_not_render_internal_evidence_tokens():
    assert user_facing_evidence_token("baseline_and_high_both_low")
    assert "baseline" not in (user_facing_evidence_token("baseline_and_high_both_low") or "")
    assert user_facing_evidence_token("brightness_ok=0.65")
    assert "=" not in (user_facing_evidence_token("brightness_ok=0.65") or "")
    assert user_facing_evidence_token("presence_ok=0.58")
    assert user_facing_evidence_token("low_airiness_alone=0.25")
    assert user_facing_evidence_token("effort_delta_0.46")
    assert user_facing_evidence_token("song_effort_HIGH")
    # Unknown internal → hidden
    assert user_facing_evidence_token("some_unknown_internal_code") is None
    mapped = map_evidence_list(
        ["baseline_and_high_both_low", "brightness=0.65", "weird_token_xyz"]
    )
    assert "baseline_and_high_both_low" not in mapped
    assert all("=" not in m for m in mapped)


def test_qa_includes_coaching_and_no_generic_fallback():
    tasks = [
        _task("sustain_a", {"effort": {"status": "LOW", "estimate": 0.3}}),
        _task("high_note_sustain_a", {"effort": {"status": "LOW", "estimate": 0.4}}),
        _task(
            "sustain_a",
            {
                "effort": {"status": "LOW", "estimate": 0.3},
                "resonance": {"status": "BRIGHT", "estimate": 0.65, "available": True},
                "breathiness": {"status": "LOW", "estimate": 0.2},
            },
        ),
    ]
    # rebuild clean tasks
    tasks = [
        _task(
            "sustain_a",
            {
                "effort": {"status": "LOW", "estimate": 0.3},
                "stability": {"status": "STEADY", "estimate": 0.2},
                "breathiness": {"status": "LOW", "estimate": 0.2},
                "resonance": {"status": "BRIGHT", "estimate": 0.65},
                "contact": {"status": "MID", "estimate": 0.5},
            },
        ),
        _task(
            "high_note_sustain_a",
            {
                "effort": {"status": "LOW", "estimate": 0.4},
                "stability": {"status": "STEADY", "estimate": 0.2},
            },
        ),
        _task("siren", {"register": {"status": "CONNECTED", "estimate": 0.8}}),
    ]
    fused = _fused(tasks)
    song = {
        "vocal_function_profile": {
            "effort_assessment": {"severity": "LOW"},
            "timbre_profile": {
                "available": True,
                "axes": {
                    "brightness": {"continuum": 0.65},
                    "presence": {"continuum": 0.58},
                    "airiness": {"continuum": 0.25},
                },
            },
        }
    }
    qa = build_personalized_qa(
        user_concerns=[
            {"id": "HIGH_NOTE_TOO_EFFORTFUL"},
            {"id": "TIMBRE_DISSATISFIED"},
            {"id": "VOICE_TOO_DARK_MUFFLED"},
        ],
        song_profile=song,
        task_results=tasks,
        fused_profile=fused,
        diagnostic_mode="CONCERN_FOCUSED",
    )
    assert qa.get("coaching")
    assert qa["questions"][0]["status"] == "NOT_SUPPORTED_IN_THIS_RECORDING"
    assert qa["questions"][0]["coaching_mode"] == "MAINTAIN"
    blob = str(qa.get("improvement_priorities")) + str(qa.get("coaching"))
    assert "현재 발성 패턴 관찰하기" not in blob
    assert "다시 녹음" not in blob


def test_same_song_diagnosis_unchanged_by_coaching():
    """Coaching must not alter concern status."""
    tasks = [
        _task("sustain_a", {"effort": {"status": "LOW", "estimate": 0.35}}),
        _task("high_note_sustain_a", {"effort": {"status": "LOW", "estimate": 0.47}}),
    ]
    fused = _fused(tasks)
    song = {"vocal_function_profile": {"effort_assessment": {"severity": "LOW"}}}
    before = evaluate_concern(
        "HIGH_NOTE_TOO_EFFORTFUL", song_profile=song, task_evidence=fused
    )
    plan = build_precision_coaching_plan(
        user_concerns=[{"id": "HIGH_NOTE_TOO_EFFORTFUL"}],
        concern_evaluations=[before],
        song_profile=song,
        fused_profile=fused,
    )
    after = evaluate_concern(
        "HIGH_NOTE_TOO_EFFORTFUL", song_profile=song, task_evidence=fused
    )
    assert before["status"] == after["status"] == "NOT_SUPPORTED_IN_THIS_RECORDING"
    assert plan["per_concern"][0]["coaching_mode"] == "MAINTAIN"
