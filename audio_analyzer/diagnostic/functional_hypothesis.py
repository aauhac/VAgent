"""Song-evidence functional hypothesis + always-actionable guidance (Precision Guidance v2).

CONTROLLED TASK SKIPPED ≠ NO ANSWER
USER_REPORTED ≠ AUDIO_OBSERVED
No anatomical / 복압 / CT-TA claims.
"""

from __future__ import annotations

from typing import Any, Optional

from audio_analyzer.diagnostic.practice_library import practice_for_focus
from audio_analyzer.diagnostic.song_evidence import get_canonical_snapshot

GUIDANCE_CONTROLLED = "CONTROLLED_CONFIRMED"
GUIDANCE_SONG_DIRECT = "SONG_DIRECT"
GUIDANCE_SONG_COMPOSITE = "SONG_COMPOSITE"
GUIDANCE_SAFE_GENERAL = "SAFE_GENERAL_GUIDANCE"
GUIDANCE_SAFETY = "SAFETY_ONLY"

CONCERN_GUIDANCE_VERSION = "precision-concern-guidance-v1.0"

_BAD_FINAL_SUBSTRINGS = (
    "연습 방향을 충분히 좁히기 어려워요",
    "고음 힘 패턴을 충분히 확정하기 어려워요",
    "현재 노래에서 확인된 범위까지만 안내해요",
)

_BANNED_USER_SUBSTRINGS = (
    "복압이 부족",
    "횡격막이 약",
    "목 근육",
    "후두가 올라",
    "성대가 너무 붙",
    "성대가 벌어",
    "중음역이 약",
    "중음역대가 약",
    "TA",
    "CT",
    "LCA",
)


def _reg_bucket(snap: dict[str, Any]) -> str:
    reg = snap.get("register") or {}
    st = str(reg.get("status") or "").upper()
    if st in ("DISRUPTED", "UNSTABLE", "TRANSITION_EVENTS", "BREAK", "FAIL", "ABRUPT"):
        return "DISRUPTED"
    if st in ("PARTIAL", "INSUFFICIENT", "MIXED"):
        return "PARTIAL"
    if st in ("CONNECTED", "SMOOTH", "STABLE", "CONTINUOUS", "STABLE_LIKE"):
        return "CONNECTED"
    # canonical_register on vocal style / type
    return "UNKNOWN"


def _effort_bucket(snap: dict[str, Any]) -> str:
    return str((snap.get("effort") or {}).get("level") or "UNKNOWN").upper()


def _contact_bucket(snap: dict[str, Any]) -> str:
    return str((snap.get("contact") or {}).get("status") or "UNKNOWN").upper()


def _presence_low(snap: dict[str, Any]) -> bool:
    timbre = snap.get("timbre") or {}
    p = timbre.get("presence")
    if p is None:
        return False
    try:
        return float(p) <= 0.42
    except (TypeError, ValueError):
        return False


def _stability_ok(snap: dict[str, Any]) -> Optional[bool]:
    st = str((snap.get("stability") or {}).get("status") or "").upper()
    if not st or st == "UNKNOWN":
        return None
    if st in ("STABLE", "LOW", "NORMAL", "OK_PROXY"):
        return True
    if st in ("UNSTABLE", "HIGH", "IRREGULAR"):
        return False
    return None


def _scope_note_for_skip(skipped: set[str], concern_id: str) -> Optional[str]:
    if "siren" in skipped and concern_id in (
        "HIGH_NOTE_CANNOT_REACH",
        "HIGH_NOTE_FLIPS",
        "REGISTER_CONNECTION_DIFFICULT",
    ):
        return "추가 성구 과제를 진행하지 않아 이 해석은 현재 노래 기준입니다."
    if "high_note_sustain_a" in skipped and concern_id in (
        "HIGH_NOTE_TOO_EFFORTFUL",
        "HIGH_NOTE_CANNOT_REACH",
        "HIGH_NOTE_UNSTABLE",
        "HIGH_NOTE_THINS",
    ):
        return "추가 고음 과제를 진행하지 않아 이 해석은 현재 노래 기준입니다."
    return None


def _attach_practice(
    hyp: dict[str, Any],
    *,
    category: str = "",
    snap: Optional[dict[str, Any]] = None,
    timbre_goal: Any = None,
) -> dict[str, Any]:
    from audio_analyzer.diagnostic.general_guidance import finalize_actionable_qa

    if hyp.get("practice_required") is False:
        hyp["practice"] = None
        hyp["practice_id"] = None
        return finalize_actionable_qa(hyp, snap, timbre_goal=timbre_goal)
    focus = str(hyp.get("primary_focus") or "MAINTAIN")
    practice = practice_for_focus(focus, category=category)
    hyp["practice"] = practice
    hyp["practice_id"] = (practice or {}).get("practice_id")
    return finalize_actionable_qa(hyp, snap, timbre_goal=timbre_goal)


def build_functional_hypothesis(
    concern_id: str,
    *,
    song_profile: dict[str, Any],
    evaluation: Optional[dict[str, Any]] = None,
    user_skipped_tasks: Optional[set[str]] = None,
    timbre_goal: Any = None,
) -> dict[str, Any]:
    """Build actionable guidance from canonical song evidence (never invent anatomy)."""
    from audio_analyzer.diagnostic.concern_reasoning import reason_about_concern
    from audio_analyzer.diagnostic.general_guidance import finalize_actionable_qa
    from audio_analyzer.diagnostic.question_semantics import semantics_for

    # Dynamic QA v3 path — structured multi-axis reasoning by concern_id
    reasoned = reason_about_concern(
        concern_id,
        song_profile=song_profile,
        evaluation=evaluation,
        user_skipped_tasks=user_skipped_tasks,
        timbre_goal=timbre_goal,
    )
    snap = get_canonical_snapshot(song_profile)
    if not reasoned.get("defer_to_legacy"):
        # Map structured reasoning into hyp shape used by compose_user_answer
        hyp = {
            "concern_id": concern_id,
            "question_type": reasoned.get("question_type"),
            "guidance_level": reasoned.get("guidance_level"),
            "primary_focus": reasoned.get("primary_focus"),
            "secondary_factors": reasoned.get("secondary_factors") or [],
            "interpretation": reasoned.get("interpretation"),
            "evidence": reasoned.get("evidence") or [],
            "contra_evidence": reasoned.get("contra_evidence") or [],
            "confidence_label": reasoned.get("confidence_label") or "medium",
            "causal_certainty": reasoned.get("causal_certainty"),
            "scope_note": reasoned.get("scope_note"),
            "practice_required": reasoned.get("practice_required", True),
            "primary_explanation": reasoned.get("primary_explanation"),
            "supporting_explanations": reasoned.get("supporting_explanations") or [],
            "less_likely_explanations": reasoned.get("less_likely_explanations") or [],
            "uncertain_factors": reasoned.get("uncertain_factors") or [],
            "evidence_used": reasoned.get("evidence_used") or [],
            "practice": reasoned.get("practice"),
            "practice_id": reasoned.get("practice_id"),
        }
        return finalize_actionable_qa(hyp, snap, timbre_goal=timbre_goal)

    # Legacy high-note / remaining paths below
    snap = get_canonical_snapshot(song_profile)
    skipped = set(user_skipped_tasks or [])
    ev = evaluation or {}
    effort = _effort_bucket(snap)
    contact = _contact_bucket(snap)
    register = _reg_bucket(snap)
    presence_low = _presence_low(snap)
    stab = _stability_ok(snap)
    breath = str((snap.get("breathiness") or {}).get("level") or "UNKNOWN").upper()
    sem = semantics_for(concern_id)
    category = str(sem.get("category") or "")

    secondary: list[str] = []
    evidence: list[str] = []
    contra: list[str] = []
    scope = _scope_note_for_skip(skipped, concern_id)

    # --- SAFETY ---
    if str(ev.get("status") or "").upper() == "SAFETY_ONLY" or concern_id.startswith("PAIN"):
        hyp = {
            "concern_id": concern_id,
            "guidance_level": GUIDANCE_SAFETY,
            "primary_focus": "SAFETY",
            "secondary_factors": [],
            "interpretation": (
                "통증이나 지속적인 불편감은 음향 분석만으로 원인을 판단할 수 없어요. "
                "지금은 강한 고음·큰 소리 반복보다 휴식이 우선이에요."
            ),
            "evidence": ["safety"],
            "contra_evidence": [],
            "confidence_label": "high",
            "causal_certainty": "SAFETY_GATE",
            "scope_note": None,
        }
        return _attach_practice(hyp, category="safety", snap=snap, timbre_goal=timbre_goal)

    # Controlled already confirmed — keep tone, still ensure practice
    st = str(ev.get("status") or "").upper()
    if st == "CONFIRMED" and ev.get("answer_hint") and not skipped:
        hyp = {
            "concern_id": concern_id,
            "guidance_level": GUIDANCE_CONTROLLED,
            "primary_focus": (ev.get("candidate_causes") or ["EFFORT"])[0]
            if "EFFORT" in str(ev.get("candidate_causes"))
            else "REGISTER_CONNECTION"
            if "REGISTER" in str(ev.get("candidate_causes"))
            else "EFFORT",
            "secondary_factors": [],
            "interpretation": str(ev.get("answer_hint")),
            "evidence": list(ev.get("support") or []),
            "contra_evidence": list(ev.get("against") or []),
            "confidence_label": ev.get("confidence_label") or "medium",
            "causal_certainty": "CONTROLLED_CONFIRMED",
            "scope_note": None,
        }
        # Map cause ids to focus
        causes = ev.get("candidate_causes") or []
        if any("REGISTER" in str(c) for c in causes):
            hyp["primary_focus"] = "REGISTER_CONNECTION"
        elif any("EFFORT" in str(c) for c in causes):
            hyp["primary_focus"] = "EFFORT"
        elif any("STABILITY" in str(c) for c in causes):
            hyp["primary_focus"] = "STABILITY"
        return _attach_practice(hyp, category=category, snap=snap, timbre_goal=timbre_goal)

    # ========== High-note cannot reach ==========
    if concern_id == "HIGH_NOTE_CANNOT_REACH":
        if register == "DISRUPTED":
            hyp = {
                "concern_id": concern_id,
                "guidance_level": GUIDANCE_SONG_DIRECT,
                "primary_focus": "REGISTER_CONNECTION",
                "secondary_factors": [],
                "interpretation": (
                    "이번 노래에서는 음역이 올라갈 때 발성 연결이 급격하게 달라지는 구간이 보여요. "
                    "그래서 높은 음 자체의 부족이라기보다, 중간 음역에서 높은 음으로 넘어가는 과정이 "
                    "현재 고음 접근을 어렵게 만드는 쪽으로 보입니다."
                ),
                "evidence": ["song_register_disrupted"],
                "contra_evidence": [],
                "confidence_label": "medium",
                "causal_certainty": "FUNCTIONAL_HYPOTHESIS",
                "scope_note": scope,
            }
            if effort in ("HIGH", "MODERATE"):
                hyp["secondary_factors"] = ["EFFORT"]
            return _attach_practice(hyp, category=category, snap=snap, timbre_goal=timbre_goal)

        if register == "PARTIAL" and (effort in ("HIGH", "MODERATE") or contact == "FIRM"):
            bits = ["음역이 올라갈 때 연결이 충분히 이어지지 않는 구간이 있고"]
            if effort in ("HIGH", "MODERATE"):
                bits.append("힘 사용")
                evidence.append("song_effort_elevated")
                secondary.append("EFFORT")
            if contact == "FIRM":
                bits.append("단단한 접촉 특성")
                evidence.append("song_contact_firm")
                secondary.append("CONTACT")
            mid = "과 ".join(bits) if len(bits) > 1 else bits[0]
            # Fix awkward join
            if len(secondary) >= 1:
                factors = []
                if "EFFORT" in secondary:
                    factors.append("힘 사용")
                if "CONTACT" in secondary:
                    factors.append("단단한 접촉 특성")
                factor_txt = "과 ".join(factors) if factors else "관련 특성"
                interpretation = (
                    f"이번 노래에서는 높은 음으로 이동할 때 연결이 충분히 이어지지 않는 구간이 있고, "
                    f"{factor_txt}도 함께 나타나요. "
                    "높은 음을 같은 무게와 힘으로 유지하려는 방식이 "
                    "고음 접근을 어렵게 만드는 쪽으로 보여요."
                )
            else:
                interpretation = (
                    "이번 노래에서는 높은 음으로 이동할 때 연결이 충분히 이어지지 않는 구간이 보여요."
                )
            hyp = {
                "concern_id": concern_id,
                "guidance_level": GUIDANCE_SONG_COMPOSITE,
                "primary_focus": "REGISTER_CONNECTION",
                "secondary_factors": secondary[:2],
                "interpretation": interpretation,
                "evidence": ["song_register_partial", *evidence],
                "contra_evidence": [],
                "confidence_label": "medium",
                "causal_certainty": "FUNCTIONAL_HYPOTHESIS",
                "scope_note": scope,
            }
            return _attach_practice(hyp, category=category, snap=snap, timbre_goal=timbre_goal)

        if register == "PARTIAL":
            hyp = {
                "concern_id": concern_id,
                "guidance_level": GUIDANCE_SONG_DIRECT,
                "primary_focus": "REGISTER_CONNECTION",
                "secondary_factors": [],
                "interpretation": (
                    "이번 노래에서는 중음에서 높은 음으로 넘어가는 연결이 "
                    "일부 구간에서만 안정적으로 이어져요. "
                    "고음 접근이 어려운 느낌은 이 전환 구간의 연결과 관련될 가능성이 있어 보여요."
                ),
                "evidence": ["song_register_partial"],
                "contra_evidence": [],
                "confidence_label": "medium",
                "causal_certainty": "FUNCTIONAL_HYPOTHESIS",
                "scope_note": scope,
            }
            return _attach_practice(hyp, category=category, snap=snap, timbre_goal=timbre_goal)

        if effort in ("HIGH", "MODERATE"):
            hyp = {
                "concern_id": concern_id,
                "guidance_level": GUIDANCE_SONG_DIRECT,
                "primary_focus": "EFFORT",
                "secondary_factors": ["CONTACT"] if contact == "FIRM" else [],
                "interpretation": (
                    "이번 노래에서는 성구 전환을 단정하기는 어렵지만, "
                    "일부 구간에서 힘 사용이 커지는 경향이 보여요. "
                    "높은 음에 도달하려 할 때 강도를 먼저 키우는 방식이 "
                    "접근을 어렵게 만드는 쪽으로 보일 수 있어요."
                ),
                "evidence": ["song_effort_elevated"],
                "contra_evidence": [],
                "confidence_label": "low",
                "causal_certainty": "FUNCTIONAL_HYPOTHESIS",
                "scope_note": scope,
            }
            return _attach_practice(hyp, category=category, snap=snap, timbre_goal=timbre_goal)

        hyp = {
            "concern_id": concern_id,
            "guidance_level": GUIDANCE_SAFE_GENERAL,
            "primary_focus": "REGISTER_CONNECTION",
            "secondary_factors": [],
            "interpretation": (
                "높은 음에 닿으려면 세게 밀기보다, "
                "편안한 중음에서 작은 강도로 연결하는 쪽을 먼저 비교해보세요."
            ),
            "evidence": [],
            "contra_evidence": [],
            "confidence_label": "low",
            "causal_certainty": "GUIDANCE_ONLY",
            "scope_note": scope,
        }
        return _attach_practice(hyp, category=category, snap=snap, timbre_goal=timbre_goal)

    # ========== High-note flips ==========
    if concern_id == "HIGH_NOTE_FLIPS":
        if register == "DISRUPTED":
            hyp = {
                "concern_id": concern_id,
                "guidance_level": GUIDANCE_SONG_DIRECT,
                "primary_focus": "REGISTER_CONNECTION",
                "secondary_factors": [],
                "interpretation": (
                    "이번 노래에서는 음역이 올라가는 구간에서 발성 연결이 갑자기 달라지는 패턴이 보여요. "
                    "느끼신 '뒤집힘'은 현재 분석에서 확인된 성구 연결 변화와 어느 정도 일치합니다."
                ),
                "evidence": ["song_register_disrupted"],
                "contra_evidence": [],
                "confidence_label": "medium",
                "causal_certainty": "FUNCTIONAL_HYPOTHESIS",
                "scope_note": scope,
            }
            if presence_low:
                hyp["interpretation"] += (
                    " 중역 존재감도 낮은 편이라, 전환 구간에서 음색이나 소리 존재감이 "
                    "함께 달라질 수 있어 보여요."
                )
                hyp["secondary_factors"] = ["PRESENCE"]
            return _attach_practice(hyp, category=category, snap=snap, timbre_goal=timbre_goal)
        if register == "PARTIAL":
            hyp = {
                "concern_id": concern_id,
                "guidance_level": GUIDANCE_SONG_DIRECT,
                "primary_focus": "REGISTER_CONNECTION",
                "secondary_factors": ["PRESENCE"] if presence_low else [],
                "interpretation": (
                    "이번 노래에서는 중음에서 높은 음으로 넘어가는 연결이 "
                    "일부 구간에서만 안정적으로 이어져요. "
                    "따라서 뒤집힘은 전환 구간의 연결이 아직 일정하지 않은 점과 "
                    "관련되어 있을 가능성이 있어 보여요."
                    + (
                        " 중역 존재감도 낮은 편이라 전환에서 소리 존재감이 함께 달라질 수 있어 보여요."
                        if presence_low
                        else ""
                    )
                ),
                "evidence": ["song_register_partial"],
                "contra_evidence": [],
                "confidence_label": "medium",
                "causal_certainty": "FUNCTIONAL_HYPOTHESIS",
                "scope_note": scope,
            }
            return _attach_practice(hyp, category=category, snap=snap, timbre_goal=timbre_goal)
        hyp = {
            "concern_id": concern_id,
            "guidance_level": GUIDANCE_SAFE_GENERAL,
            "primary_focus": "REGISTER_CONNECTION",
            "secondary_factors": [],
            "interpretation": (
                "현재 노래에서는 뒤집힘과 직접 연결되는 특징이 뚜렷하게 잡히지 않았어요. "
                "지금은 작은 강도의 립트릴이나 빨대 발성으로 "
                "중음에서 높은 음까지 끊기지 않게 연결하는 연습부터 시작하는 것이 좋아요."
            ),
            "evidence": [],
            "contra_evidence": [],
            "confidence_label": "low",
            "causal_certainty": "GUIDANCE_ONLY",
            "scope_note": scope,
        }
        return _attach_practice(hyp, category=category, snap=snap, timbre_goal=timbre_goal)

    if concern_id == "HIGH_NOTE_UNSTABLE":
        if stab is False:
            hyp = {
                "concern_id": concern_id,
                "guidance_level": GUIDANCE_SONG_DIRECT,
                "primary_focus": "STABILITY",
                "secondary_factors": [],
                "interpretation": (
                    "이번 노래에서는 고음·지속 구간에서 안정성이 떨어지는 패턴이 보여요. "
                    "짧은 안정 구간을 유지한 뒤 범위를 넓히는 연습이 적합해 보여요."
                ),
                "evidence": ["song_stability"],
                "contra_evidence": [],
                "confidence_label": "medium",
                "causal_certainty": "FUNCTIONAL_HYPOTHESIS",
                "scope_note": scope,
            }
            return _attach_practice(hyp, category=category, snap=snap, timbre_goal=timbre_goal)
        hyp = {
            "concern_id": concern_id,
            "guidance_level": GUIDANCE_SAFE_GENERAL,
            "primary_focus": "STABILITY",
            "secondary_factors": [],
            "interpretation": (
                "현재 노래에서는 고음 흔들림과 직접 연결되는 특징이 뚜렷하게 잡히지 않았어요. "
                "짧은 안정 구간을 유지한 뒤 조금씩 범위를 넓히는 연습부터 시작하는 것이 좋아요."
            ),
            "evidence": [],
            "contra_evidence": [],
            "confidence_label": "low",
            "causal_certainty": "GUIDANCE_ONLY",
            "scope_note": scope,
        }
        return _attach_practice(hyp, category=category, snap=snap, timbre_goal=timbre_goal)

    # Default category fallback — never force register glide for timbre/effort/control
    focus = str(sem.get("fallback_focus") or "MAINTAIN")
    from audio_analyzer.diagnostic.concern_reasoning import _fallback_interpretation

    focus2, interpretation = _fallback_interpretation(category or "other", concern_id)
    hyp = {
        "concern_id": concern_id,
        "guidance_level": GUIDANCE_SAFE_GENERAL,
        "primary_focus": focus2 or focus,
        "secondary_factors": [],
        "interpretation": interpretation,
        "evidence": [],
        "contra_evidence": [],
        "confidence_label": "low",
        "causal_certainty": "GUIDANCE_ONLY",
        "scope_note": scope,
        "practice_required": bool(sem.get("practice_required", True)),
    }
    return _attach_practice(hyp, category=category or "other", snap=snap, timbre_goal=timbre_goal)


# Keep helper symbols used by tests / callers that imported private names via module

def compose_user_answer(hyp: dict[str, Any]) -> str:
    """Primary answer: observed interpretation + short next step. Full practice stays in coaching."""
    from audio_analyzer.diagnostic.general_guidance import fix_korean_suffixes, public_answer_text

    text = public_answer_text(hyp)
    scope = hyp.get("scope_note")
    if scope:
        text = f"{text}\n\n({scope})"
    for bad in _BANNED_USER_SUBSTRINGS:
        if bad in text:
            text = text.replace(bad, "")
    return fix_korean_suffixes(text).strip()


def _copy_qa_contract(out: dict[str, Any], hyp: dict[str, Any]) -> None:
    out["observed"] = hyp.get("observed") or []
    out["knowledge_support"] = hyp.get("knowledge_support")
    out["knowledge_support_internal"] = hyp.get("knowledge_support_internal", True)
    out["what_to_change"] = hyp.get("what_to_change")
    out["action"] = hyp.get("action")
    out["success_cues"] = hyp.get("success_cues") or []
    out["avoid"] = hyp.get("avoid") or []
    out["knowledge_scope"] = hyp.get("knowledge_scope")
    out["interpretation"] = hyp.get("interpretation") or out.get("interpretation")
    out["answer_mode"] = hyp.get("answer_mode")
    out["response_mode"] = hyp.get("response_mode") or hyp.get("answer_mode")
    out["working_direction"] = hyp.get("working_direction")
    out["comparison"] = hyp.get("comparison") or hyp.get("comparison_protocol")
    out["comparison_protocol"] = out["comparison"]
    out["counts_for_consensus"] = hyp.get("counts_for_consensus")
    if hyp.get("evidence_used") is not None:
        out["evidence_used"] = hyp.get("evidence_used")


def ensure_actionable_guidance(
    evaluation: dict[str, Any],
    *,
    song_profile: dict[str, Any],
    user_skipped_tasks: Optional[set[str]] = None,
    timbre_goal: Any = None,
) -> dict[str, Any]:
    """Enrich concern evaluation so skip never leaves a useless final answer."""
    out = dict(evaluation or {})
    cid = str(out.get("concern_id") or out.get("concern") or "")
    if not cid:
        return out

    status = str(out.get("status") or "").upper()
    if status == "SAFETY_ONLY":
        hyp = build_functional_hypothesis(
            cid,
            song_profile=song_profile,
            evaluation=out,
            user_skipped_tasks=user_skipped_tasks,
            timbre_goal=timbre_goal,
        )
        out["guidance_level"] = GUIDANCE_SAFETY
        out["primary_focus"] = "SAFETY"
        out["functional_hypothesis"] = hyp
        out["answer_hint"] = compose_user_answer(hyp)
        out["practice"] = hyp.get("practice")
        _copy_qa_contract(out, hyp)
        return out

    skipped = set(user_skipped_tasks or [])
    # Preserve skip provenance without terminating reasoning
    if out.get("unresolved_reason") == "USER_SKIPPED_RELEVANT_TASK":
        out["controlled_confirmation"] = "NOT_AVAILABLE_USER_SKIPPED"
        # Do not keep skip-only answer as primary
        hint = str(out.get("answer_hint") or "")
        if any(b in hint for b in _BAD_FINAL_SUBSTRINGS) or "건너뛰어" in hint:
            out["answer_hint"] = None

    hyp = build_functional_hypothesis(
        cid,
        song_profile=song_profile,
        evaluation=out,
        user_skipped_tasks=skipped,
        timbre_goal=timbre_goal,
    )

    # If controlled CONFIRMED already had a strong answer, prefer it but attach practice
    if status == "CONFIRMED" and out.get("answer_hint") and not skipped:
        out["guidance_level"] = GUIDANCE_CONTROLLED
        out["primary_focus"] = hyp.get("primary_focus")
        out["practice"] = hyp.get("practice")
        out["functional_hypothesis"] = hyp
        # Ensure practice appended if takeaway-only
        if "\n\n→ " not in str(out.get("answer_hint")):
            out["answer_hint"] = compose_user_answer(
                {**hyp, "interpretation": out["answer_hint"]}
            )
        _copy_qa_contract(out, hyp)
        return out

    out["guidance_level"] = hyp["guidance_level"]
    out["primary_focus"] = hyp.get("primary_focus")
    out["secondary_factors"] = hyp.get("secondary_factors") or []
    out["question_type"] = hyp.get("question_type")
    out["practice_required"] = hyp.get("practice_required", True)
    out["functional_hypothesis"] = hyp
    out["practice"] = hyp.get("practice")
    out["answer_hint"] = compose_user_answer(hyp)
    out["interpretation"] = hyp.get("interpretation")
    out["song_evidence_used"] = list(
        dict.fromkeys([*(out.get("song_evidence_used") or []), *(hyp.get("evidence") or [])])
    )
    _copy_qa_contract(out, hyp)
    # Soften status for song guidance paths without claiming controlled confirmation
    if status in ("UNRESOLVED", "") and hyp["guidance_level"] in (
        GUIDANCE_SONG_DIRECT,
        GUIDANCE_SONG_COMPOSITE,
    ):
        out["status"] = "PARTIALLY_SUPPORTED"
        out["evidence_level"] = "SONG_SUPPORTED"
    elif status in ("UNRESOLVED", "") and hyp["guidance_level"] == GUIDANCE_SAFE_GENERAL:
        out["status"] = "UNRESOLVED"
        out["evidence_level"] = "INSUFFICIENT"
    if skipped:
        out["controlled_confirmation"] = out.get("controlled_confirmation") or (
            "NOT_AVAILABLE_USER_SKIPPED"
        )
    return out


def assert_no_banned_claims(text: str) -> bool:
    return not any(b in (text or "") for b in _BANNED_USER_SUBSTRINGS)
