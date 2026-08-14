"""Dynamic Concern QA v3 — concern_id routing, same-concern different evidence."""

from __future__ import annotations

from audio_analyzer.diagnostic.concern_resolver import evaluate_concern
from audio_analyzer.diagnostic.concerns import (
    CONCERN_QUESTION_TEMPLATES,
    build_personalized_qa,
)
from audio_analyzer.diagnostic.practice_library import practice_for_focus
from audio_analyzer.diagnostic.question_semantics import (
    QUESTION_SEMANTICS,
    TYPE_DESCRIPTIVE,
    TYPE_FUNCTIONAL,
    TYPE_PERCEPTUAL,
    TYPE_SAFETY,
    audited_concern_ids,
    question_type_for,
)


def _song(
    *,
    effort="HIGH",
    contact="FIRM",
    register="PARTIAL",
    presence=0.32,
    breath="LOW",
    brightness=None,
    stability="STABLE",
):
    cont = {"FIRM": 0.72, "LIGHT": 0.28, "MID": 0.5}.get(contact, 0.5)
    axes = {"airiness": {"continuum": 0.25}}
    if presence is not None:
        axes["presence"] = {"continuum": presence}
    if brightness is not None:
        axes["brightness"] = {"continuum": brightness}
    return {
        "vocal_function_profile": {
            "effort_assessment": {"severity": effort},
            "dimensions": {
                "vocal_effort_strain": {"status": effort},
                "glottal_contact_profile": {
                    "status": "OBSERVED",
                    "continuum_0_to_1": cont,
                    "status_label": "중간"
                    if contact == "MID"
                    else ("단단" if contact == "FIRM" else "가벼"),
                },
                "air_leakage_breathiness": {"status": breath},
                "phonation_regularity": {"status": stability},
            },
            "vocal_type_profile": {
                "register_strategy": {"status": register},
                "canonical_register": {"status": register},
            },
            "timbre_profile": {"available": True, "axes": axes},
        }
    }


def _skip(*tasks: str):
    return {
        "task_profiles": {},
        "controlled_contrasts": {},
        "user_skipped_tasks": list(tasks),
        "task_evidence": {"user_skipped_tasks": list(tasks)},
    }


def test_questions_follow_selected_concern_ids():
    ids = ["TIMBRE_DISSATISFIED", "VOICE_TOO_THIN", "VOICE_TOO_DARK_MUFFLED"]
    qa = build_personalized_qa(
        user_concerns=[{"id": x} for x in ids],
        song_profile=_song(),
        fused_profile=_skip("siren"),
    )
    assert [q["concern_id"] for q in qa["questions"]] == ids
    for q in qa["questions"]:
        assert q["question"] == CONCERN_QUESTION_TEMPLATES[q["concern_id"]]


def test_question_order_follows_user_selection():
    ids = ["PITCH_UNSTABLE", "THROAT_EFFORT", "VOICE_TOO_BREATHY"]
    qa = build_personalized_qa(
        user_concerns=[{"id": x} for x in ids],
        song_profile=_song(effort="HIGH"),
        fused_profile=_skip(),
    )
    assert [q["concern_id"] for q in qa["questions"]] == ids


def test_no_q1_q2_q3_semantic_hardcoding():
    # Same slot index, different concern → different question text
    a = build_personalized_qa(
        user_concerns=[{"id": "VOICE_TOO_THIN"}],
        song_profile=_song(),
        fused_profile=_skip(),
    )
    b = build_personalized_qa(
        user_concerns=[{"id": "HIGH_NOTE_FLIPS"}],
        song_profile=_song(register="DISRUPTED"),
        fused_profile=_skip("siren"),
    )
    assert a["questions"][0]["concern_id"] != b["questions"][0]["concern_id"]
    assert a["questions"][0]["question"] != b["questions"][0]["question"]


def test_same_concern_different_evidence_different_answer():
    a = evaluate_concern(
        "VOICE_TOO_THIN",
        song_profile=_song(breath="HIGH", presence=0.55, contact="LIGHT", register="CONNECTED"),
        task_evidence=_skip(),
    )
    b = evaluate_concern(
        "VOICE_TOO_THIN",
        song_profile=_song(breath="LOW", presence=0.30, contact="MID", register="CONNECTED"),
        task_evidence=_skip(),
    )
    c = evaluate_concern(
        "VOICE_TOO_THIN",
        song_profile=_song(breath="LOW", presence=0.55, contact="MID", register="DISRUPTED"),
        task_evidence=_skip(),
    )
    answers = {a["answer_hint"], b["answer_hint"], c["answer_hint"]}
    assert len(answers) == 3
    assert a["primary_focus"] != b["primary_focus"] or a["primary_focus"] != c["primary_focus"]


def test_same_concern_different_primary_focus():
    a = evaluate_concern(
        "HIGH_NOTE_TOO_EFFORTFUL",
        song_profile=_song(effort="HIGH", contact="FIRM", register="CONNECTED"),
        task_evidence=_skip("high_note_sustain_a"),
    )
    b = evaluate_concern(
        "HIGH_NOTE_TOO_EFFORTFUL",
        song_profile=_song(effort="LOW", contact="MID", register="DISRUPTED"),
        task_evidence=_skip("high_note_sustain_a"),
    )
    c = evaluate_concern(
        "HIGH_NOTE_TOO_EFFORTFUL",
        song_profile=_song(effort="LOW", contact="MID", register="CONNECTED"),
        task_evidence=_skip("high_note_sustain_a"),
    )
    assert a["primary_focus"] == "EFFORT"
    assert b["primary_focus"] == "REGISTER_CONNECTION"
    assert c["primary_focus"] == "MAINTAIN"


def test_same_concern_different_practice():
    a = evaluate_concern(
        "HIGH_NOTE_TOO_EFFORTFUL",
        song_profile=_song(effort="HIGH", contact="FIRM"),
        task_evidence=_skip("high_note_sustain_a"),
    )
    b = evaluate_concern(
        "HIGH_NOTE_TOO_EFFORTFUL",
        song_profile=_song(effort="LOW", register="DISRUPTED"),
        task_evidence=_skip("high_note_sustain_a"),
    )
    assert (a.get("practice") or {}).get("practice_id") != (b.get("practice") or {}).get(
        "practice_id"
    )


def test_descriptive_profile_uses_multiple_axes():
    ev = evaluate_concern(
        "TIMBRE_DISSATISFIED",
        song_profile=_song(breath="LOW", contact="MID", presence=0.35, brightness=None),
        task_evidence=_skip(),
    )
    assert ev.get("question_type") == TYPE_DESCRIPTIVE or (
        (ev.get("functional_hypothesis") or {}).get("question_type") == TYPE_DESCRIPTIVE
    )
    ans = ev.get("answer_hint") or ""
    # multi-axis synthesis — not binary confirm/deny
    assert "확인됐어요" not in ans
    assert "아니에요" not in ans or "단정" in ans
    assert "숨" in ans or "접촉" in ans or "존재감" in ans


def test_descriptive_profile_can_have_no_practice():
    ev = evaluate_concern(
        "TIMBRE_DISSATISFIED",
        song_profile=_song(breath="LOW", contact="MID"),
        task_evidence=_skip(),
    )
    assert ev.get("practice") is None
    assert "→" not in (ev.get("answer_hint") or "")


def test_perceptual_concern_does_not_deny_user_feeling():
    ev = evaluate_concern(
        "VOICE_TOO_THIN",
        song_profile=_song(breath="LOW", presence=0.3),
        task_evidence=_skip(),
    )
    ans = ev.get("answer_hint") or ""
    assert "얇지 않아요" not in ans
    assert "얇" in ans or "존재감" in ans


def test_thin_low_breathiness_searches_other_explanations():
    ev = evaluate_concern(
        "VOICE_TOO_THIN",
        song_profile=_song(breath="LOW", presence=0.3),
        task_evidence=_skip(),
    )
    ans = ev.get("answer_hint") or ""
    assert "숨이 많이 새서" in ans or "강하게 보이지" in ans
    assert "존재감" in ans
    assert ev.get("primary_focus") == "PRESENCE"


def test_muffled_unavailable_brightness_never_claims_brightness():
    ev = evaluate_concern(
        "VOICE_TOO_DARK_MUFFLED",
        song_profile=_song(presence=0.3, brightness=None),
        task_evidence=_skip(),
    )
    ans = ev.get("answer_hint") or ""
    assert "밝은" not in ans
    assert "어두운 음색 때문" not in ans or "단정하지" in ans
    # should mention presence or uncertainty, not invent brightness direction as fact
    assert "존재감" in ans or "비교되지" in ans


def test_muffled_brightness_cases_differ():
    a = evaluate_concern(
        "VOICE_TOO_DARK_MUFFLED",
        song_profile=_song(brightness=0.3, presence=0.5),
        task_evidence=_skip(),
    )
    b = evaluate_concern(
        "VOICE_TOO_DARK_MUFFLED",
        song_profile=_song(brightness=None, presence=0.3),
        task_evidence=_skip(),
    )
    c = evaluate_concern(
        "VOICE_TOO_DARK_MUFFLED",
        song_profile=_song(brightness=None, presence=0.55),
        task_evidence=_skip(),
    )
    assert len({a["answer_hint"], b["answer_hint"], c["answer_hint"]}) == 3


def test_concern_only_contains_no_controlled_claim():
    qa = build_personalized_qa(
        user_concerns=[{"id": "VOICE_TOO_THIN"}, {"id": "THROAT_EFFORT"}],
        song_profile=_song(),
        fused_profile=_skip("siren", "high_note_sustain_a", "sustain_a"),
    )
    blob = " ".join(q["answer"] for q in qa["questions"])
    assert "표준 발성" not in blob
    assert "표준 과제" not in blob


def test_timbre_unknown_does_not_default_to_register_glide():
    p = practice_for_focus("UNKNOWN_FOCUS", category="timbre")
    assert p.get("practice_id") != "REGISTER_GLIDE_LIGHT"
    assert p.get("practice_id") == "TIMBRE_PRESERVE"


def test_effort_unknown_does_not_default_to_timbre_practice():
    p = practice_for_focus("UNKNOWN_FOCUS", category="effort")
    assert p.get("practice_id") == "REDUCE_HIGH_NOTE_EFFORT"


def test_control_unknown_gets_control_specific_guidance():
    p = practice_for_focus("UNKNOWN_FOCUS", category="control")
    assert p.get("practice_id") == "STABILITY_SHORT_HOLD"


def test_all_catalog_concerns_have_semantics():
    from audio_analyzer.diagnostic.concerns import CONCERN_CATALOG

    for cid in CONCERN_CATALOG:
        assert cid in QUESTION_SEMANTICS or cid == "OTHER_CONCERN" or cid in audited_concern_ids()
        assert question_type_for(cid)


def test_semantics_types_cover_expected():
    types = {question_type_for(c) for c in audited_concern_ids()}
    assert TYPE_DESCRIPTIVE in types
    assert TYPE_PERCEPTUAL in types
    assert TYPE_FUNCTIONAL in types
    assert TYPE_SAFETY in types


def test_detail_qa_presence_consistent():
    song = _song(presence=0.3)
    ev = evaluate_concern("VOICE_TOO_THIN", song_profile=song, task_evidence=_skip())
    ans = ev.get("answer_hint") or ""
    # Detail says presence LOW; QA must not claim high presence
    assert "존재감이 높은" not in ans
    assert "존재감" in ans


def test_detail_qa_breathiness_consistent():
    song = _song(breath="LOW", presence=0.3)
    ev = evaluate_concern("VOICE_TOO_THIN", song_profile=song, task_evidence=_skip())
    ans = ev.get("answer_hint") or ""
    assert "숨 섞임이 큰" not in ans.split("대신")[0] or "강하게 보이지" in ans


def test_banned_anatomical_claims_absent():
    for cid in (
        "VOICE_TOO_THIN",
        "THROAT_EFFORT",
        "HIGH_NOTE_FLIPS",
        "VOICE_TOO_DARK_MUFFLED",
    ):
        ev = evaluate_concern(cid, song_profile=_song(), task_evidence=_skip("siren"))
        ans = ev.get("answer_hint") or ""
        for bad in ("복압", "목 근육", "후두가", "성대가 너무", "TA", "CT"):
            assert bad not in ans


def test_representative_fixture_sets_produce_matching_questions():
    sets = [
        ["TIMBRE_DISSATISFIED", "VOICE_TOO_THIN", "VOICE_TOO_DARK_MUFFLED"],
        ["HIGH_NOTE_CANNOT_REACH", "HIGH_NOTE_TOO_EFFORTFUL", "HIGH_NOTE_FLIPS"],
        ["THROAT_EFFORT", "VOICE_TOO_BREATHY", "PITCH_UNSTABLE"],
    ]
    for ids in sets:
        qa = build_personalized_qa(
            user_concerns=[{"id": x} for x in ids],
            song_profile=_song(register="DISRUPTED", effort="HIGH"),
            fused_profile=_skip("siren", "high_note_sustain_a"),
        )
        assert [q["concern_id"] for q in qa["questions"]] == ids
        for q in qa["questions"]:
            assert q["answer"]
            assert q["concern_id"] in q.get("question") or CONCERN_QUESTION_TEMPLATES[q["concern_id"]] == q["question"]
