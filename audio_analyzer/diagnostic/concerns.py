"""User concern model + hypothesis map + personalized Q&A (Precision Diagnostic v2).

USER_REPORTED ≠ AUDIO_OBSERVED ≠ CONTROLLED_TASK_CONFIRMED
"""

from __future__ import annotations

from typing import Any, Optional

CONCERN_SOURCE = "USER_REPORTED"

# Safety concerns → pain flag (not anatomical location map)
PAIN_CONCERN_IDS = frozenset(
    {
        "PAIN_WHILE_SINGING",
        "PAIN_AFTER_SINGING",
        "SPEAKING_DISCOMFORT",
        "PERSISTENT_HOARSENESS",
    }
)

AGGRESSIVE_TASKS_WHEN_PAIN = frozenset({"dynamic_swell", "high_note_sustain_a"})

# Safety checkbox severity (not anatomical diagnosis)
# LEVEL 2 — actual pain / unsafe to phonate → block ALL controlled phonation
PAIN_LIMITED_SAFETY_FLAGS = frozenset(
    {
        "pain_on_phonation",
        "breathing_difficulty",
        "sudden_voice_change",
        "persistent_severe_hoarseness",
    }
)
# LEVEL 1 — discomfort / fatigue burden → block aggressive tasks only
DISCOMFORT_SAFETY_FLAGS = frozenset(
    {
        "severe_discomfort_after",
    }
)

SAFETY_SEVERITY_NONE = "NONE"
SAFETY_SEVERITY_DISCOMFORT = "DISCOMFORT"
SAFETY_SEVERITY_PAIN = "PAIN_LIMITED"

CONCERN_CATALOG: dict[str, dict[str, str]] = {
    "HIGH_NOTE_CANNOT_REACH": {"label": "고음이 잘 안 올라가요", "category": "high_note"},
    "HIGH_NOTE_TOO_EFFORTFUL": {"label": "고음은 나오는데 너무 힘들어요", "category": "high_note"},
    "HIGH_NOTE_FLIPS": {"label": "고음에서 소리가 갑자기 뒤집혀요", "category": "high_note"},
    "HIGH_NOTE_THINS": {"label": "고음에서 소리가 너무 얇아져요", "category": "high_note"},
    "HIGH_NOTE_UNSTABLE": {"label": "고음에서 음정이나 소리가 흔들려요", "category": "high_note"},
    "THROAT_EFFORT": {"label": "목에 힘이 자꾸 들어가요", "category": "effort"},
    "LOUD_VOICE_DIFFICULT": {"label": "큰 소리를 내면 힘들어요", "category": "effort"},
    "VOCAL_FATIGUE": {"label": "조금만 불러도 금방 지쳐요", "category": "effort"},
    "AFTER_SINGING_FATIGUE": {"label": "노래 후 목소리가 쉽게 지쳐요", "category": "effort"},
    "TIMBRE_DISSATISFIED": {"label": "내 음색이 마음에 들지 않아요", "category": "timbre"},
    "VOICE_TOO_THIN": {"label": "소리가 얇고 모기소리처럼 느껴져요", "category": "timbre"},
    "VOICE_TOO_DARK_MUFFLED": {"label": "소리가 답답하게 들려요", "category": "timbre"},
    "VOICE_TOO_NASAL_PERCEPT": {"label": "콧소리처럼 들려요", "category": "timbre"},
    "VOICE_TOO_BREATHY": {"label": "숨이 많이 섞여요", "category": "timbre"},
    "VOICE_TOO_SHARP": {"label": "소리가 너무 날카롭게 들려요", "category": "timbre"},
    "VOICE_ROUGH": {"label": "거칠게 들려요", "category": "timbre"},
    "TIMBRE_CHANGES_HIGH": {"label": "고음에서 음색이 갑자기 달라져요", "category": "timbre"},
    "PITCH_UNSTABLE": {"label": "음정이 흔들려요", "category": "control"},
    "REGISTER_CONNECTION_DIFFICULT": {"label": "낮은 음과 높은 음이 자연스럽게 연결되지 않아요", "category": "control"},
    "VIBRATO_UNSTABLE": {"label": "비브라토가 불안정해요", "category": "control"},
    "DYNAMICS_DIFFICULT": {"label": "강약 조절이 어려워요", "category": "control"},
    "PHRASE_END_WEAK": {"label": "긴 구절을 끝까지 유지하기 어려워요", "category": "control"},
    "PAIN_WHILE_SINGING": {"label": "노래할 때 목이 아파요", "category": "safety"},
    "PAIN_AFTER_SINGING": {"label": "노래 후에도 통증이 남아요", "category": "safety"},
    "SPEAKING_DISCOMFORT": {"label": "말할 때도 불편해요", "category": "safety"},
    "PERSISTENT_HOARSENESS": {"label": "노래 후 쉰 느낌이 오래 지속돼요", "category": "safety"},
    "OTHER_CONCERN": {"label": "직접 입력", "category": "other"},
}

# Concern → planner dimension keys (hypothesis space, not diagnosis)
CONCERN_HYPOTHESIS_MAP: dict[str, list[str]] = {
    "HIGH_NOTE_CANNOT_REACH": ["effort", "register", "stability", "breathiness", "resonance"],
    "HIGH_NOTE_TOO_EFFORTFUL": ["effort", "register", "stability", "contact"],
    "HIGH_NOTE_FLIPS": ["register", "stability", "effort"],
    "HIGH_NOTE_THINS": ["breathiness", "resonance", "contact", "effort"],
    "HIGH_NOTE_UNSTABLE": ["stability", "effort", "register", "breathiness"],
    "THROAT_EFFORT": ["effort", "contact", "register"],
    "LOUD_VOICE_DIFFICULT": ["effort", "dynamic_response", "contact"],
    "VOCAL_FATIGUE": ["effort", "dynamic_response", "stability"],
    "AFTER_SINGING_FATIGUE": ["effort", "stability", "breathiness"],
    "TIMBRE_DISSATISFIED": ["resonance", "breathiness", "contact", "stability"],
    "VOICE_TOO_THIN": ["breathiness", "resonance", "contact", "effort"],
    "VOICE_TOO_DARK_MUFFLED": ["resonance", "contact", "breathiness"],
    "VOICE_TOO_NASAL_PERCEPT": ["resonance", "contact"],
    "VOICE_TOO_BREATHY": ["breathiness", "contact", "stability"],
    "VOICE_TOO_SHARP": ["resonance", "contact", "breathiness"],
    "VOICE_ROUGH": ["stability", "contact", "breathiness"],
    "TIMBRE_CHANGES_HIGH": ["resonance", "breathiness", "register", "effort"],
    "PITCH_UNSTABLE": ["stability", "effort", "register"],
    "REGISTER_CONNECTION_DIFFICULT": ["register", "effort", "stability"],
    "VIBRATO_UNSTABLE": ["stability", "effort"],
    "DYNAMICS_DIFFICULT": ["dynamic_response", "effort", "contact"],
    "PHRASE_END_WEAK": ["dynamic_response", "stability", "breathiness"],
}

FOLLOW_UP_OPTIONS: dict[str, list[dict[str, str]]] = {
    "HIGH_NOTE_CANNOT_REACH": [
        {"id": "NOT_REACHING", "label": "음 자체가 잘 올라가지 않아요"},
        {"id": "EFFORTFUL_HIGH", "label": "올라가지만 힘이 많이 들어가요"},
        {"id": "FLIPS", "label": "갑자기 다른 소리로 바뀌어요"},
        {"id": "THINS", "label": "소리가 얇아져요"},
        {"id": "UNSTABLE", "label": "흔들려요"},
        {"id": "UNSURE", "label": "잘 모르겠어요"},
    ],
    "TIMBRE_DISSATISFIED": [
        {"id": "THIN", "label": "얇고 가벼워요"},
        {"id": "MUFFLED", "label": "답답해요"},
        {"id": "NASAL", "label": "콧소리처럼 느껴져요"},
        {"id": "BREATHY", "label": "숨이 많이 섞여요"},
        {"id": "SHARP", "label": "너무 날카로워요"},
        {"id": "ROUGH", "label": "거칠어요"},
        {"id": "HIGH_ONLY", "label": "고음에서만 달라져요"},
        {"id": "HARD_TO_DESCRIBE", "label": "표현하기 어려워요"},
    ],
}

MAX_CONCERNS = 3

DIAGNOSTIC_MODE_CONCERN = "CONCERN_FOCUSED"
DIAGNOSTIC_MODE_GENERAL = "GENERAL_DISCOVERY"

CONCERN_QUESTION_TEMPLATES: dict[str, str] = {
    "HIGH_NOTE_CANNOT_REACH": "왜 고음이 잘 올라가지 않을까요?",
    "HIGH_NOTE_TOO_EFFORTFUL": "왜 고음은 나오는데 너무 힘들까요?",
    "HIGH_NOTE_FLIPS": "왜 고음에서 소리가 갑자기 뒤집힐까요?",
    "HIGH_NOTE_THINS": "왜 고음에서 소리가 너무 얇아질까요?",
    "HIGH_NOTE_UNSTABLE": "왜 고음에서 음정이나 소리가 흔들릴까요?",
    "THROAT_EFFORT": "왜 노래할 때 목에 힘이 자꾸 들어갈까요?",
    "LOUD_VOICE_DIFFICULT": "왜 큰 소리를 내면 힘들까요?",
    "VOCAL_FATIGUE": "왜 조금만 불러도 금방 지칠까요?",
    "AFTER_SINGING_FATIGUE": "왜 노래 후 목소리가 쉽게 지칠까요?",
    "TIMBRE_DISSATISFIED": "내 음색은 어떤 특징 때문에 이렇게 들릴까요?",
    "VOICE_TOO_THIN": "왜 소리가 얇고 모기소리처럼 느껴질까요?",
    "VOICE_TOO_DARK_MUFFLED": "왜 소리가 답답하게 들릴까요?",
    "VOICE_TOO_NASAL_PERCEPT": "왜 콧소리처럼 들릴까요?",
    "VOICE_TOO_BREATHY": "왜 숨이 많이 섞여 들릴까요?",
    "VOICE_TOO_SHARP": "왜 소리가 너무 날카롭게 들릴까요?",
    "VOICE_ROUGH": "왜 거칠게 들릴까요?",
    "TIMBRE_CHANGES_HIGH": "왜 고음에서 음색이 갑자기 달라질까요?",
    "PITCH_UNSTABLE": "왜 음정이 흔들릴까요?",
    "REGISTER_CONNECTION_DIFFICULT": "왜 낮은 음과 높은 음이 자연스럽게 연결되지 않을까요?",
    "VIBRATO_UNSTABLE": "왜 비브라토가 불안정할까요?",
    "DYNAMICS_DIFFICULT": "왜 강약 조절이 어려울까요?",
    "PHRASE_END_WEAK": "왜 긴 구절을 끝까지 유지하기 어려울까요?",
    "PAIN_WHILE_SINGING": "노래할 때 목이 아픈 느낌은 어떻게 다루면 좋을까요?",
    "PAIN_AFTER_SINGING": "노래 후에도 통증이 남는 경우 어떻게 하면 좋을까요?",
    "SPEAKING_DISCOMFORT": "말할 때도 불편한 느낌은 어떻게 다루면 좋을까요?",
    "PERSISTENT_HOARSENESS": "노래 후 쉰 느낌이 오래 갈 때 어떻게 하면 좋을까요?",
    "OTHER_CONCERN": "선택하신 고민은 이번 분석에서 어떻게 보일까요?",
}

BANNED_CLAIM_SUBSTRINGS = (
    "복압이 부족",
    "횡격막을 못",
    "후두가 올라",
    "목 근육이 긴장",
    "성대가 압착",
    "TA가",
    "CT가",
    "LCA가",
)


def normalize_user_concerns(raw: list[Any] | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, item in enumerate(raw[:MAX_CONCERNS]):
        if isinstance(item, str):
            cid = item
            follow = None
            text = None
        elif isinstance(item, dict):
            cid = str(item.get("id") or item.get("concern_id") or "")
            follow = item.get("follow_up")
            text = item.get("free_text")
        else:
            continue
        if cid not in CONCERN_CATALOG or cid in seen:
            continue
        seen.add(cid)
        out.append(
            {
                "id": cid,
                "source": CONCERN_SOURCE,
                "priority": len(out) + 1,
                "label": CONCERN_CATALOG[cid]["label"],
                "category": CONCERN_CATALOG[cid]["category"],
                **({"follow_up": follow} if follow else {}),
                **({"free_text": text} if text and cid == "OTHER_CONCERN" else {}),
            }
        )
    return out


def has_pain_safety_flag(concerns: list[dict[str, Any]]) -> bool:
    return any(c.get("id") in PAIN_CONCERN_IDS for c in concerns)


def concern_dimension_boost(concerns: list[dict[str, Any]]) -> dict[str, float]:
    """Priority boost per planner dimension from user concerns (not acoustic truth)."""
    boost: dict[str, float] = {}
    for c in concerns:
        weight = 1.0 / max(float(c.get("priority") or 1), 1.0)
        for dim in CONCERN_HYPOTHESIS_MAP.get(str(c.get("id")), []):
            boost[dim] = boost.get(dim, 0.0) + weight
    return boost


def classify_safety_severity(
    safety_flags: list[str] | None = None,
    *,
    pain_flag: bool = False,
) -> str:
    """Map safety answers → NONE | DISCOMFORT | PAIN_LIMITED (gating only)."""
    flags = [str(f) for f in (safety_flags or []) if f]
    if any(f in PAIN_LIMITED_SAFETY_FLAGS for f in flags):
        return SAFETY_SEVERITY_PAIN
    if any(f in DISCOMFORT_SAFETY_FLAGS for f in flags):
        return SAFETY_SEVERITY_DISCOMFORT
    # Concern-level pain without checkbox: discomfort tier (aggressive only).
    # Explicit pain_on_phonation is the hard phonation stop.
    if pain_flag and not flags:
        return SAFETY_SEVERITY_DISCOMFORT
    return SAFETY_SEVERITY_NONE


def filter_tasks_for_safety(
    selected: list[str],
    *,
    pain_flag: bool,
    safety_flags: list[str] | None = None,
) -> list[str]:
    severity = classify_safety_severity(safety_flags, pain_flag=pain_flag)
    if severity == SAFETY_SEVERITY_PAIN:
        # Actual phonation pain / serious safety → no controlled phonation tasks
        return []
    if severity == SAFETY_SEVERITY_DISCOMFORT:
        blocked = set(AGGRESSIVE_TASKS_WHEN_PAIN)
        return [t for t in selected if t not in blocked]
    return selected


def normalize_diagnostic_mode(
    mode: str | None,
    concerns: list[dict[str, Any]] | None = None,
) -> str:
    concerns = concerns or []
    raw = (mode or "").upper().strip()
    if raw == DIAGNOSTIC_MODE_GENERAL or raw == "GENERAL":
        return DIAGNOSTIC_MODE_GENERAL
    if raw == DIAGNOSTIC_MODE_CONCERN or raw == "CONCERN":
        return DIAGNOSTIC_MODE_CONCERN
    if concerns:
        return DIAGNOSTIC_MODE_CONCERN
    return DIAGNOSTIC_MODE_GENERAL


def concern_question_for(concern_id: str) -> str:
    return CONCERN_QUESTION_TEMPLATES.get(
        concern_id,
        f"왜 {CONCERN_CATALOG.get(concern_id, {}).get('label', concern_id)}일까요?",
    )


def build_concern_question(concerns: list[dict[str, Any]]) -> str:
    """Legacy single-question helper — prefer per-concern questions list."""
    if not concerns:
        return "이번 발성에서 가장 신경 쓰이는 부분은 무엇일까요?"
    return concern_question_for(str(concerns[0].get("id")))


def _answer_for_concern(
    concern_id: str,
    status: str,
    *,
    effort_level: str,
    reg_level: str,
    evaluation: dict[str, Any] | None = None,
) -> str:
    label = CONCERN_CATALOG.get(concern_id, {}).get("label", concern_id)
    ev = evaluation or {}
    if ev.get("answer_hint"):
        return str(ev["answer_hint"])
    if status == "SAFETY_ONLY":
        return (
            "통증이나 지속적인 불편감은 음향 분석만으로 원인을 판단할 수 없어요. "
            "불편한 상태에서는 강한 고음이나 큰 소리를 반복하지 마세요."
        )
    if status == "CONTEXT_DEPENDENT":
        return (
            "노래와 표준 과제에서 패턴이 다르게 나타났어요. "
            "곡의 강도나 표현 상황에 따라 달라질 가능성이 있습니다."
        )
    if status == "UNRESOLVED" and ev.get("unresolved_reason"):
        reason = str(ev["unresolved_reason"])
        if reason == "INVALID_HIGH_NOTE_TASK":
            return "높은 음 과제에서 비교 가능한 구간이 충분하지 않아 편한 음과 고음의 힘 차이를 확인하지 못했어요."
        if reason == "MISSING_BASELINE":
            return "편한 지속음 baseline이 없어 조건 간 차이를 확정하기 어려웠어요."
        if reason == "INSUFFICIENT_TIMBRE_FAMILIES":
            return "음색 관련 지표가 부족해 특징을 충분히 설명하기 어려웠어요."
        if reason == "NASALITY_NOT_DIRECTLY_MEASURED":
            return "콧소리처럼 들린다는 인상은 이번 음향 지표만으로 단정하기 어려워요."
        if reason == "CONFLICTING_TASK_RESULTS":
            return "음색 관련 지표가 과제마다 서로 다르게 나타나 원인을 하나로 좁히기 어려웠어요."
    if concern_id in ("THROAT_EFFORT", "HIGH_NOTE_TOO_EFFORTFUL") and effort_level == "HIGH":
        return (
            "노래와 추가 녹음에서 확인된 힘 증가 패턴이 "
            "현재 더 두드러진 제한으로 보입니다."
        )
    if concern_id == "THROAT_EFFORT" and effort_level == "LOW":
        return (
            "체감상 힘을 느끼셨지만, 이번 노래·표준 녹음에서는 "
            "과도한 effort와 일치하는 음향 패턴이 뚜렷하지 않았어요."
        )
    if concern_id in ("HIGH_NOTE_CANNOT_REACH", "REGISTER_CONNECTION_DIFFICULT"):
        if effort_level == "HIGH" and reg_level == "UNRESOLVED":
            return (
                "이번 검사에서는 성구 전환 자체보다 "
                "높은 음에서 힘이 크게 증가하는 패턴이 더 두드러졌습니다. "
                "전환 문제는 이번 녹음만으로 단정하기 어려워요."
            )
        if reg_level == "UNRESOLVED":
            return (
                "성구 전환 자체는 이번 녹음에서 충분히 관찰되지 않아 "
                "전환 문제가 원인이라고 단정하기는 어렵습니다."
            )
    return _status_user_line(status, label)


def build_general_discovery_summary(
    *,
    song_profile: dict[str, Any],
    task_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Whole-vocal precision summary — no fake Q&A."""
    effort_level, _ = _effort_observed(song_profile)
    reg_level, _ = _register_observed(song_profile)
    breath_level, _ = _breathiness_observed(song_profile)
    features: list[str] = []
    if breath_level == "LOW":
        features.append("기본 발성에서는 숨 섞임이 많지 않았어요.")
    elif breath_level == "HIGH":
        features.append("숨 섞임이 상대적으로 두드러졌어요.")
    if reg_level == "OBSERVED":
        features.append("중음에서 고음으로 올라갈 때 연결은 비교적 연속적으로 보였어요.")
    elif reg_level == "UNRESOLVED":
        features.append("성구 연결은 이번 검사만으로 충분히 확정하기 어려웠어요.")
    if effort_level == "HIGH":
        features.append("높은 음이나 강한 구간에서 힘 사용이 증가하는 패턴이 보였어요.")
    elif effort_level == "LOW":
        features.append("이번 검사에서는 과도한 힘 증가 패턴이 뚜렷하지 않았어요.")
    if task_results:
        features.append(f"표준 추가 녹음 {len(task_results)}개 결과를 함께 반영했어요.")
    if not features:
        features.append("이번 검사에서는 크게 두드러지는 제한 요소가 확인되지 않았어요.")

    from audio_analyzer.diagnostic.coaching import build_precision_coaching_plan

    bottleneck = _infer_bottleneck(song_profile)
    coaching = build_precision_coaching_plan(
        user_concerns=[],
        concern_evaluations=[],
        song_profile=song_profile,
        fused_profile={},
        task_results=task_results,
        diagnostic_mode=DIAGNOSTIC_MODE_GENERAL,
    )
    # General mode: strengths from song features → maintain practices
    if not coaching.get("practice_directions"):
        coaching["practice_directions"] = [
            {
                "practice_id": "MAINTAIN_STRENGTHS",
                "mode": "MAINTAIN",
                "mode_label": "유지",
                "title": "현재 잘 유지되고 있는 특징 지키기",
                "goal": "크게 두드러지는 제한이 없을 때 안정적인 패턴 유지",
                "instruction": "편안한 강도로 짧은 지속음을 유지하며, 소리를 과하게 밀지 마세요.",
                "success_cues": ["불편감 없이 짧은 구간 유지", "음량을 갑자기 키우지 않음"],
                "avoid": ["제한이 없는데도 강한 고음·큰 소리로 밀어붙이기"],
                "related_concerns": [],
                "evidence_basis": ["general_discovery"],
                "safety_note": None,
            }
        ]
        coaching["improvement_priorities"] = [
            {
                "goal_id": "MAINTAIN_STRENGTHS",
                "title": "현재 잘 유지되고 있는 특징 지키기",
                "principle": "편안한 강도로 짧은 지속음을 유지하며, 소리를 과하게 밀지 마세요.",
                "suggested_focus": ["불편감 없이 짧은 구간 유지"],
                "safety_note": None,
                "mode": "MAINTAIN",
                "mode_label": "유지",
            }
        ]
    if coaching.get("strengths"):
        features = [s["description"] for s in coaching["strengths"]] + features

    return {
        "mode": DIAGNOSTIC_MODE_GENERAL,
        "title": "정밀 진단에서 확인된 핵심 특징",
        "features": features[:6],
        "questions": [],
        "answer_summary": " · ".join(features[:3]),
        "improvement_priorities": coaching.get("improvement_priorities") or [],
        "coaching": coaching,
        "main_bottleneck": bottleneck,
        "evidence": [
            {"source": "AUDIO_OBSERVED", "text": "노래 분석"},
            *(
                [{"source": "CONTROLLED_TASK_CONFIRMED", "text": f"추가 녹음 {len(task_results)}개"}]
                if task_results
                else []
            ),
        ],
    }


def build_personalized_qa(
    *,
    user_concerns: list[dict[str, Any]],
    song_profile: dict[str, Any],
    task_results: list[dict[str, Any]] | None = None,
    fused_profile: dict[str, Any] | None = None,
    diagnostic_mode: str | None = None,
) -> dict[str, Any]:
    concerns = normalize_user_concerns(user_concerns)
    mode = normalize_diagnostic_mode(diagnostic_mode, concerns)

    if mode == DIAGNOSTIC_MODE_GENERAL or not concerns:
        summary = build_general_discovery_summary(
            song_profile=song_profile,
            task_results=task_results,
        )
        return {
            "mode": DIAGNOSTIC_MODE_GENERAL,
            "question": None,
            "questions": [],
            "answer_summary": summary["answer_summary"],
            "discovered_features": summary["features"],
            "concern_evaluations": [],
            "concern_user_lines": [],
            "evidence": summary["evidence"],
            "main_bottleneck": summary["main_bottleneck"],
            "secondary_factors": _secondary_factors(song_profile),
            "not_supported": [],
            "improvement_priorities": summary["improvement_priorities"],
            "coaching": summary.get("coaching"),
            "confidence_label": "medium",
            "show_qa_section": False,
        }

    task_evidence = fused_profile or {}
    evaluations = [
        evaluate_concern_status(
            c["id"],
            song_profile=song_profile,
            task_evidence=task_evidence,
            task_results=task_results,
        )
        for c in concerns
    ]

    effort_level, _effort_flags = _effort_observed(song_profile)
    reg_level, _reg_flags = _register_observed(song_profile)

    questions: list[dict[str, Any]] = []
    answer_parts: list[str] = []
    not_supported: list[str] = []
    evidence: list[dict[str, str]] = []

    for c, ev in zip(concerns, evaluations):
        cid = str(c["id"])
        q = concern_question_for(cid)
        a = _answer_for_concern(
            cid,
            ev["status"],
            effort_level=effort_level,
            reg_level=reg_level,
            evaluation=ev,
        )
        questions.append(
            {
                "concern_id": cid,
                "question": q,
                "answer": a,
                "status": ev["status"],
                "evidence_level": ev.get("evidence_level"),
                "support": ev.get("support") or [],
                "against": ev.get("against") or [],
                "missing": ev.get("missing") or [],
                "unresolved_reason": ev.get("unresolved_reason"),
                "candidate_causes": ev.get("candidate_causes") or [],
            }
        )
        answer_parts.append(a)
        label = CONCERN_CATALOG.get(cid, {}).get("label", cid)
        if ev["status"] in ("NOT_SUPPORTED_IN_THIS_RECORDING", "NOT_SUPPORTED"):
            not_supported.append(label)

    valid_tasks = [
        tr
        for tr in (task_results or [])
        if not tr.get("invalid") and str((tr.get("quality") or {}).get("status") or "").lower() != "fail"
    ]
    if task_results:
        evidence.append(
            {
                "source": "CONTROLLED_TASK_CONFIRMED",
                "text": (
                    f"{len(task_results)}개 과제를 분석했고, "
                    f"그중 {len(valid_tasks)}개에서 현재 질문에 사용할 수 있는 근거를 확보했어요."
                    if len(valid_tasks) != len(task_results)
                    else f"{len(task_results)}개 과제 결과 반영"
                ),
            }
        )
    evidence.append({"source": "AUDIO_OBSERVED", "text": "노래 분석 evidence"})

    from audio_analyzer.diagnostic.concern_resolver import infer_precision_bottleneck
    from audio_analyzer.diagnostic.coaching import (
        attach_coaching_to_questions,
        build_precision_coaching_plan,
    )

    bn_info = infer_precision_bottleneck(
        song_profile=song_profile,
        fused_profile=task_evidence,
        concern_evaluations=evaluations,
        controlled_contrasts=(task_evidence or {}).get("controlled_contrasts"),
    )
    coaching = build_precision_coaching_plan(
        user_concerns=concerns,
        concern_evaluations=evaluations,
        song_profile=song_profile,
        fused_profile=task_evidence,
        task_results=task_results,
        diagnostic_mode=mode,
    )
    questions = attach_coaching_to_questions(questions, coaching)
    # Prefer coaching practices; pain always uses SAFETY_FIRST guidance
    if has_pain_safety_flag(concerns):
        priorities = build_improvement_guidance(
            song_profile=song_profile,
            evaluations=evaluations,
            pain_flag=True,
            precision_bottleneck=bn_info.get("bottleneck"),
            fused_profile=task_evidence,
        )
        # Keep coaching payload but force safety practice first
        coaching = dict(coaching)
        coaching["practice_directions"] = [
            {
                "practice_id": "SAFETY_FIRST",
                "mode": "SAFETY",
                "mode_label": "안전",
                "title": priorities[0]["title"] if priorities else "불편할 때는 강한 고음·큰 소리 피하기",
                "goal": priorities[0].get("principle") if priorities else "",
                "instruction": priorities[0].get("principle") if priorities else "",
                "success_cues": (priorities[0].get("suggested_focus") or []) if priorities else [],
                "avoid": ["통증 상태에서의 강한 고음 반복"],
                "related_concerns": [c["id"] for c in concerns if c["id"] in (
                    "PAIN_WHILE_SINGING", "PAIN_AFTER_SINGING", "SPEAKING_DISCOMFORT", "PERSISTENT_HOARSENESS"
                )],
                "evidence_basis": ["safety"],
                "safety_note": priorities[0].get("safety_note") if priorities else None,
            }
        ]
        coaching["improvement_priorities"] = priorities
        coaching["headline"] = "지금은 무리한 연습보다 안전이 우선이에요."
    else:
        priorities = coaching.get("improvement_priorities") or build_improvement_guidance(
            song_profile=song_profile,
            evaluations=evaluations,
            pain_flag=False,
            precision_bottleneck=bn_info.get("bottleneck"),
            fused_profile=task_evidence,
        )
    # User-facing evidence families (no "evidence" English / raw tokens)
    evidence_ui = [
        {"source": "FAMILY", "text": t}
        for t in (coaching.get("evidence_families") or [])
    ]
    if not evidence_ui:
        evidence_ui = [
            {"source": "FAMILY", "text": e.get("text")}
            for e in evidence
            if e.get("text") and "evidence" not in str(e.get("text")).lower()
        ]

    from audio_analyzer.diagnostic.song_evidence import get_canonical_snapshot

    song_feats = list(get_canonical_snapshot(song_profile).get("key_features") or [])

    qa = {
        "mode": DIAGNOSTIC_MODE_CONCERN,
        "question": questions[0]["question"] if questions else None,
        "questions": questions,
        "answer_summary": (questions[0].get("takeaway") or questions[0]["answer"])
        if questions
        else "",
        "concern_evaluations": evaluations,
        "concern_user_lines": answer_parts,
        "evidence": evidence_ui,
        "song_key_features": song_feats,
        "main_bottleneck": bn_info.get("bottleneck") or "UNRESOLVED",
        "bottleneck_source": bn_info.get("source"),
        "secondary_factors": _secondary_factors(song_profile),
        "not_supported": not_supported,
        "improvement_priorities": priorities,
        "coaching": coaching,
        "confidence_label": "medium",
        "show_qa_section": True,
        "controlled_contrasts": (task_evidence or {}).get("controlled_contrasts"),
    }
    blob = str(qa.get("answer_summary") or "")
    for banned in BANNED_CLAIM_SUBSTRINGS:
        if banned in blob:
            qa["answer_summary"] = blob.replace(banned, "…")
    for q in qa["questions"]:
        for banned in BANNED_CLAIM_SUBSTRINGS:
            if banned in (q.get("answer") or ""):
                q["answer"] = q["answer"].replace(banned, "…")
    return qa


def _effort_observed(song: dict[str, Any]) -> tuple[str, list[str]]:
    vf = song.get("vocal_function_profile") or {}
    effort = vf.get("effort_assessment") or {}
    sev = (effort.get("severity") or "").upper()
    flags: list[str] = []
    if sev in ("MODERATE", "HIGH", "EXCESS"):
        flags.append("GENERAL_EXCESS_EFFORT")
    coach = vf.get("coaching_decision") or {}
    primary = coach.get("primary_bottleneck") or {}
    if (primary.get("issue_id") or "").upper() in ("EXCESS_EFFORT", "GENERAL_EXCESS_EFFORT"):
        flags.append("PRIMARY_EXCESS_EFFORT")
    level = "HIGH" if sev in ("MODERATE", "HIGH", "EXCESS") else "LOW" if sev == "LOW" else "UNKNOWN"
    return level, flags


def _register_observed(song: dict[str, Any]) -> tuple[str, list[str]]:
    vt = (song.get("vocal_function_profile") or {}).get("vocal_type_profile") or {}
    reg = (vt.get("register_strategy") or {}).get("status") or ""
    bridge = vt.get("bridge") or {}
    suff = (bridge.get("register_sufficiency") or "").upper()
    flags: list[str] = []
    if suff == "INSUFFICIENT" or reg == "UNRESOLVED":
        return "UNRESOLVED", ["REGISTER_INSUFFICIENT"]
    if reg in ("SMOOTH_BRIDGE", "HEAD_DOMINANT", "CHEST_DOMINANT"):
        return "OBSERVED", [f"REGISTER_{reg}"]
    return "PARTIAL", flags


def _breathiness_observed(song: dict[str, Any]) -> tuple[str, list[str]]:
    dims = (song.get("vocal_function_profile") or {}).get("dimensions") or {}
    leak = dims.get("air_leakage_breathiness") or {}
    status = (leak.get("status") or "").upper()
    if status in ("INCREASED", "HIGH", "ELEVATED"):
        return "HIGH", ["AIR_LEAKAGE"]
    if status in ("STABLE", "LOW", "NORMAL"):
        return "LOW", []
    return "UNKNOWN", []


def evaluate_concern_status(
    concern_id: str,
    *,
    song_profile: dict[str, Any],
    task_evidence: Optional[dict[str, Any]] = None,
    task_results: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Map one concern using song + controlled task contrast evidence."""
    from audio_analyzer.diagnostic.concern_resolver import evaluate_concern

    return evaluate_concern(
        concern_id,
        song_profile=song_profile,
        task_evidence=task_evidence,
        task_results=task_results,
    )


def _status_user_line(status: str, label: str) -> str:
    if status == "CONFIRMED":
        return f"느끼셨던 '{label}'이(가) 이번 분석에서도 확인됐어요."
    if status == "PARTIALLY_SUPPORTED":
        return f"'{label}'과(와) 비슷한 변화가 일부 구간에서 보였어요."
    if status == "NOT_SUPPORTED_IN_THIS_RECORDING":
        return f"이번 녹음에서는 '{label}'과(와) 일치하는 패턴이 뚜렷하지 않았어요."
    if status == "SAFETY_ONLY":
        return f"'{label}'은(는) 안전 관련 신호로 기록됐어요. 음향 분석만으로 원인을 단정하지 않아요."
    return f"'{label}'은(는) 이번 녹음만으로는 충분히 확인하기 어려웠어요."


def _infer_bottleneck(song: dict[str, Any]) -> str:
    coach = (song.get("vocal_function_profile") or {}).get("coaching_decision") or {}
    primary = coach.get("primary_bottleneck") or {}
    issue = (primary.get("issue_id") or primary.get("id") or "").upper()
    mapping = {
        "GENERAL_EXCESS_EFFORT": "HIGH_NOTE_EFFORT",
        "EXCESS_EFFORT": "HIGH_NOTE_EFFORT",
        "AIR_LEAK_BREATHINESS": "AIR_LEAKAGE",
        "REGISTER_TRANSITION_DISRUPTION": "REGISTER_TRANSITION_DISRUPTION",
    }
    return mapping.get(issue, issue or "UNRESOLVED")


def _secondary_factors(song: dict[str, Any]) -> list[str]:
    vf = song.get("vocal_function_profile") or {}
    out: list[str] = []
    vt = vf.get("vocal_type_profile") or {}
    if (vt.get("register_strategy") or {}).get("status") == "UNRESOLVED":
        out.append("register_unresolved")
    effort = vf.get("effort_assessment") or {}
    if (effort.get("severity") or "").upper() == "MODERATE":
        out.append("moderate_effort")
    return out


def build_improvement_guidance(
    *,
    song_profile: dict[str, Any],
    evaluations: list[dict[str, Any]],
    pain_flag: bool,
    precision_bottleneck: str | None = None,
    fused_profile: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if pain_flag:
        return [
            {
                "goal_id": "SAFETY_FIRST",
                "title": "불편한 상태에서는 강한 고음·큰 소리 반복을 피하기",
                "principle": "통증이나 지속적인 불편감은 음향 분석만으로 원인을 판단할 수 없어요.",
                "suggested_focus": [
                    "불편할 때는 짧게 쉬기",
                    "통증·쉰 느낌이 반복되면 전문 진료 고려",
                ],
                "safety_note": (
                    "통증이나 쉰 느낌이 반복되거나 지속된다면 "
                    "이비인후과 또는 음성 전문 진료를 권장합니다."
                ),
            }
        ]

    bottleneck = precision_bottleneck or _infer_bottleneck(song_profile)
    # Promote from confirmed evaluations when song bottleneck empty
    if bottleneck in ("", "UNRESOLVED", None):
        for ev in evaluations:
            if ev.get("status") not in ("CONFIRMED", "PARTIALLY_SUPPORTED"):
                continue
            causes = ev.get("candidate_causes") or []
            if "EFFORT_ESCALATION_WITH_HEIGHT" in causes:
                bottleneck = "HIGH_NOTE_EFFORT"
                break
            if "LOW_PRESENCE" in causes or "LOW_BRIGHTNESS" in causes:
                bottleneck = "LOW_PRESENCE"
                break
            if "HIGH_AIRINESS" in causes:
                bottleneck = "AIR_LEAKAGE"
                break
            if "REGISTER_TRANSITION_DISRUPTION" in causes:
                bottleneck = "REGISTER_TRANSITION_DISRUPTION"
                break
            if "HIGH_NOTE_STABILITY_DROP" in causes:
                bottleneck = "HIGH_NOTE_STABILITY_DROP"
                break

    out: list[dict[str, Any]] = []

    if bottleneck in ("HIGH_NOTE_EFFORT", "GENERAL_EXCESS_EFFORT", "EXCESS_EFFORT"):
        out.append(
            {
                "goal_id": "REDUCE_HIGH_NOTE_EFFORT",
                "title": "고음에서 힘 증가 줄이기",
                "principle": "높은 음에서 음량을 더 키우기보다 낮은 effort로 같은 음을 유지하는 연습",
                "suggested_focus": [
                    "작은 강도에서 높은 음 연결",
                    "중간 강도에서 고음 연결을 먼저 안정시키기",
                ],
                "safety_note": None,
                "evidence_source": "TASK" if fused_profile else "SONG",
            }
        )
    if bottleneck == "REGISTER_TRANSITION_DISRUPTION":
        out.append(
            {
                "goal_id": "REGISTER_TRANSITION",
                "title": "중음→고음 연결 안정화",
                "principle": "전환 구간에서 갑자기 소리를 밀어붙이지 않고 연속적으로 연결",
                "suggested_focus": ["작은 강도로 부드러운 사이렌 연습"],
                "safety_note": None,
            }
        )
    if bottleneck == "AIR_LEAKAGE":
        out.append(
            {
                "goal_id": "AIRINESS_CONTROL",
                "title": "숨 섞임 조절하기",
                "principle": "숨이 과하게 섞이지 않는 안정적인 발성 상태를 낮은 강도에서 유지",
                "suggested_focus": ["짧은 지속음에서 안정적인 접촉 유지"],
                "safety_note": None,
            }
        )
    if bottleneck == "LOW_PRESENCE":
        out.append(
            {
                "goal_id": "PRESENCE_BALANCE",
                "title": "음색의 중역 존재감 유지하기",
                "principle": "답답하거나 얇게 들릴 때는 중역 존재감을 과도하게 막지 않는 방향으로 관찰",
                "suggested_focus": ["편한 강도에서 음색 변화 관찰"],
                "safety_note": None,
            }
        )
    if bottleneck == "HIGH_NOTE_STABILITY_DROP":
        out.append(
            {
                "goal_id": "HIGH_NOTE_STABILITY",
                "title": "고음 안정성 유지하기",
                "principle": "높은 음에서 흔들림이 커질 때 강도·범위를 줄여 안정 구간부터 확장",
                "suggested_focus": ["짧은 고음 지속에서 안정 유지"],
                "safety_note": None,
            }
        )

    # Avoid generic fallback when clear derived issue exists
    has_clear = any(
        ev.get("status") in ("CONFIRMED", "PARTIALLY_SUPPORTED") for ev in evaluations
    )
    if not out and not has_clear:
        out.append(
            {
                "goal_id": "GENERAL_AWARENESS",
                "title": "현재 발성 패턴 관찰하기",
                "principle": "확인된 bottleneck이 충분하지 않을 때는 무리한 훈련보다 관찰 우선",
                "suggested_focus": ["편안한 강도에서 반복 녹음으로 변화 추적"],
                "safety_note": None,
            }
        )
    elif not out and has_clear:
        # Soft target from first confirmed concern
        for ev in evaluations:
            if ev.get("status") in ("CONFIRMED", "PARTIALLY_SUPPORTED"):
                cid = ev.get("concern_id") or ev.get("concern")
                out.append(
                    {
                        "goal_id": f"FOCUS_{cid}",
                        "title": "확인된 발성 특징 중심으로 관찰하기",
                        "principle": "이번 정밀 검사에서 확인된 특징을 우선 추적해요.",
                        "suggested_focus": ["같은 조건으로 짧게 다시 녹음해 변화 비교"],
                        "safety_note": None,
                    }
                )
                break
    return out[:3]


def public_concern_catalog() -> dict[str, Any]:
    categories = [
        ("high_note", "고음"),
        ("effort", "힘·피로"),
        ("timbre", "음색"),
        ("control", "컨트롤"),
        ("safety", "통증·불편"),
    ]
    groups = []
    for cat_id, cat_label in categories:
        items = [
            {"id": cid, "label": meta["label"]}
            for cid, meta in CONCERN_CATALOG.items()
            if meta["category"] == cat_id
        ]
        groups.append({"category_id": cat_id, "category_label": cat_label, "concerns": items})
    return {
        "max_concerns": MAX_CONCERNS,
        "follow_up_options": FOLLOW_UP_OPTIONS,
        "groups": groups,
    }
