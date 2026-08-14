"""Dynamic concern reasoning (QA v3).

concern_id → question semantics → canonical evidence → structured explanation.
Same concern + different evidence ⇒ different primary / answer / practice.
"""

from __future__ import annotations

from typing import Any, Optional

from audio_analyzer.diagnostic.practice_library import practice_for_focus
from audio_analyzer.diagnostic.question_semantics import (
    FACTOR_BREATHINESS,
    FACTOR_BRIGHTNESS,
    FACTOR_CONTACT,
    FACTOR_DYNAMICS,
    FACTOR_EFFORT,
    FACTOR_MAINTAIN,
    FACTOR_PRESENCE,
    FACTOR_REGISTER,
    FACTOR_SAFETY,
    FACTOR_STABILITY,
    FACTOR_TIMBRE,
    TYPE_CONTROL,
    TYPE_DESCRIPTIVE,
    TYPE_FUNCTIONAL,
    TYPE_PERCEPTUAL,
    TYPE_SAFETY,
    semantics_for,
)
from audio_analyzer.diagnostic.song_evidence import get_canonical_snapshot

GUIDANCE_CONTROLLED = "CONTROLLED_CONFIRMED"
GUIDANCE_SONG_DIRECT = "SONG_DIRECT"
GUIDANCE_SONG_COMPOSITE = "SONG_COMPOSITE"
GUIDANCE_SAFE_GENERAL = "SAFE_GENERAL_GUIDANCE"
GUIDANCE_SAFETY = "SAFETY_ONLY"

SCOPE_SONG = "SONG"
SCOPE_CONTROLLED = "CONTROLLED"
SCOPE_BOTH = "SONG_AND_CONTROLLED"
SCOPE_USER = "USER_REPORTED"


def _reg(snap: dict[str, Any]) -> str:
    st = str((snap.get("register") or {}).get("status") or "").upper()
    if st in ("DISRUPTED", "UNSTABLE", "TRANSITION_EVENTS", "BREAK", "FAIL", "ABRUPT"):
        return "DISRUPTED"
    if st in ("PARTIAL", "INSUFFICIENT", "MIXED"):
        return "PARTIAL"
    if st in ("CONNECTED", "SMOOTH", "STABLE", "CONTINUOUS", "STABLE_LIKE"):
        return "CONNECTED"
    return "UNKNOWN"


def _high_note_available(snap: dict[str, Any]) -> bool:
    return bool((snap.get("high_note") or {}).get("available"))


def _chest_tendency(snap: dict[str, Any]) -> Optional[str]:
    from audio_analyzer.diagnostic.general_guidance import chest_tendency

    return chest_tendency(snap)


def _effort(snap: dict[str, Any]) -> str:
    return str((snap.get("effort") or {}).get("level") or "UNKNOWN").upper()


def _contact(snap: dict[str, Any]) -> str:
    return str((snap.get("contact") or {}).get("status") or "UNKNOWN").upper()


def _breath(snap: dict[str, Any]) -> str:
    return str((snap.get("breathiness") or {}).get("level") or "UNKNOWN").upper()


def _presence(snap: dict[str, Any]) -> Optional[float]:
    t = snap.get("timbre") or {}
    p = t.get("presence")
    try:
        return float(p) if p is not None else None
    except (TypeError, ValueError):
        return None


def _brightness(snap: dict[str, Any]) -> Optional[float]:
    t = snap.get("timbre") or {}
    b = t.get("brightness")
    try:
        return float(b) if b is not None else None
    except (TypeError, ValueError):
        return None


def _airiness(snap: dict[str, Any]) -> Optional[float]:
    t = snap.get("timbre") or {}
    a = t.get("airiness")
    try:
        return float(a) if a is not None else None
    except (TypeError, ValueError):
        return None


def _stability(snap: dict[str, Any]) -> Optional[bool]:
    st = str((snap.get("stability") or {}).get("status") or "").upper()
    if not st or st == "UNKNOWN":
        return None
    if st in ("STABLE", "LOW", "NORMAL", "OK_PROXY"):
        return True
    if st in ("UNSTABLE", "HIGH", "IRREGULAR"):
        return False
    return None


def _presence_bucket(p: Optional[float]) -> str:
    if p is None:
        return "UNAVAILABLE"
    if p <= 0.42:
        return "LOW"
    if p >= 0.58:
        return "HIGH"
    return "MID"


def _brightness_bucket(b: Optional[float]) -> str:
    if b is None:
        return "UNAVAILABLE"
    if b <= 0.42:
        return "LOW"
    if b >= 0.58:
        return "HIGH"
    return "MID"


def _scope_label(scope: str) -> str:
    if scope == SCOPE_CONTROLLED:
        return "추가 발성 과제에서는"
    if scope == SCOPE_BOTH:
        return "노래와 추가 발성 과제에서 모두"
    return "이번 노래에서는"


def _evidence_item(axis: str, status: str, *, used_for: str, scope: str = SCOPE_SONG) -> dict[str, Any]:
    return {
        "axis": axis,
        "status": status,
        "scope": scope,
        "confidence": "medium",
        "used_for": used_for,
    }


def _fallback_interpretation(category: str, concern_id: str) -> tuple[str, str]:
    """Category-specific GUIDED_EXPERIMENT lead — never lead with 'unknown cause' meta."""
    from audio_analyzer.diagnostic.general_guidance import comparison_protocol_for

    proto = comparison_protocol_for(concern_id)
    lead = str(proto.get("lead") or "").strip()
    if category == "high_note":
        return (
            FACTOR_REGISTER,
            lead
            or (
                "높은 음에 닿으려면 세게 밀기보다, "
                "편안한 중음에서 작은 강도로 연결하는 쪽을 먼저 비교해보세요."
            ),
        )
    if category == "effort":
        return (
            FACTOR_EFFORT,
            lead
            or "작은~중간 강도로 짧게 유지하며 음량을 고정하는 쪽을 먼저 비교해보세요.",
        )
    if category == "timbre":
        return (FACTOR_TIMBRE, lead or "같은 짧은 구절을 두 방식으로 비교해보세요.")
    if category == "control":
        return (
            FACTOR_STABILITY,
            lead
            or "짧은 구간에서 안정이 유지되는 쪽을 먼저 비교해보세요.",
        )
    return (FACTOR_MAINTAIN, lead or "같은 짧은 구절을 두 방식으로 비교해보세요.")


def _reason_safety(concern_id: str) -> dict[str, Any]:
    return {
        "concern_id": concern_id,
        "question_type": TYPE_SAFETY,
        "guidance_level": GUIDANCE_SAFETY,
        "primary_focus": FACTOR_SAFETY,
        "primary_explanation": {
            "factor": FACTOR_SAFETY,
            "claim": "통증·지속 불편은 음향만으로 원인을 단정하지 않아요.",
            "scope": SCOPE_USER,
        },
        "supporting_explanations": [],
        "less_likely_explanations": [],
        "uncertain_factors": [],
        "evidence_used": [_evidence_item("safety", "FLAGGED", used_for="primary_explanation", scope=SCOPE_USER)],
        "interpretation": (
            "통증이나 지속적인 불편감은 음향 분석만으로 원인을 판단할 수 없어요. "
            "지금은 강한 고음·큰 소리 반복보다 휴식이 우선이에요."
        ),
        "confidence_label": "high",
        "causal_certainty": "SAFETY_GATE",
        "practice_required": True,
        "scope_note": None,
    }


def _reason_descriptive_timbre(
    concern_id: str,
    snap: dict[str, Any],
    scope: str,
    *,
    timbre_goal: Any = None,
) -> dict[str, Any]:
    """TIMBRE_DISSATISFIED — multi-axis profile, usually no corrective practice."""
    from audio_analyzer.diagnostic.general_guidance import timbre_goal_support_line

    breath = _breath(snap)
    contact = _contact(snap)
    effort = _effort(snap)
    stab = _stability(snap)
    chest = _chest_tendency(snap)
    pb = _presence_bucket(_presence(snap))
    bb = _brightness_bucket(_brightness(snap))
    sentences: list[str] = []
    evidence: list[dict[str, Any]] = []
    supporting: list[dict[str, Any]] = []

    if effort in ("LOW", "HIGH", "MODERATE"):
        e_label = {"LOW": "낮은 편이에요", "HIGH": "큰 편이에요", "MODERATE": "중간 정도예요"}[effort]
        sentences.append(f"힘 사용이 {e_label}")
        evidence.append(_evidence_item("effort", effort, used_for="primary_explanation", scope=scope))
    if breath in ("LOW", "HIGH", "MODERATE"):
        b_label = {"LOW": "적어요", "HIGH": "많은 편이에요", "MODERATE": "중간 정도예요"}[breath]
        sentences.append(f"숨 섞임이 {b_label}")
        evidence.append(_evidence_item("breathiness", breath, used_for="primary_explanation", scope=scope))
    if contact in ("MID", "FIRM", "LIGHT"):
        c_label = {"MID": "중간 정도예요", "FIRM": "다소 단단한 편이에요", "LIGHT": "가벼운 편이에요"}[contact]
        sentences.append(f"접촉 특성은 {c_label}")
        evidence.append(_evidence_item("contact", contact, used_for="supporting", scope=scope))
        supporting.append({"factor": FACTOR_CONTACT, "claim": f"접촉감 {contact}", "scope": scope})
    if chest == "CHEST" and len(sentences) < 4:
        sentences.append("흉성 쪽 음향 성향도 비교적 분명하게 나타납니다")
        evidence.append(_evidence_item("head_chest", "CHEST", used_for="supporting", scope=scope))
    elif chest == "HEAD" and len(sentences) < 4:
        sentences.append("두성 쪽 음향 성향이 비교적 분명하게 나타납니다")
        evidence.append(_evidence_item("head_chest", "HEAD", used_for="supporting", scope=scope))
    if stab is True and len(sentences) < 4:
        sentences.append("발성 안정성은 비교적 유지되는 편이에요")
        evidence.append(_evidence_item("stability", "STABLE", used_for="supporting", scope=scope))
    elif stab is False and len(sentences) < 4:
        sentences.append("발성 안정성이 떨어지는 구간이 있어요")
        evidence.append(_evidence_item("stability", "UNSTABLE", used_for="supporting", scope=scope))
    if pb == "LOW" and len(sentences) < 4:
        sentences.append("중역 존재감은 낮은 편이에요")
        evidence.append(_evidence_item("presence", "LOW", used_for="supporting", scope=scope))
        supporting.append({"factor": FACTOR_PRESENCE, "claim": "중역 존재감이 낮은 편", "scope": scope})
    elif pb == "HIGH" and len(sentences) < 4:
        sentences.append("중역 존재감은 다소 높은 편이에요")
        evidence.append(_evidence_item("presence", "HIGH", used_for="supporting", scope=scope))
    if bb == "LOW" and len(sentences) < 4:
        sentences.append("밝기는 어두운 쪽에 가까운 편이에요")
        evidence.append(_evidence_item("brightness", "LOW", used_for="supporting", scope=scope))
    elif bb == "HIGH" and len(sentences) < 4:
        sentences.append("밝기는 밝은 쪽에 가까운 편이에요")
        evidence.append(_evidence_item("brightness", "HIGH", used_for="supporting", scope=scope))
    # brightness UNAVAILABLE: omit from generation — do not mention missing brightness

    lead = _scope_label(scope)
    if sentences:
        body = ". ".join(sentences[:4])
        if not body.endswith("."):
            body = body + "."
        interpretation = f"{lead} 음색이 이런 특징과 관련되어 보여요. {body}"
        goal_line = timbre_goal_support_line(timbre_goal, snap)
        if goal_line:
            interpretation = f"{interpretation} {goal_line}"
        guidance = GUIDANCE_SONG_COMPOSITE if len(evidence) >= 2 else GUIDANCE_SONG_DIRECT
        primary = {"factor": FACTOR_TIMBRE, "claim": body, "scope": scope}
    else:
        from audio_analyzer.diagnostic.general_guidance import comparison_protocol_for

        proto = comparison_protocol_for(concern_id)
        interpretation = str(proto.get("lead") or "같은 짧은 구절을 두 방식으로 비교해보세요.")
        goal_line = timbre_goal_support_line(timbre_goal, snap)
        if goal_line:
            interpretation = f"{interpretation} {goal_line}"
        guidance = GUIDANCE_SAFE_GENERAL
        primary = {"factor": FACTOR_TIMBRE, "claim": "guided experiment", "scope": scope}

    return {
        "concern_id": concern_id,
        "question_type": TYPE_DESCRIPTIVE,
        "guidance_level": guidance,
        "primary_focus": FACTOR_TIMBRE,
        "primary_explanation": primary,
        "supporting_explanations": supporting[:2],
        "less_likely_explanations": [],
        "uncertain_factors": [],
        "evidence_used": evidence,
        "interpretation": interpretation,
        "confidence_label": "medium" if evidence else "low",
        "causal_certainty": "DESCRIPTIVE",
        "practice_required": False,
        "scope_note": None,
    }


def _reason_thin(concern_id: str, snap: dict[str, Any], scope: str) -> dict[str, Any]:
    breath = _breath(snap)
    contact = _contact(snap)
    pb = _presence_bucket(_presence(snap))
    register = _reg(snap)
    lead = _scope_label(scope)
    less: list[dict[str, Any]] = []
    supporting: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []

    # Contra: low breathiness makes leakage explanation less likely
    if breath == "LOW":
        less.append(
            {
                "factor": FACTOR_BREATHINESS,
                "claim": "숨이 많이 새서 얇게 들리는 유형은 강하게 보이지 않았어요.",
                "scope": scope,
            }
        )
        evidence.append(_evidence_item("breathiness", "LOW", used_for="less_likely", scope=scope))

    if breath == "HIGH" and pb != "LOW":
        interpretation = (
            f"{lead} 숨 섞임이 큰 편이라 얇은 인상과 관련될 가능성이 있어 보여요."
        )
        if contact == "LIGHT":
            interpretation += " 가벼운 접촉 특성도 함께 나타나요."
            supporting.append({"factor": FACTOR_CONTACT, "claim": "가벼운 접촉", "scope": scope})
        primary_focus = FACTOR_BREATHINESS
        primary = {
            "factor": FACTOR_BREATHINESS,
            "claim": "숨 섞임이 큰 편",
            "scope": scope,
        }
        evidence.append(_evidence_item("breathiness", "HIGH", used_for="primary_explanation", scope=scope))
        guidance = GUIDANCE_SONG_COMPOSITE if supporting else GUIDANCE_SONG_DIRECT
    elif pb == "LOW":
        interpretation = (
            (less[0]["claim"] + " " if less else "")
            + f"{lead} 중역 존재감이 낮은 편이라 소리의 중심이 덜 또렷하게 느껴지면서 "
            "얇다는 인상을 줄 가능성이 있어 보여요."
        )
        primary_focus = FACTOR_PRESENCE
        primary = {
            "factor": FACTOR_PRESENCE,
            "claim": "중역 존재감이 낮은 편",
            "scope": scope,
        }
        evidence.append(_evidence_item("presence", "LOW", used_for="primary_explanation", scope=scope))
        if register in ("PARTIAL", "DISRUPTED"):
            interpretation += (
                " 음역이 올라가는 구간에서 연결이 일부 달라지는 점도 "
                "특정 고음에서 갑자기 가벼워진 것처럼 느껴지는 데 영향을 줄 수 있어요."
            )
            supporting.append(
                {
                    "factor": FACTOR_REGISTER,
                    "claim": f"register {register}",
                    "scope": scope,
                }
            )
            evidence.append(_evidence_item("register", register, used_for="supporting", scope=scope))
        if contact == "LIGHT":
            supporting.append({"factor": FACTOR_CONTACT, "claim": "가벼운 접촉", "scope": scope})
        guidance = GUIDANCE_SONG_COMPOSITE if (less or supporting) else GUIDANCE_SONG_DIRECT
    elif register in ("PARTIAL", "DISRUPTED") and breath != "HIGH":
        contra = ""
        if less:
            contra = "숨이 많이 새는 패턴은 두드러지지 않아, 숨을 더 막는 방향은 우선이 아니에요. "
        interpretation = (
            contra
            + f"{lead} 음역이 올라가는 구간의 연결이 "
            + ("급격히 달라지거나 " if register == "DISRUPTED" else "일부만 안정적으로 이어져 ")
            + "특정 구간에서 소리가 가볍게 느껴질 수 있어요. "
            "지금은 음역이 변할 때도 소리 중심이 유지되는 방식을 먼저 찾아보는 게 좋아요."
        )
        primary_focus = FACTOR_REGISTER
        primary = {"factor": FACTOR_REGISTER, "claim": f"register {register}", "scope": scope}
        evidence.append(_evidence_item("register", register, used_for="primary_explanation", scope=scope))
        guidance = GUIDANCE_SONG_DIRECT
    elif contact == "LIGHT":
        interpretation = (
            f"{lead} 가벼운 접촉 특성이 보여, 얇은 인상과 관련될 가능성이 있어 보여요."
        )
        primary_focus = FACTOR_CONTACT
        primary = {"factor": FACTOR_CONTACT, "claim": "가벼운 접촉", "scope": scope}
        evidence.append(_evidence_item("contact", "LIGHT", used_for="primary_explanation", scope=scope))
        guidance = GUIDANCE_SONG_DIRECT
    else:
        from audio_analyzer.diagnostic.general_guidance import comparison_protocol_for

        if less:
            interpretation = (
                "숨이 많이 새는 패턴은 두드러지지 않아, 숨을 더 막는 방향은 우선이 아니에요. "
                + str(comparison_protocol_for(concern_id).get("lead") or "")
            ).strip()
        else:
            interpretation = str(
                comparison_protocol_for(concern_id).get("lead")
                or "얇게 느껴지는 구간에서 소리 중심이 유지되는 방식을 찾는 게 좋아요."
            )
        primary_focus = FACTOR_MAINTAIN
        primary = {"factor": FACTOR_MAINTAIN, "claim": "guided experiment", "scope": scope}
        guidance = GUIDANCE_SAFE_GENERAL

    return {
        "concern_id": concern_id,
        "question_type": TYPE_PERCEPTUAL,
        "guidance_level": guidance,
        "primary_focus": primary_focus,
        "primary_explanation": primary,
        "supporting_explanations": supporting[:2],
        "less_likely_explanations": less[:2],
        "uncertain_factors": [],
        "evidence_used": evidence,
        "interpretation": interpretation,
        "confidence_label": "medium",
        "causal_certainty": "FUNCTIONAL_HYPOTHESIS",
        "practice_required": True,
        "scope_note": None,
    }


def _reason_muffled(concern_id: str, snap: dict[str, Any], scope: str) -> dict[str, Any]:
    bb = _brightness_bucket(_brightness(snap))
    pb = _presence_bucket(_presence(snap))
    effort = _effort(snap)
    breath = _breath(snap)
    register = _reg(snap)
    lead = _scope_label(scope)
    less: list[dict[str, Any]] = []
    supporting: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []

    def _contra_priority() -> str:
        bits: list[str] = []
        if effort == "LOW":
            less.append(
                {"factor": FACTOR_EFFORT, "claim": "힘 사용이 높은 패턴은 두드러지지 않음", "scope": scope}
            )
            evidence.append(_evidence_item("effort", "LOW", used_for="less_likely", scope=scope))
        if breath == "LOW":
            less.append(
                {
                    "factor": FACTOR_BREATHINESS,
                    "claim": "숨이 많이 섞이는 패턴은 두드러지지 않음",
                    "scope": scope,
                }
            )
            evidence.append(_evidence_item("breathiness", "LOW", used_for="less_likely", scope=scope))
        if effort == "LOW" and breath == "LOW":
            bits.append(
                "힘 사용이 높거나 숨이 많이 섞이는 패턴은 두드러지지 않았어요. "
                "따라서 더 세게 부르거나 숨을 더 막는 방향은 현재 우선순위가 낮습니다."
            )
        elif effort == "LOW":
            bits.append(
                "힘 사용이 높은 패턴은 두드러지지 않았어요. "
                "따라서 더 세게 부르는 방향은 현재 우선순위가 낮습니다."
            )
        elif breath == "LOW":
            bits.append(
                "숨이 많이 섞이는 패턴은 두드러지지 않았어요. "
                "따라서 숨을 더 막는 방향은 현재 우선순위가 낮습니다."
            )
        return " ".join(bits)

    if bb == "LOW":
        interpretation = (
            f"{lead} 밝기가 어두운 쪽에 가까운 편이라 "
            "소리가 답답하게 느껴지는 데 관련될 가능성이 있어 보여요."
        )
        primary_focus = FACTOR_BRIGHTNESS
        primary = {"factor": FACTOR_BRIGHTNESS, "claim": "밝기 낮음", "scope": scope}
        evidence.append(_evidence_item("brightness", "LOW", used_for="primary_explanation", scope=scope))
        if pb == "LOW":
            interpretation += " 중역 존재감도 낮은 편이라 또렷함이 더 줄어들 수 있어요."
            supporting.append({"factor": FACTOR_PRESENCE, "claim": "존재감 낮음", "scope": scope})
            evidence.append(_evidence_item("presence", "LOW", used_for="supporting", scope=scope))
        guidance = GUIDANCE_SONG_COMPOSITE if supporting else GUIDANCE_SONG_DIRECT
    elif pb == "LOW":
        contra = _contra_priority()
        interpretation = (
            f"{lead} "
            + (contra + " " if contra else "")
            + "중역 존재감이 낮은 편이라 소리가 덜 또렷하고 답답하게 느껴지는 데 "
            "일부 관련될 수 있어 보여요."
        )
        primary_focus = FACTOR_PRESENCE
        primary = {"factor": FACTOR_PRESENCE, "claim": "중역 존재감 낮음", "scope": scope}
        evidence.append(_evidence_item("presence", "LOW", used_for="primary_explanation", scope=scope))
        if register in ("DISRUPTED", "PARTIAL"):
            interpretation += (
                " 음역이 바뀔 때 발성 특성이 달라지는 구간이 있다면, "
                "그 연결을 더 일정하게 만들며 답답하게 느껴지는 구간의 변화가 줄어드는지 "
                "함께 확인해보는 것이 좋아요."
            )
            supporting.append({"factor": FACTOR_REGISTER, "claim": f"register {register}", "scope": scope})
            evidence.append(_evidence_item("register", register, used_for="supporting", scope=scope))
        guidance = GUIDANCE_SONG_COMPOSITE if (less or supporting) else GUIDANCE_SONG_DIRECT
    else:
        # brightness unavailable or not low — use other available evidence; never center missing brightness
        contra = _contra_priority()
        if register in ("DISRUPTED", "PARTIAL"):
            interpretation = (
                (f"{lead} {contra} " if contra else f"{lead} ")
                + "반면 음역이 바뀔 때 발성 특성이 급격하게 달라지는 구간이 있다면, "
                "먼저 그 연결을 더 일정하게 만들면서 답답하게 느껴지는 구간의 변화가 "
                "줄어드는지 확인해보는 것이 좋아요."
            )
            primary_focus = FACTOR_REGISTER
            primary = {"factor": FACTOR_REGISTER, "claim": f"register {register}", "scope": scope}
            evidence.append(_evidence_item("register", register, used_for="primary_explanation", scope=scope))
            guidance = GUIDANCE_SONG_COMPOSITE if less else GUIDANCE_SONG_DIRECT
        elif effort in ("HIGH", "MODERATE"):
            interpretation = (
                f"{lead} 힘 사용이 커지는 구간이 보여요. "
                "답답하게 느껴지는 구절을 작은 강도에서 비교하며 "
                "힘을 더하지 않는 쪽이 편한지 확인해보는 것이 좋아요."
            )
            primary_focus = FACTOR_EFFORT
            primary = {"factor": FACTOR_EFFORT, "claim": f"effort {effort}", "scope": scope}
            evidence.append(_evidence_item("effort", effort, used_for="primary_explanation", scope=scope))
            guidance = GUIDANCE_SONG_DIRECT
        else:
            from audio_analyzer.diagnostic.general_guidance import comparison_protocol_for

            interpretation = (
                (f"{lead} {contra} " if contra else f"{lead} ")
                + str(
                    comparison_protocol_for(concern_id).get("lead")
                    or "같은 짧은 구절을 두 방식으로 비교해보세요."
                )
            ).strip()
            primary_focus = FACTOR_PRESENCE
            primary = {"factor": FACTOR_PRESENCE, "claim": "비교 탐색", "scope": scope}
            guidance = GUIDANCE_SAFE_GENERAL if not evidence else GUIDANCE_SONG_DIRECT

    return {
        "concern_id": concern_id,
        "question_type": TYPE_PERCEPTUAL,
        "guidance_level": guidance,
        "primary_focus": primary_focus,
        "primary_explanation": primary,
        "supporting_explanations": supporting[:2],
        "less_likely_explanations": less,
        "uncertain_factors": [],
        "evidence_used": evidence,
        "interpretation": interpretation,
        "confidence_label": "medium" if evidence else "low",
        "causal_certainty": "FUNCTIONAL_HYPOTHESIS",
        "practice_required": True,
        "scope_note": None,
    }


def _reason_breathy(concern_id: str, snap: dict[str, Any], scope: str) -> dict[str, Any]:
    breath = _breath(snap)
    contact = _contact(snap)
    lead = _scope_label(scope)
    if breath == "HIGH":
        interpretation = f"{lead} 숨 섞임이 큰 편이라 느끼신 숨 섞임과 관련될 가능성이 있어 보여요."
        focus = FACTOR_BREATHINESS
        guidance = GUIDANCE_SONG_DIRECT
        primary = {"factor": focus, "claim": "숨 섞임 HIGH", "scope": scope}
        evidence = [_evidence_item("breathiness", "HIGH", used_for="primary_explanation", scope=scope)]
        less: list = []
    elif breath == "LOW":
        interpretation = (
            f"{lead} 숨 섞임이 큰 유형은 강하게 보이지 않았어요. "
            "따라서 숨이 많이 새는 느낌보다는 다른 요소(구간·모음·음량)를 "
            "먼저 확인하는 편이 적절해 보여요."
        )
        focus = FACTOR_MAINTAIN
        guidance = GUIDANCE_SAFE_GENERAL
        primary = {"factor": focus, "claim": "breathiness LOW contra", "scope": scope}
        evidence = [_evidence_item("breathiness", "LOW", used_for="less_likely", scope=scope)]
        less = [{"factor": FACTOR_BREATHINESS, "claim": "숨 섞임 HIGH 설명은 덜 유력", "scope": scope}]
    else:
        if contact == "LIGHT":
            interpretation = f"{lead} 가벼운 접촉 특성이 보여 숨 섞인 인상과 관련될 수 있어 보여요."
            focus = FACTOR_CONTACT
            guidance = GUIDANCE_SONG_DIRECT
            primary = {"factor": focus, "claim": "가벼운 접촉", "scope": scope}
            evidence = [_evidence_item("contact", "LIGHT", used_for="primary_explanation", scope=scope)]
            less = []
        else:
            focus, interpretation = _fallback_interpretation("timbre", concern_id)
            guidance = GUIDANCE_SAFE_GENERAL
            primary = {"factor": focus, "claim": "uncertain", "scope": scope}
            evidence = []
            less = []
    return {
        "concern_id": concern_id,
        "question_type": TYPE_PERCEPTUAL,
        "guidance_level": guidance,
        "primary_focus": focus,
        "primary_explanation": primary,
        "supporting_explanations": [],
        "less_likely_explanations": less,
        "uncertain_factors": [],
        "evidence_used": evidence,
        "interpretation": interpretation,
        "confidence_label": "medium",
        "causal_certainty": "FUNCTIONAL_HYPOTHESIS",
        "practice_required": True,
        "scope_note": None,
    }


def _reason_sharp(concern_id: str, snap: dict[str, Any], scope: str) -> dict[str, Any]:
    bb = _brightness_bucket(_brightness(snap))
    pb = _presence_bucket(_presence(snap))
    effort = _effort(snap)
    register = _reg(snap)
    lead = _scope_label(scope)
    if bb == "HIGH":
        interpretation = f"{lead} 밝기가 밝은 쪽에 가까운 편이라 날카로운 인상과 관련될 가능성이 있어 보여요."
        focus = FACTOR_BRIGHTNESS
        guidance = GUIDANCE_SONG_DIRECT
        evidence = [_evidence_item("brightness", "HIGH", used_for="primary_explanation", scope=scope)]
        uncertain: list[str] = []
    elif pb == "HIGH":
        interpretation = (
            f"{lead} 중역 존재감이 다소 높은 편이라 또렷·날카로운 인상에 "
            "영향을 줄 수 있어 보여요."
        )
        focus = FACTOR_PRESENCE
        guidance = GUIDANCE_SONG_DIRECT
        evidence = [_evidence_item("presence", "HIGH", used_for="primary_explanation", scope=scope)]
        uncertain = []
    elif bb == "LOW":
        interpretation = (
            f"{lead} 밝기가 어두운 쪽에 가까워 날카로움의 주된 설명으로는 보이지 않아요. "
            "같은 구절을 작은 강도에서 짧게 비교하며 특정 모음에서만 날카롭게 느껴지는지 "
            "확인해보는 것이 좋아요."
        )
        focus = FACTOR_MAINTAIN
        guidance = GUIDANCE_SAFE_GENERAL
        evidence = [_evidence_item("brightness", "LOW", used_for="less_likely", scope=scope)]
        uncertain = []
    elif register in ("DISRUPTED", "PARTIAL"):
        interpretation = (
            f"{lead} 음역이 바뀔 때 발성 특성이 달라지는 구간이 보여요. "
            "날카롭게 느껴지는 지점을 세게 밀기보다, 작은 강도로 연결을 다듬으며 "
            "그 인상이 줄어드는지 비교해보세요."
        )
        focus = FACTOR_REGISTER
        guidance = GUIDANCE_SONG_DIRECT
        evidence = [_evidence_item("register", register, used_for="primary_explanation", scope=scope)]
        uncertain = []
    elif effort in ("HIGH", "MODERATE"):
        interpretation = (
            f"{lead} 힘 사용이 커지는 구간이 보여요. "
            "날카롭게 느껴지는 구절을 작은 강도에서 비교해보는 것이 좋아요."
        )
        focus = FACTOR_EFFORT
        guidance = GUIDANCE_SONG_DIRECT
        evidence = [_evidence_item("effort", effort, used_for="primary_explanation", scope=scope)]
        uncertain = []
    else:
        focus, interpretation = _fallback_interpretation("timbre", concern_id)
        guidance = GUIDANCE_SAFE_GENERAL
        evidence = []
        uncertain = []
    return {
        "concern_id": concern_id,
        "question_type": TYPE_PERCEPTUAL,
        "guidance_level": guidance,
        "primary_focus": focus,
        "primary_explanation": {"factor": focus, "claim": interpretation[:40], "scope": scope},
        "supporting_explanations": [],
        "less_likely_explanations": [],
        "uncertain_factors": uncertain,
        "evidence_used": evidence,
        "interpretation": interpretation,
        "confidence_label": "medium",
        "causal_certainty": "FUNCTIONAL_HYPOTHESIS",
        "practice_required": True,
        "scope_note": None,
    }


def _reason_effortful_high(
    concern_id: str, snap: dict[str, Any], scope: str, skipped: set[str]
) -> dict[str, Any]:
    """HIGH_NOTE_TOO_EFFORTFUL — primary follows evidence, not concern label."""
    effort = _effort(snap)
    contact = _contact(snap)
    register = _reg(snap)
    lead = _scope_label(scope)
    scope_note = None
    if "high_note_sustain_a" in skipped:
        scope_note = "추가 고음 과제를 진행하지 않아 이 해석은 현재 노래 기준입니다."

    if effort in ("HIGH", "MODERATE"):
        interpretation = (
            f"{lead} 힘 사용이 큰 구간이 나타나"
            + ("고, 단단한 접촉 특성도 함께 보여요. " if contact == "FIRM" else "요. ")
            + "높은 음을 낼 때 소리를 더 강하게 유지하는 방식이 부담을 키우는 쪽으로 보입니다."
        )
        focus = FACTOR_EFFORT
        supporting = (
            [{"factor": FACTOR_CONTACT, "claim": "단단한 접촉", "scope": scope}]
            if contact == "FIRM"
            else []
        )
        evidence = [_evidence_item("effort", effort, used_for="primary_explanation", scope=scope)]
        if contact == "FIRM":
            evidence.append(_evidence_item("contact", "FIRM", used_for="supporting", scope=scope))
        guidance = GUIDANCE_SONG_COMPOSITE if supporting else GUIDANCE_SONG_DIRECT
        less: list = []
    elif register in ("DISRUPTED", "PARTIAL") and effort == "LOW":
        interpretation = (
            f"{lead} 과도한 힘 증가가 주된 제한으로 강하게 보이지는 않았어요. "
            "대신 음역이 올라갈 때 연결이 "
            + ("급격히 달라지거나 " if register == "DISRUPTED" else "일부만 이어져 ")
            + "고음이 더 힘들게 느껴질 수 있어 보여요. "
            "힘을 빼는 것만 반복하기보다 작은 강도로 연결이 유지되는지부터 확인하는 방향이 더 적합해 보여요."
        )
        focus = FACTOR_REGISTER
        supporting = []
        evidence = [
            _evidence_item("effort", "LOW", used_for="less_likely", scope=scope),
            _evidence_item("register", register, used_for="primary_explanation", scope=scope),
        ]
        less = [{"factor": FACTOR_EFFORT, "claim": "과도한 힘 증가 약함", "scope": scope}]
        guidance = GUIDANCE_SONG_COMPOSITE
    elif effort == "LOW" and register == "CONNECTED":
        interpretation = (
            f"{lead} 과도한 힘이나 큰 연결 단절이 주된 제한으로 강하게 보이지는 않았어요. "
            "그래서 세게 힘을 빼는 것보다 현재 편안한 패턴을 유지하며 "
            "범위를 천천히 넓히는 것이 좋아요."
        )
        focus = FACTOR_MAINTAIN
        supporting = []
        evidence = [
            _evidence_item("effort", "LOW", used_for="contra", scope=scope),
            _evidence_item("register", "CONNECTED", used_for="contra", scope=scope),
        ]
        less = [{"factor": FACTOR_EFFORT, "claim": "effort HIGH 설명 덜 유력", "scope": scope}]
        guidance = GUIDANCE_SAFE_GENERAL
    else:
        focus, interpretation = _fallback_interpretation("high_note", concern_id)
        supporting = []
        evidence = []
        less = []
        guidance = GUIDANCE_SAFE_GENERAL

    return {
        "concern_id": concern_id,
        "question_type": TYPE_FUNCTIONAL,
        "guidance_level": guidance,
        "primary_focus": focus,
        "primary_explanation": {"factor": focus, "claim": interpretation[:60], "scope": scope},
        "supporting_explanations": supporting[:2],
        "less_likely_explanations": less,
        "uncertain_factors": [],
        "evidence_used": evidence,
        "interpretation": interpretation,
        "confidence_label": "medium",
        "causal_certainty": "FUNCTIONAL_HYPOTHESIS",
        "practice_required": True,
        "scope_note": scope_note,
    }


def _reason_timbre_changes_high(concern_id: str, snap: dict[str, Any], scope: str) -> dict[str, Any]:
    """TIMBRE_CHANGES_HIGH — use register when available; never claim a direct high-note compare if absent."""
    register = _reg(snap)
    effort = _effort(snap)
    lead = _scope_label(scope)
    hn = _high_note_available(snap)
    process = "음역이 올라가는 과정에서" if not hn else "음역이 올라갈 때"

    if register == "DISRUPTED":
        interpretation = (
            f"{lead} {process} 발성 특성이 급격하게 달라지는 구간이 관찰됐어요. "
            "그래서 고음에서 음색이 갑자기 달라지는 느낌을 줄이려면, "
            "높은 음을 더 세게 만드는 것보다 전환 구간을 더 일정하게 연결하는 것을 먼저 해보는 게 좋아요."
        )
        focus = FACTOR_REGISTER
        guidance = GUIDANCE_SONG_DIRECT
        evidence = [_evidence_item("register", "DISRUPTED", used_for="primary_explanation", scope=scope)]
    elif register == "PARTIAL":
        interpretation = (
            f"{lead} 음역이 올라갈 때 연결이 일부 구간에서만 안정적으로 이어졌어요. "
            "그래서 고음에서 음색이 갑자기 달라지는 느낌을 줄이려면, "
            "높은 음을 더 세게 만드는 것보다 전환 구간을 더 일정하게 연결하는 것을 먼저 해보는 게 좋아요."
        )
        focus = FACTOR_REGISTER
        guidance = GUIDANCE_SONG_DIRECT
        evidence = [_evidence_item("register", "PARTIAL", used_for="primary_explanation", scope=scope)]
    elif effort in ("HIGH", "MODERATE"):
        interpretation = (
            f"{lead} {process} 힘 사용이 커지는 구간이 보여요. "
            "고음을 더 세게 내기보다 편안한 강도에서 연결을 유지하는 쪽을 먼저 비교해보세요."
        )
        focus = FACTOR_EFFORT
        guidance = GUIDANCE_SONG_DIRECT
        evidence = [_evidence_item("effort", effort, used_for="primary_explanation", scope=scope)]
    else:
        from audio_analyzer.diagnostic.general_guidance import comparison_protocol_for

        interpretation = str(
            comparison_protocol_for(concern_id).get("lead")
            or (
                "고음에서 음색이 갑자기 달라지는 느낌을 줄이려면, "
                "높은 음을 더 세게 만드는 것보다 전환 구간을 더 일정하게 연결하는 것을 먼저 해보는 게 좋아요."
            )
        )
        focus = FACTOR_REGISTER
        guidance = GUIDANCE_SAFE_GENERAL
        evidence = []

    return {
        "concern_id": concern_id,
        "question_type": TYPE_PERCEPTUAL,
        "guidance_level": guidance,
        "primary_focus": focus,
        "primary_explanation": {"factor": focus, "claim": interpretation[:60], "scope": scope},
        "supporting_explanations": [],
        "less_likely_explanations": [],
        "uncertain_factors": [],
        "evidence_used": evidence,
        "interpretation": interpretation,
        "confidence_label": "medium" if evidence else "low",
        "causal_certainty": "FUNCTIONAL_HYPOTHESIS",
        "practice_required": True,
        "scope_note": None,
    }


def _reason_controlish(concern_id: str, snap: dict[str, Any], scope: str, sem: dict[str, Any]) -> dict[str, Any]:
    """Walk candidate_factors in semantic order — question meaning sets priority."""
    register = _reg(snap)
    stab = _stability(snap)
    effort = _effort(snap)
    lead = _scope_label(scope)
    category = str(sem.get("category") or "control")
    factors = list(sem.get("candidate_factors") or [])

    focus = None
    interpretation = ""
    guidance = GUIDANCE_SAFE_GENERAL
    evidence: list[dict[str, Any]] = []

    for factor in factors:
        if factor == FACTOR_STABILITY and stab is False:
            interpretation = (
                f"{lead} 안정성이 떨어지는 구간이 보여, "
                "흔들림·불안정감과 관련될 가능성이 있어 보여요."
            )
            focus = FACTOR_STABILITY
            guidance = GUIDANCE_SONG_DIRECT
            evidence = [_evidence_item("stability", "UNSTABLE", used_for="primary_explanation", scope=scope)]
            break
        if factor == FACTOR_REGISTER and register in ("DISRUPTED", "PARTIAL"):
            interpretation = (
                f"{lead} 음역이 올라가는 구간의 연결이 "
                + ("급격히 달라지는 " if register == "DISRUPTED" else "일부만 안정적으로 이어지는 ")
                + "패턴이 보여요."
            )
            focus = FACTOR_REGISTER
            guidance = GUIDANCE_SONG_DIRECT
            evidence = [_evidence_item("register", register, used_for="primary_explanation", scope=scope)]
            break
        if factor == FACTOR_EFFORT and effort in ("HIGH", "MODERATE"):
            interpretation = f"{lead} 힘 사용이 큰 구간이 함께 보여, 조절이 더 어렵게 느껴질 수 있어 보여요."
            focus = FACTOR_EFFORT
            guidance = GUIDANCE_SONG_DIRECT
            evidence = [_evidence_item("effort", effort, used_for="primary_explanation", scope=scope)]
            break
        if factor == FACTOR_DYNAMICS:
            focus = FACTOR_DYNAMICS
            interpretation = (
                f"{lead} 강약 조절은 긴 프레이즈보다 짧은 구간에서 작은 강도로 시작해 "
                "편안함이 유지되는 범위를 먼저 찾는 방식이 좋아요."
            )
            guidance = GUIDANCE_SAFE_GENERAL
            evidence = []
            break

    if focus is None:
        # Concern-specific defaults when no matching evidence
        if concern_id == "HIGH_NOTE_UNSTABLE":
            focus = FACTOR_STABILITY
            interpretation = (
                f"{lead} 고음에서 음정·소리가 흔들릴 때는 "
                "길게 버티기보다 짧은 안정 구간부터 비교하는 쪽이 좋아요."
            )
        elif concern_id == "PITCH_UNSTABLE":
            focus = FACTOR_STABILITY
            interpretation = f"{lead} 음정 흔들림은 짧은 안정 구간부터 비교하는 쪽이 좋아요."
        elif concern_id == "VIBRATO_UNSTABLE":
            focus = FACTOR_STABILITY
            interpretation = (
                f"{lead} 비브라토는 억지로 크게 만들기보다 "
                "짧은 지속음에서 자연스러운 흔들림이 생기는지 비교해보세요."
            )
        elif concern_id == "PHRASE_END_WEAK":
            focus = FACTOR_DYNAMICS
            interpretation = (
                f"{lead} 프레이즈 끝은 긴 문장을 세게 버티기보다 "
                "짧은 프레이즈부터 끝까지 같은 편안함을 유지해보세요."
            )
        elif concern_id == "DYNAMICS_DIFFICULT":
            focus = FACTOR_DYNAMICS
            interpretation = (
                f"{lead} 강약 조절은 편한 강도에서 작은 변화만 추가해 비교하는 쪽이 좋아요."
            )
        else:
            focus, interpretation = _fallback_interpretation(category, concern_id)
        guidance = GUIDANCE_SAFE_GENERAL
        evidence = []

    return {
        "concern_id": concern_id,
        "question_type": str(sem.get("type") or TYPE_CONTROL),
        "guidance_level": guidance,
        "primary_focus": focus,
        "primary_explanation": {"factor": focus, "claim": interpretation[:50], "scope": scope},
        "supporting_explanations": [],
        "less_likely_explanations": [],
        "uncertain_factors": [],
        "evidence_used": evidence,
        "interpretation": interpretation,
        "confidence_label": "medium" if evidence else "low",
        "causal_certainty": "FUNCTIONAL_HYPOTHESIS",
        "practice_required": bool(sem.get("practice_required", True)),
        "scope_note": None,
    }


def reason_about_concern(
    concern_id: str,
    *,
    song_profile: dict[str, Any],
    evaluation: Optional[dict[str, Any]] = None,
    user_skipped_tasks: Optional[set[str]] = None,
    has_valid_controlled: bool = False,
    timbre_goal: Any = None,
) -> dict[str, Any]:
    """Return structured reasoning for one selected concern_id."""
    snap = get_canonical_snapshot(song_profile)
    skipped = set(user_skipped_tasks or [])
    sem = semantics_for(concern_id)
    qtype = str(sem.get("type") or TYPE_OTHER)
    scope = SCOPE_BOTH if has_valid_controlled else SCOPE_SONG
    ev = evaluation or {}

    if qtype == TYPE_SAFETY or str(ev.get("status") or "").upper() == "SAFETY_ONLY":
        out = _reason_safety(concern_id)
    elif concern_id == "TIMBRE_DISSATISFIED":
        out = _reason_descriptive_timbre(concern_id, snap, scope, timbre_goal=timbre_goal)
    elif concern_id in ("VOICE_TOO_THIN", "HIGH_NOTE_THINS"):
        out = _reason_thin(concern_id, snap, scope)
    elif concern_id == "VOICE_TOO_DARK_MUFFLED":
        out = _reason_muffled(concern_id, snap, scope)
    elif concern_id == "VOICE_TOO_BREATHY":
        out = _reason_breathy(concern_id, snap, scope)
    elif concern_id == "VOICE_TOO_SHARP":
        out = _reason_sharp(concern_id, snap, scope)
    elif concern_id == "HIGH_NOTE_TOO_EFFORTFUL":
        out = _reason_effortful_high(concern_id, snap, scope, skipped)
    elif concern_id in (
        "PITCH_UNSTABLE",
        "REGISTER_CONNECTION_DIFFICULT",
        "VIBRATO_UNSTABLE",
        "DYNAMICS_DIFFICULT",
        "PHRASE_END_WEAK",
        "HIGH_NOTE_UNSTABLE",
    ):
        out = _reason_controlish(concern_id, snap, scope, sem)
    elif qtype in (TYPE_CONTROL, TYPE_FUNCTIONAL) and concern_id not in (
        "HIGH_NOTE_CANNOT_REACH",
        "HIGH_NOTE_FLIPS",
        "HIGH_NOTE_UNSTABLE",
        "THROAT_EFFORT",
        "LOUD_VOICE_DIFFICULT",
        "VOCAL_FATIGUE",
        "AFTER_SINGING_FATIGUE",
        "VOICE_ROUGH",
        "TIMBRE_CHANGES_HIGH",
        "VOICE_TOO_NASAL_PERCEPT",
    ):
        out = _reason_controlish(concern_id, snap, scope, sem)
    elif concern_id in ("VOICE_ROUGH", "TIMBRE_CHANGES_HIGH", "VOICE_TOO_NASAL_PERCEPT"):
        # Perceptual with control/timbre mix
        if concern_id == "VOICE_ROUGH":
            stab = _stability(snap)
            lead = _scope_label(scope)
            if stab is False:
                interpretation = f"{lead} 안정성이 떨어지는 구간이 보여 거친 인상과 관련될 가능성이 있어 보여요."
                focus = FACTOR_STABILITY
                guidance = GUIDANCE_SONG_DIRECT
            else:
                interpretation = (
                    f"{lead} 짧은 구간에서 안정이 유지되는 범위를 먼저 만든 뒤 "
                    "조금씩 넓혀보는 쪽이 좋아요."
                )
                focus = FACTOR_STABILITY
                guidance = GUIDANCE_SAFE_GENERAL
            out = {
                "concern_id": concern_id,
                "question_type": TYPE_PERCEPTUAL,
                "guidance_level": guidance,
                "primary_focus": focus,
                "primary_explanation": {"factor": focus, "claim": interpretation[:40], "scope": scope},
                "supporting_explanations": [],
                "less_likely_explanations": [],
                "uncertain_factors": [],
                "evidence_used": (
                    [_evidence_item("stability", "UNSTABLE", used_for="primary_explanation", scope=scope)]
                    if stab is False
                    else []
                ),
                "interpretation": interpretation,
                "confidence_label": "medium",
                "causal_certainty": "FUNCTIONAL_HYPOTHESIS",
                "practice_required": True,
                "scope_note": None,
            }
        elif concern_id == "TIMBRE_CHANGES_HIGH":
            out = _reason_timbre_changes_high(concern_id, snap, scope)
        else:
            pb = _presence_bucket(_presence(snap))
            register = _reg(snap)
            if pb == "LOW":
                interpretation = (
                    f"{_scope_label(scope)} 중역 존재감이 낮은 편이라 콧소리처럼 들릴 수 있는 "
                    "인상과 일부 관련될 수 있어 보여요. "
                    "특정 모음에서만 나타나는지, 작은 강도로 짧게 비교해보세요."
                )
                focus = FACTOR_PRESENCE
                guidance = GUIDANCE_SONG_DIRECT
                evidence = [_evidence_item("presence", "LOW", used_for="primary_explanation", scope=scope)]
            elif register in ("DISRUPTED", "PARTIAL"):
                interpretation = (
                    f"{_scope_label(scope)} 음역이 바뀔 때 발성 특성이 달라지는 구간이 보여요. "
                    "콧소리처럼 느껴지는 구간에서는 소리를 더 세게 바꾸기보다, "
                    "같은 짧은 구절을 두 방식으로 비교해보세요."
                )
                focus = FACTOR_REGISTER
                guidance = GUIDANCE_SONG_DIRECT
                evidence = [_evidence_item("register", register, used_for="primary_explanation", scope=scope)]
            else:
                from audio_analyzer.diagnostic.general_guidance import comparison_protocol_for

                focus = FACTOR_TIMBRE
                interpretation = str(
                    comparison_protocol_for(concern_id).get("lead")
                    or (
                        "콧소리처럼 느껴지는 구간에서는 소리를 더 세게 바꾸기보다, "
                        "같은 짧은 구절을 두 방식으로 비교해보세요."
                    )
                )
                guidance = GUIDANCE_SAFE_GENERAL
                evidence = []
            out = {
                "concern_id": concern_id,
                "question_type": TYPE_PERCEPTUAL,
                "guidance_level": guidance,
                "primary_focus": focus,
                "primary_explanation": {"factor": focus, "claim": "nasal percept", "scope": scope},
                "supporting_explanations": [],
                "less_likely_explanations": [],
                "uncertain_factors": [],
                "evidence_used": evidence,
                "interpretation": interpretation,
                "confidence_label": "low",
                "causal_certainty": "GUIDANCE_ONLY",
                "practice_required": True,
                "scope_note": None,
            }
    else:
        # Defer high-note cannot/flips/effort-ish to existing functional_hypothesis paths
        # by returning a sentinel — caller may merge. For effort/fatigue generic:
        out = None  # type: ignore

    if out is None:
        # Generic functional using candidates
        if concern_id in ("THROAT_EFFORT", "LOUD_VOICE_DIFFICULT", "VOCAL_FATIGUE", "AFTER_SINGING_FATIGUE"):
            effort = _effort(snap)
            contact = _contact(snap)
            register = _reg(snap)
            lead = _scope_label(scope)
            if effort in ("HIGH", "MODERATE") and contact == "FIRM":
                interpretation = (
                    f"{lead} 힘 사용과 단단한 접촉 특성이 함께 나타나는 구간이 보여요. "
                    "작은 강도로 짧게 유지하며 음량을 고정하는 연습부터 시작하는 것이 좋아요."
                )
                focus = FACTOR_EFFORT
                guidance = GUIDANCE_SONG_COMPOSITE
            elif effort in ("HIGH", "MODERATE"):
                interpretation = f"{lead} 힘 사용이 큰 구간이 보여요."
                focus = FACTOR_EFFORT
                guidance = GUIDANCE_SONG_DIRECT
            elif register in ("DISRUPTED", "PARTIAL"):
                interpretation = (
                    f"{lead} 과도한 힘이 주된 제한으로 강하게 보이지는 않았어요. "
                    "대신 연결 구간 변화가 부담 느낌과 관련될 수 있어 보여요."
                )
                focus = FACTOR_REGISTER
                guidance = GUIDANCE_SONG_DIRECT
            else:
                focus, interpretation = _fallback_interpretation("effort", concern_id)
                guidance = GUIDANCE_SAFE_GENERAL
            out = {
                "concern_id": concern_id,
                "question_type": TYPE_FUNCTIONAL,
                "guidance_level": guidance,
                "primary_focus": focus,
                "primary_explanation": {"factor": focus, "claim": interpretation[:40], "scope": scope},
                "supporting_explanations": [],
                "less_likely_explanations": [],
                "uncertain_factors": [],
                "evidence_used": [],
                "interpretation": interpretation,
                "confidence_label": "medium",
                "causal_certainty": "FUNCTIONAL_HYPOTHESIS",
                "practice_required": True,
                "scope_note": None,
            }
        else:
            # Signal: use legacy high-note builders
            return {
                "concern_id": concern_id,
                "question_type": qtype,
                "defer_to_legacy": True,
                "practice_required": bool(sem.get("practice_required", True)),
                "fallback_focus": sem.get("fallback_focus") or FACTOR_MAINTAIN,
                "category": sem.get("category"),
            }

    # Attach practice by primary focus (never by Q index)
    practice_required = bool(out.get("practice_required", True))
    focus = str(out.get("primary_focus") or sem.get("fallback_focus") or FACTOR_MAINTAIN)
    if practice_required and out.get("guidance_level") != GUIDANCE_SAFETY:
        out["practice"] = practice_for_focus(focus, category=str(sem.get("category") or ""))
        out["practice_id"] = (out["practice"] or {}).get("practice_id")
    elif out.get("guidance_level") == GUIDANCE_SAFETY:
        out["practice"] = practice_for_focus(FACTOR_SAFETY)
        out["practice_id"] = "SAFETY_STOP"
    else:
        out["practice"] = None
        out["practice_id"] = None

    out["secondary_factors"] = [
        str(s.get("factor"))
        for s in (out.get("supporting_explanations") or [])
        if s.get("factor")
    ][:2]
    out["evidence"] = [
        f"{e.get('axis')}_{e.get('status')}" for e in (out.get("evidence_used") or [])
    ]
    out["contra_evidence"] = [
        str(x.get("factor")) for x in (out.get("less_likely_explanations") or [])
    ]
    return out
