"""Precision QA Actionable Guidance v4 — evidence-first + general vocal guidance."""

from __future__ import annotations

import copy
import json
import re

from audio_analyzer.diagnostic.concern_resolver import evaluate_concern
from audio_analyzer.diagnostic.concerns import build_personalized_qa
from audio_analyzer.diagnostic.functional_hypothesis import assert_no_banned_claims
from audio_analyzer.diagnostic.general_guidance import (
    finalize_actionable_qa,
    observed_facts_from_snapshot,
)
from audio_analyzer.diagnostic.goal_planner import plan_coaching_goal
from audio_analyzer.diagnostic.song_evidence import get_canonical_snapshot

MISSING_WHEN_EVIDENCE = (
    "충분히 비교되지 않았어요",
    "하나로 좁히기 어려워요",
    "이번 노래만으로 알기 어려워요",
    "추가 확인이 필요해요",
    "판단하기 어려워요",
    "확인하기 어려워요",
    "밝기 비교가 충분하지 않아요",
)

BANNED_DIAGNOSIS = (
    "복압",
    "횡격막",
    "후두가",
    "목 근육",
    "성대를 너무",
    "성대가 벌어",
    "TA",
    "CT",
    "LCA",
)

BAD_SUFFIX = re.compile(r"(적|높|낮)예요")


def _song(
    *,
    effort="LOW",
    contact="MID",
    register="DISRUPTED",
    presence=0.5,
    breath="LOW",
    brightness=None,
    stability="STABLE",
    chest_ratio=0.62,
    high_note_available=False,
):
    cont = {"FIRM": 0.72, "LIGHT": 0.28, "MID": 0.5}.get(contact, 0.5)
    axes = {"airiness": {"continuum": 0.25}}
    if presence is not None:
        axes["presence"] = {"continuum": presence}
    if brightness is not None:
        axes["brightness"] = {"continuum": brightness}
    hn = {"available": bool(high_note_available), "reason": None, "summary": None, "axes": {}}
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
                "modifiers": ["CHEST_DOMINANT"] if chest_ratio and chest_ratio >= 0.55 else [],
                "head_chest": {
                    "chest_ratio": chest_ratio,
                    "available": chest_ratio is not None,
                    "broad_label": "흉성 경향" if chest_ratio and chest_ratio >= 0.55 else None,
                },
            },
            "timbre_profile": {
                "available": presence is not None or brightness is not None,
                "axes": axes,
            },
            "high_note_function_profile": hn,
        }
    }


def _skip(*tasks: str):
    return {
        "task_profiles": {},
        "controlled_contrasts": {},
        "user_skipped_tasks": list(tasks) or ["siren", "high_note_sustain_a"],
        "task_evidence": {"user_skipped_tasks": list(tasks) or ["siren", "high_note_sustain_a"]},
    }


def _qa(ids=None, song=None, timbre="SOFT_SWEET"):
    ids = ids or ["TIMBRE_DISSATISFIED", "VOICE_TOO_DARK_MUFFLED", "TIMBRE_CHANGES_HIGH"]
    song = song or _song()
    return build_personalized_qa(
        user_concerns=[{"id": x} for x in ids],
        song_profile=song,
        fused_profile=_skip(),
        timbre_goal=timbre,
    )


def _blob(qa) -> str:
    return " ".join(str(q.get("answer") or "") for q in qa.get("questions") or [])


def test_available_evidence_prevents_missing_data_answer():
    qa = _qa()
    blob = _blob(qa)
    for phrase in MISSING_WHEN_EVIDENCE:
        assert phrase not in blob, phrase


def test_unavailable_brightness_not_center_of_answer():
    qa = _qa()
    blob = _blob(qa)
    assert "밝기 비교가" not in blob
    assert "밝기나 세부 음색 분포는" not in blob
    q2 = next(q for q in qa["questions"] if q["concern_id"] == "VOICE_TOO_DARK_MUFFLED")
    assert "밝기" not in (q2.get("answer") or "")


def test_unknown_exact_cause_still_returns_action():
    song = _song(effort="UNKNOWN", register="UNRESOLVED", presence=None, breath="UNKNOWN", contact="UNKNOWN")
    song["vocal_function_profile"]["effort_assessment"] = {}
    song["vocal_function_profile"]["vocal_type_profile"]["register_strategy"] = {"status": "UNRESOLVED"}
    song["vocal_function_profile"]["dimensions"]["air_leakage_breathiness"] = {}
    song["vocal_function_profile"]["dimensions"]["glottal_contact_profile"] = {}
    ev = evaluate_concern(
        "HIGH_NOTE_CANNOT_REACH",
        song_profile=song,
        task_evidence=_skip("siren"),
    )
    assert ev.get("what_to_change")
    assert ev.get("action", {}).get("short_instruction")
    ans = ev.get("answer_hint") or ""
    assert "→" in ans or "연습" in ans or "비교" in ans


def test_general_guidance_never_creates_personal_diagnosis():
    qa = _qa()
    blob = _blob(qa) + " " + " ".join(str(q.get("knowledge_support") or "") for q in qa["questions"])
    for bad in BANNED_DIAGNOSIS:
        assert bad not in blob
    assert "따라서 이 사용자의 원인은" not in blob
    assert assert_no_banned_claims(blob)


def test_timbre_dissatisfied_uses_multiple_available_axes():
    ev = evaluate_concern(
        "TIMBRE_DISSATISFIED",
        song_profile=_song(),
        task_evidence=_skip(),
        timbre_goal={"id": "SOFT_SWEET"},
    )
    ans = ev.get("answer_hint") or ""
    hits = sum(1 for k in ("힘", "숨", "접촉", "안정", "흉") if k in ans)
    assert hits >= 2
    assert "적예요" not in ans
    assert "숨 섞임이 적어요" in ans or "숨 섞임이 적은" in ans


def test_descriptive_profile_not_single_axis_dump():
    ev = evaluate_concern(
        "TIMBRE_DISSATISFIED",
        song_profile=_song(),
        task_evidence=_skip(),
    )
    ans = ev.get("answer_hint") or ""
    assert ans.count("숨 섞임") <= 1
    assert "나머지는" not in ans
    assert "측정되지" not in ans
    assert ev.get("practice") is None
    assert "→" not in ans


def test_timbre_goal_connected_to_action():
    ev = evaluate_concern(
        "TIMBRE_DISSATISFIED",
        song_profile=_song(),
        task_evidence=_skip(),
        timbre_goal={"id": "SOFT_SWEET"},
    )
    ans = ev.get("answer_hint") or ""
    assert "부드럽" in ans or "감미" in ans
    assert ev.get("what_to_change")


def test_muffled_question_returns_action_without_brightness():
    ev = evaluate_concern(
        "VOICE_TOO_DARK_MUFFLED",
        song_profile=_song(brightness=None, presence=0.5),
        task_evidence=_skip(),
    )
    ans = ev.get("answer_hint") or ""
    assert "밝기 비교" not in ans
    assert ev.get("what_to_change")
    assert ev.get("action", {}).get("short_instruction")
    assert "→" in ans


def test_thin_question_uses_support_and_contra_evidence():
    ev = evaluate_concern(
        "VOICE_TOO_THIN",
        song_profile=_song(breath="LOW", presence=0.3),
        task_evidence=_skip(),
    )
    ans = ev.get("answer_hint") or ""
    assert "숨이 많이 새서" in ans or "강하게 보이지" in ans
    assert "존재감" in ans
    assert ev.get("what_to_change")


def test_perceptual_question_does_not_force_user_perception_true():
    ev = evaluate_concern(
        "VOICE_TOO_DARK_MUFFLED",
        song_profile=_song(),
        task_evidence=_skip(),
    )
    ans = ev.get("answer_hint") or ""
    assert "답답한 음색이 확인" not in ans
    assert "원인이다" not in ans


def test_timbre_changes_high_uses_register_when_available():
    ev = evaluate_concern(
        "TIMBRE_CHANGES_HIGH",
        song_profile=_song(register="DISRUPTED", high_note_available=False),
        task_evidence=_skip(),
    )
    ans = ev.get("answer_hint") or ""
    assert "급격" in ans or "달라지" in ans
    assert ev.get("primary_focus") == "REGISTER_CONNECTION"
    assert "하나로 좁히기" not in ans
    pid = (ev.get("action") or {}).get("practice_id") or (ev.get("practice") or {}).get("practice_id")
    assert pid == "REGISTER_GLIDE_LIGHT"


def test_high_note_question_uses_range_transition_when_high_note_unavailable():
    ev = evaluate_concern(
        "TIMBRE_CHANGES_HIGH",
        song_profile=_song(register="DISRUPTED", high_note_available=False),
        task_evidence=_skip(),
    )
    ans = ev.get("answer_hint") or ""
    assert "고음 자체를 직접 비교" not in ans
    assert "음역이 올라가는 과정" in ans or "음역이 올라갈 때" in ans


def test_high_note_question_returns_safe_general_action_when_direct_evidence_absent():
    song = _song(register="UNRESOLVED", effort="UNKNOWN")
    song["vocal_function_profile"]["effort_assessment"] = {}
    song["vocal_function_profile"]["vocal_type_profile"]["register_strategy"] = {"status": "UNRESOLVED"}
    ev = evaluate_concern(
        "TIMBRE_CHANGES_HIGH",
        song_profile=song,
        task_evidence=_skip(),
    )
    assert ev.get("what_to_change")
    assert ev.get("action", {}).get("short_instruction")
    assert "하나로 좁히기" not in (ev.get("answer_hint") or "")


def test_general_knowledge_never_changes_canonical_evidence():
    song = _song()
    snap = get_canonical_snapshot(song)
    before = copy.deepcopy(snap)
    hyp = {
        "concern_id": "VOICE_TOO_DARK_MUFFLED",
        "question_type": "PERCEPTUAL_CAUSAL",
        "primary_focus": "REGISTER_CONNECTION",
        "interpretation": "관찰이 있어요.",
        "guidance_level": "SONG_DIRECT",
        "evidence_used": [{"axis": "register", "status": "DISRUPTED"}],
        "practice_required": True,
    }
    finalize_actionable_qa(hyp, snap, timbre_goal="SOFT_SWEET")
    assert snap == before
    assert (snap.get("timbre") or {}).get("brightness") == (before.get("timbre") or {}).get("brightness")


def test_general_knowledge_never_changes_primary_measurements():
    song = _song(brightness=None)
    before_effort = copy.deepcopy(song["vocal_function_profile"]["effort_assessment"])
    evaluate_concern(
        "VOICE_TOO_DARK_MUFFLED",
        song_profile=song,
        task_evidence=_skip(),
        timbre_goal={"id": "SOFT_SWEET"},
    )
    assert song["vocal_function_profile"]["effort_assessment"] == before_effort
    snap = get_canonical_snapshot(song)
    assert (snap.get("timbre") or {}).get("brightness") is None


def test_general_knowledge_only_fills_interpretation_or_action():
    ev = evaluate_concern(
        "TIMBRE_CHANGES_HIGH",
        song_profile=_song(),
        task_evidence=_skip(),
    )
    ks = ev.get("knowledge_support") or ""
    ans = ev.get("answer_hint") or ""
    assert ks
    assert "이 사용자의 원인" not in ks
    assert ks not in ans
    assert (ev.get("comparison") or {}).get("A") and (ev.get("comparison") or {}).get("B")
    assert "비교해보기" not in ans
    assert ev.get("prescription") or ev.get("what_to_change")
    assert ev.get("knowledge_scope") == "GENERAL_VOCAL_GUIDANCE"
    assert ev.get("what_to_change")
    assert ev.get("success_cues")
    assert ev.get("knowledge_support_internal") is True
    for bad in (
        "직접 확정할 음향 지표는 제한적이에요",
        "한 원인으로 단정하지는 않아요",
        "특정 원인을 가정하기보다는",
        "뚜렷한 음향 특징이 강하지 않아요",
    ):
        assert bad not in ans


def test_goal_and_qa_share_register_evidence():
    song = _song(register="DISRUPTED")
    qa = _qa(song=song)
    goal = plan_coaching_goal(
        user_concerns=[{"id": q["concern_id"]} for q in qa["questions"]],
        timbre_goal={"id": "SOFT_SWEET"},
        concern_evaluations=qa["concern_evaluations"],
        song_profile=song,
    )
    snap = get_canonical_snapshot(song)
    assert str((snap.get("register") or {}).get("status") or "").upper() == "DISRUPTED"
    q3 = next(q for q in qa["questions"] if q["concern_id"] == "TIMBRE_CHANGES_HIGH")
    assert "급격" in (q3.get("answer") or "") or "달라지" in (q3.get("answer") or "")
    assert "연결" in (goal.get("goal_title") or "") or goal.get("primary_focus") == "REGISTER_CONNECTION"


def test_goal_and_qa_share_effort_evidence():
    song = _song(effort="LOW")
    qa = _qa(song=song)
    q1 = next(q for q in qa["questions"] if q["concern_id"] == "TIMBRE_DISSATISFIED")
    assert "힘" in (q1.get("answer") or "")
    snap = get_canonical_snapshot(song)
    assert str((snap.get("effort") or {}).get("level") or "").upper() == "LOW"


def test_goal_and_qa_do_not_contradict():
    song = _song(register="DISRUPTED")
    qa = _qa(song=song)
    goal = plan_coaching_goal(
        user_concerns=[{"id": q["concern_id"]} for q in qa["questions"]],
        timbre_goal={"id": "SOFT_SWEET"},
        concern_evaluations=qa["concern_evaluations"],
        song_profile=song,
    )
    blob = _blob(qa)
    if goal.get("primary_focus") == "REGISTER_CONNECTION":
        assert "연결" not in blob or "확인되지" not in blob
        assert "연결과 관련된 특징은 확인되지" not in blob


def test_no_bad_korean_suffixes():
    qa = _qa()
    blob = _blob(qa)
    assert BAD_SUFFIX.search(blob) is None
    assert "적예요" not in blob
    assert "높예요" not in blob
    assert "낮예요" not in blob


def test_no_repeated_missing_data_phrases_when_evidence_exists():
    qa = _qa()
    for q in qa["questions"]:
        ans = q.get("answer") or ""
        observed = q.get("observed") or q.get("evidence_used") or []
        if observed:
            for phrase in MISSING_WHEN_EVIDENCE:
                assert phrase not in ans, f"{q['concern_id']}: {phrase}"


def test_pain_does_not_receive_active_general_practice():
    ev = evaluate_concern(
        "PAIN_WHILE_SINGING",
        song_profile=_song(),
        task_evidence={},
    )
    assert ev.get("guidance_level") == "SAFETY_ONLY"
    pid = (ev.get("practice") or {}).get("practice_id")
    assert pid == "SAFETY_STOP"
    ans = ev.get("answer_hint") or ""
    assert "휴식" in ans or "멈추" in ans
    assert "립트릴" not in ans
    assert (ev.get("action") or {}).get("practice_id") == "SAFETY_STOP"


def test_general_guidance_respects_safety_gate():
    ev = evaluate_concern(
        "PAIN_WHILE_SINGING",
        song_profile=_song(),
        task_evidence={},
        timbre_goal={"id": "SOFT_SWEET"},
    )
    assert "음색 탐색" not in (ev.get("what_to_change") or "")
    assert "REGISTER_GLIDE" not in json.dumps(ev.get("action") or {}, ensure_ascii=False)
    cues = " ".join(ev.get("success_cues") or [])
    avoid = " ".join(ev.get("avoid") or [])
    assert "통증" in avoid or "강한 고음" in avoid or "휴식" in (ev.get("answer_hint") or "")


def test_sample_q1_q2_q3_actionable():
    qa = _qa()
    by = {q["concern_id"]: q for q in qa["questions"]}
    q1, q2, q3 = by["TIMBRE_DISSATISFIED"], by["VOICE_TOO_DARK_MUFFLED"], by["TIMBRE_CHANGES_HIGH"]
    assert "힘" in q1["answer"] and ("숨" in q1["answer"] or "접촉" in q1["answer"])
    assert "부드럽" in q1["answer"] or "감미" in q1["answer"]
    assert q1.get("what_to_change")
    assert "밝기 비교" not in q2["answer"]
    assert q2.get("what_to_change")
    assert "급격" in q3["answer"] or "달라지" in q3["answer"]
    assert q3.get("primary_focus") == "REGISTER_CONNECTION"
    for q in (q1, q2, q3):
        assert q.get("success_cues")
        assert q.get("what_to_change") or q.get("action")


def test_internal_tokens_not_in_user_answer():
    qa = _qa()
    blob = _blob(qa)
    for tok in ("canonical", "SONG_DIRECT", "SONG_COMPOSITE", "GENERAL_VOCAL_GUIDANCE", "primary_focus"):
        assert tok not in blob


def test_observed_skips_unavailable_brightness():
    facts = observed_facts_from_snapshot(get_canonical_snapshot(_song(brightness=None)))
    axes = {f["axis"] for f in facts}
    assert "brightness" not in axes
    assert "effort" in axes
    assert "breathiness" in axes
