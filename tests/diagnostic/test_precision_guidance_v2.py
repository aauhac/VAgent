"""Precision Guidance v2 — skip must not terminate; always-actionable answers."""

from __future__ import annotations

from audio_analyzer.diagnostic.concern_resolver import evaluate_concern
from audio_analyzer.diagnostic.functional_hypothesis import (
    assert_no_banned_claims,
    build_functional_hypothesis,
)
from audio_analyzer.diagnostic.practice_library import PRACTICE_LIBRARY


def _song(
    *,
    effort="HIGH",
    contact="FIRM",
    register="DISRUPTED",
    presence=0.32,
    breath="LOW",
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
                    "status_label": "중간" if contact == "MID" else ("단단" if contact == "FIRM" else "가벼"),
                },
                "air_leakage_breathiness": {"status": breath},
                "phonation_regularity": {"status": "STABLE"},
                "resonance_formant_strategy": {
                    "status": "OBSERVED",
                    "profile": {"mid_presence": "낮은 편", "brightness": "어두운 편"},
                },
            },
            "vocal_type_profile": {
                "register_strategy": {"status": register},
                "canonical_register": {"status": register},
                "modifiers": ["LOW_RESONANCE_PRESENCE"] if presence <= 0.42 else [],
            },
            "timbre_profile": {
                "available": True,
                "axes": {
                    "presence": {"continuum": presence},
                    "brightness": {"continuum": 0.3},
                    "airiness": {"continuum": 0.25},
                },
            },
        }
    }


def _skip_fused(*tasks: str):
    return {
        "task_profiles": {},
        "controlled_contrasts": {},
        "user_skipped_tasks": list(tasks),
        "task_evidence": {"user_skipped_tasks": list(tasks)},
    }


def test_siren_skip_still_uses_song_register():
    song = _song(register="DISRUPTED")
    ev = evaluate_concern(
        "HIGH_NOTE_FLIPS",
        song_profile=song,
        task_evidence=_skip_fused("siren"),
    )
    assert ev.get("controlled_confirmation") == "NOT_AVAILABLE_USER_SKIPPED"
    assert "건너뛰어" not in (ev.get("answer_hint") or "").split("→")[0]
    assert "연결" in (ev.get("answer_hint") or "")
    assert ev.get("guidance_level") in ("SONG_DIRECT", "SONG_COMPOSITE")
    assert ev.get("practice", {}).get("instruction")


def test_high_task_skip_still_uses_song_effort():
    song = _song(effort="HIGH", contact="FIRM")
    ev = evaluate_concern(
        "HIGH_NOTE_TOO_EFFORTFUL",
        song_profile=song,
        task_evidence=_skip_fused("high_note_sustain_a"),
    )
    assert ev["status"] != "CONFIRMED"
    assert "범위까지만 안내" not in (ev.get("answer_hint") or "")
    assert "힘" in (ev.get("answer_hint") or "")
    assert ev.get("primary_focus") == "EFFORT"


def test_skip_is_provenance_not_answer_blocker():
    song = _song(register="PARTIAL", effort="HIGH", contact="FIRM")
    ev = evaluate_concern(
        "HIGH_NOTE_CANNOT_REACH",
        song_profile=song,
        task_evidence=_skip_fused("siren", "high_note_sustain_a"),
    )
    assert ev.get("controlled_confirmation") == "NOT_AVAILABLE_USER_SKIPPED"
    assert "→" in (ev.get("answer_hint") or "")
    assert "좁히기 어려워요." not in (ev.get("answer_hint") or "").split("→")[-1]


def test_every_non_safety_concern_returns_actionable_guidance():
    song = _song()
    for cid in (
        "HIGH_NOTE_CANNOT_REACH",
        "HIGH_NOTE_TOO_EFFORTFUL",
        "HIGH_NOTE_FLIPS",
        "THROAT_EFFORT",
        "VOICE_TOO_THIN",
    ):
        ev = evaluate_concern(cid, song_profile=song, task_evidence=_skip_fused("siren", "high_note_sustain_a"))
        assert ev.get("guidance_level")
        assert ev.get("answer_hint")
        assert ev.get("practice", {}).get("instruction")
        assert ev.get("practice", {}).get("success_cues")
        assert ev.get("practice", {}).get("avoid")
        assert assert_no_banned_claims(ev["answer_hint"])


def test_unresolved_cause_can_still_return_safe_guidance():
    song = _song(effort="UNKNOWN", contact="MID", register="UNRESOLVED", presence=0.5)
    # Force unknown-ish by stripping
    song["vocal_function_profile"]["effort_assessment"] = {}
    song["vocal_function_profile"]["vocal_type_profile"]["register_strategy"] = {"status": "UNRESOLVED"}
    ev = evaluate_concern(
        "HIGH_NOTE_CANNOT_REACH",
        song_profile=song,
        task_evidence=_skip_fused("siren"),
    )
    assert ev.get("guidance_level") == "SAFE_GENERAL_GUIDANCE"
    assert "→" in (ev.get("answer_hint") or "")
    assert "연습" in (ev.get("answer_hint") or "") or "방향" in (ev.get("answer_hint") or "")


def test_high_note_cannot_reach_song_register_disrupted():
    ev = evaluate_concern(
        "HIGH_NOTE_CANNOT_REACH",
        song_profile=_song(register="DISRUPTED"),
        task_evidence=_skip_fused("siren"),
    )
    assert ev.get("primary_focus") == "REGISTER_CONNECTION"
    assert "연결" in (ev.get("answer_hint") or "")


def test_high_note_cannot_reach_composite_register_effort_contact():
    ev = evaluate_concern(
        "HIGH_NOTE_CANNOT_REACH",
        song_profile=_song(register="PARTIAL", effort="HIGH", contact="FIRM"),
        task_evidence=_skip_fused("siren"),
    )
    assert ev.get("guidance_level") == "SONG_COMPOSITE"
    assert "힘" in (ev.get("answer_hint") or "")
    assert "접촉" in (ev.get("answer_hint") or "")


def test_high_note_effort_song_high_effort_firm_contact():
    ev = evaluate_concern(
        "HIGH_NOTE_TOO_EFFORTFUL",
        song_profile=_song(effort="HIGH", contact="FIRM"),
        task_evidence=_skip_fused("high_note_sustain_a"),
    )
    assert "힘" in (ev.get("answer_hint") or "")
    assert "성대가" not in (ev.get("answer_hint") or "")


def test_high_note_effort_song_low_not_force_confirmed():
    ev = evaluate_concern(
        "HIGH_NOTE_TOO_EFFORTFUL",
        song_profile=_song(effort="LOW", contact="MID", register="CONNECTED"),
        task_evidence=_skip_fused("high_note_sustain_a"),
    )
    assert ev["status"] != "CONFIRMED"
    assert "과도한 힘" in (ev.get("answer_hint") or "") or "강하게 보이지" in (ev.get("answer_hint") or "")


def test_high_note_flip_song_register_disrupted():
    ev = evaluate_concern(
        "HIGH_NOTE_FLIPS",
        song_profile=_song(register="DISRUPTED"),
        task_evidence=_skip_fused("siren"),
    )
    assert "뒤집" in (ev.get("answer_hint") or "") or "연결" in (ev.get("answer_hint") or "")
    assert ev.get("guidance_level") == "SONG_DIRECT"


def test_high_note_flip_presence_only_not_causal():
    hyp = build_functional_hypothesis(
        "HIGH_NOTE_FLIPS",
        song_profile=_song(register="UNRESOLVED", presence=0.3, effort="LOW", contact="MID"),
        user_skipped_tasks={"siren"},
    )
    # Must not claim midrange weakness as cause
    assert "중음역이 약" not in hyp["interpretation"]
    assert "중음역대가 약" not in hyp["interpretation"]
    if "존재감" in hyp["interpretation"]:
        assert hyp.get("primary_focus") != "PRESENCE" or hyp["guidance_level"] == "SAFE_GENERAL_GUIDANCE"


def test_low_presence_never_becomes_weak_midrange():
    hyp = build_functional_hypothesis(
        "HIGH_NOTE_FLIPS",
        song_profile=_song(register="PARTIAL", presence=0.3),
        user_skipped_tasks={"siren"},
    )
    assert "중음역이 약" not in hyp["interpretation"]
    assert "중역 존재감" in hyp["interpretation"] or "존재감" in hyp["interpretation"] or hyp["guidance_level"]


def test_firm_contact_never_becomes_vocal_fold_overcompression_fact():
    hyp = build_functional_hypothesis(
        "HIGH_NOTE_TOO_EFFORTFUL",
        song_profile=_song(effort="HIGH", contact="FIRM"),
        user_skipped_tasks={"high_note_sustain_a"},
    )
    assert "성대가" not in hyp["interpretation"]
    assert "붙" not in hyp["interpretation"] or "접촉" in hyp["interpretation"]


def test_effort_never_becomes_low_abdominal_pressure():
    for p in PRACTICE_LIBRARY.values():
        blob = " ".join(
            [
                str(p.get("instruction")),
                str(p.get("title")),
                " ".join(p.get("success_cues") or []),
                " ".join(p.get("avoid") or []),
            ]
        )
        assert "복압" not in blob
        assert "횡격막" not in blob


def test_register_issue_never_becomes_ct_ta_diagnosis():
    hyp = build_functional_hypothesis(
        "HIGH_NOTE_CANNOT_REACH",
        song_profile=_song(register="DISRUPTED"),
        user_skipped_tasks={"siren"},
    )
    assert "TA" not in hyp["interpretation"]
    assert "CT" not in hyp["interpretation"]


def test_user_concern_does_not_force_positive_diagnosis():
    ev = evaluate_concern(
        "HIGH_NOTE_TOO_EFFORTFUL",
        song_profile=_song(effort="LOW", register="CONNECTED"),
        task_evidence=_skip_fused("high_note_sustain_a"),
    )
    assert ev["status"] != "CONFIRMED"


def test_pain_uses_safety_guidance_not_active_exercise():
    ev = evaluate_concern(
        "PAIN_WHILE_SINGING",
        song_profile=_song(),
        task_evidence={},
    )
    assert ev["status"] == "SAFETY_ONLY"
    assert ev.get("guidance_level") == "SAFETY_ONLY"
    assert "휴식" in (ev.get("answer_hint") or "") or "멈추" in (ev.get("answer_hint") or "")
