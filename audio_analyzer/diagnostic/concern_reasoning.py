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
    if st in ("DISRUPTED", "UNSTABLE", "TRANSITION_EVENTS"):
        return "DISRUPTED"
    if st in ("PARTIAL", "INSUFFICIENT", "MIXED"):
        return "PARTIAL"
    if st in ("CONNECTED", "SMOOTH", "STABLE", "CONTINUOUS", "STABLE_LIKE"):
        return "CONNECTED"
    return "UNKNOWN"


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
    """Category-specific SAFE_GENERAL — never all register-glide."""
    if category == "high_note":
        return (
            FACTOR_REGISTER,
            "이번 노래만으로 고음 관련 원인을 하나로 좁히기는 어려워요. "
            "다만 음량을 먼저 키우지 않고, 편안한 중음에서 높은 음까지 "
            "작은 강도로 연결하는 연습부터 시작하는 것이 좋아요.",
        )
    if category == "effort":
        return (
            FACTOR_EFFORT,
            "이번 노래만으로 힘 관련 원인을 하나로 좁히기는 어려워요. "
            "다만 작은~중간 강도로 짧게 유지하며 음량을 고정하는 연습부터 "
            "시작하는 것이 좋아요.",
        )
    if category == "timbre":
        return (
            FACTOR_TIMBRE,
            "이번 노래만으로 음색 관련 원인을 하나로 좁히기는 어려워요. "
            "다만 편안한 강도에서 짧은 지속음을 유지하며 "
            "소리를 과하게 밀지 않는 관찰부터 시작하는 것이 좋아요.",
        )
    if category == "control":
        return (
            FACTOR_STABILITY,
            "이번 노래만으로 조절 관련 원인을 하나로 좁히기는 어려워요. "
            "다만 짧은 구간에서 안정이 유지되는 범위를 확인한 뒤 "
            "조금씩 넓히는 연습부터 시작하는 것이 좋아요.",
        )
    return (
        FACTOR_MAINTAIN,
        "이번 노래만으로 원인을 하나로 좁히기는 어려워요. "
        "다만 지금은 작은 강도로 짧게 유지하며 불편감 없이 "
        "현재 패턴을 확인하는 방향이 좋아요.",
    )


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


def _reason_descriptive_timbre(concern_id: str, snap: dict[str, Any], scope: str) -> dict[str, Any]:
    """TIMBRE_DISSATISFIED — multi-axis profile, usually no corrective practice."""
    breath = _breath(snap)
    contact = _contact(snap)
    pb = _presence_bucket(_presence(snap))
    bb = _brightness_bucket(_brightness(snap))
    air = _airiness(snap)
    feats = list(snap.get("key_features") or [])
    parts: list[str] = []
    evidence: list[dict[str, Any]] = []
    supporting: list[dict[str, Any]] = []
    uncertain: list[str] = []

    if breath in ("LOW", "HIGH", "MODERATE"):
        label = "적고" if breath == "LOW" else ("많은 편이고" if breath == "HIGH" else "중간 정도이고")
        parts.append(f"숨 섞임이 {label}")
        evidence.append(_evidence_item("breathiness", breath, used_for="primary_explanation", scope=scope))
    if contact in ("MID", "FIRM", "LIGHT"):
        c_label = {"MID": "중간에 가깝고", "FIRM": "다소 단단한 편이고", "LIGHT": "가벼운 편이고"}[contact]
        parts.append(f"접촉감은 {c_label}")
        evidence.append(_evidence_item("contact", contact, used_for="supporting", scope=scope))
        supporting.append({"factor": FACTOR_CONTACT, "claim": f"접촉감 {contact}", "scope": scope})
    if pb == "LOW":
        parts.append("중역 존재감이 낮은 편이며")
        evidence.append(_evidence_item("presence", "LOW", used_for="supporting", scope=scope))
        supporting.append(
            {
                "factor": FACTOR_PRESENCE,
                "claim": "중역 존재감이 낮은 편",
                "scope": scope,
            }
        )
    elif pb == "HIGH":
        parts.append("중역 존재감이 다소 높은 편이며")
        evidence.append(_evidence_item("presence", "HIGH", used_for="supporting", scope=scope))
    if bb == "LOW":
        parts.append("밝기는 어두운 쪽에 가까운 편이에요")
        evidence.append(_evidence_item("brightness", "LOW", used_for="supporting", scope=scope))
    elif bb == "HIGH":
        parts.append("밝기는 밝은 쪽에 가까운 편이에요")
        evidence.append(_evidence_item("brightness", "HIGH", used_for="supporting", scope=scope))
    elif bb == "UNAVAILABLE":
        uncertain.append("brightness")
    if air is not None and air >= 0.58:
        parts.append("공기감이 다소 있는 편이에요")

    lead = _scope_label(scope)
    if parts:
        # Clean trailing conjunctions
        body = " ".join(parts).rstrip("이며").rstrip("이고").rstrip("고")
        if not body.endswith(("요", "다", "음", "예요", "이에요")):
            if body.endswith("편"):
                body = body + "이에요"
            else:
                body = body.rstrip("，, ") + "예요"
        interpretation = (
            f"{lead} {body}. "
            "그래서 공기감이 많은 가벼운 음색보다는 "
            "조금 더 밀도가 있는 쪽으로 들릴 가능성이 있어요."
            if breath == "LOW" and contact in ("MID", "FIRM")
            else f"{lead} {body}."
        )
        if bb == "UNAVAILABLE":
            interpretation += " 밝기나 세부 음색 분포는 이번 녹음에서 충분히 비교되지 않았어요."
        elif feats and len(parts) < 2:
            interpretation += f" 추가로 관찰된 특징: {', '.join(feats[:3])}."
        guidance = GUIDANCE_SONG_COMPOSITE if len(evidence) >= 2 else GUIDANCE_SONG_DIRECT
        primary = {
            "factor": FACTOR_TIMBRE,
            "claim": body,
            "scope": scope,
        }
    else:
        interpretation = (
            f"{lead} 음색 특징을 종합적으로 설명하기엔 확보된 축이 제한적이에요. "
            "음색은 스타일 목표가 달라 좋고 나쁨으로 평가하지 않아요."
        )
        guidance = GUIDANCE_SAFE_GENERAL
        primary = {"factor": FACTOR_TIMBRE, "claim": "제한적 관찰", "scope": scope}

    return {
        "concern_id": concern_id,
        "question_type": TYPE_DESCRIPTIVE,
        "guidance_level": guidance,
        "primary_focus": FACTOR_TIMBRE,
        "primary_explanation": primary,
        "supporting_explanations": supporting[:2],
        "less_likely_explanations": [],
        "uncertain_factors": uncertain,
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
        interpretation = (
            (less[0]["claim"] + " " if less else "")
            + f"{lead} 음역이 올라가는 구간의 연결이 "
            + ("급격히 달라지거나 " if register == "DISRUPTED" else "일부만 안정적으로 이어져 ")
            + "특정 구간에서 소리가 가볍게 느껴질 수 있어 보여요."
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
        interpretation = (
            f"{lead} 얇은 인상을 설명하는 뚜렷한 음향 특징이 강하지 않아요. "
            "특정 음역·모음·구간에서만 나타나는지 확인하는 방향이 적합해 보여요."
        )
        primary_focus = FACTOR_MAINTAIN
        primary = {"factor": FACTOR_MAINTAIN, "claim": "뚜렷한 thin cue 약함", "scope": scope}
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
    lead = _scope_label(scope)
    less: list[dict[str, Any]] = []
    supporting: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    uncertain: list[str] = []

    if bb == "UNAVAILABLE":
        uncertain.append("brightness")
        # Never claim bright/dark directional when unavailable
        if pb == "LOW":
            interpretation = (
                f"{lead} 중역 존재감이 낮은 편이라 소리가 덜 또렷하고 답답하게 느껴지는 데 "
                "일부 관련될 수 있어 보여요. "
                "다만 밝기 자체는 충분히 비교되지 않아, "
                "전체적으로 어두운 음색 때문이라고 단정하지는 않겠습니다."
            )
            primary_focus = FACTOR_PRESENCE
            primary = {"factor": FACTOR_PRESENCE, "claim": "중역 존재감 낮음", "scope": scope}
            evidence.append(_evidence_item("presence", "LOW", used_for="primary_explanation", scope=scope))
            guidance = GUIDANCE_SONG_DIRECT
        else:
            interpretation = (
                f"{lead} 답답함과 직접 연결되는 밝기 비교가 충분하지 않아요. "
                "중역 존재감도 뚜렷한 제한으로 강하지 않아, "
                "특정 모음·구간에서만 답답하게 느껴지는지 확인하는 방향이 좋아요."
            )
            primary_focus = FACTOR_MAINTAIN
            primary = {"factor": FACTOR_MAINTAIN, "claim": "brightness unavailable", "scope": scope}
            guidance = GUIDANCE_SAFE_GENERAL
    elif bb == "LOW":
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
        interpretation = (
            f"{lead} 중역 존재감이 낮은 편이라 덜 또렷하고 답답하게 느껴질 수 있어 보여요."
        )
        primary_focus = FACTOR_PRESENCE
        primary = {"factor": FACTOR_PRESENCE, "claim": "존재감 낮음", "scope": scope}
        evidence.append(_evidence_item("presence", "LOW", used_for="primary_explanation", scope=scope))
        guidance = GUIDANCE_SONG_DIRECT
    else:
        interpretation = (
            f"{lead} 답답함을 설명할 뚜렷한 어두운·낮은 존재감 패턴이 강하지 않아요. "
            "특정 구간에서만 나타나는지 확인하는 방향이 적합해 보여요."
        )
        primary_focus = FACTOR_MAINTAIN
        primary = {"factor": FACTOR_MAINTAIN, "claim": "muffled cue weak", "scope": scope}
        guidance = GUIDANCE_SAFE_GENERAL

    return {
        "concern_id": concern_id,
        "question_type": TYPE_PERCEPTUAL,
        "guidance_level": guidance,
        "primary_focus": primary_focus,
        "primary_explanation": primary,
        "supporting_explanations": supporting[:2],
        "less_likely_explanations": less,
        "uncertain_factors": uncertain,
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
    lead = _scope_label(scope)
    if bb == "HIGH":
        interpretation = f"{lead} 밝기가 밝은 쪽에 가까운 편이라 날카로운 인상과 관련될 가능성이 있어 보여요."
        focus = FACTOR_BRIGHTNESS
        guidance = GUIDANCE_SONG_DIRECT
        evidence = [_evidence_item("brightness", "HIGH", used_for="primary_explanation", scope=scope)]
        uncertain: list[str] = []
    elif bb == "UNAVAILABLE":
        uncertain = ["brightness"]
        if pb == "HIGH":
            interpretation = (
                f"{lead} 중역 존재감이 다소 높은 편이라 또렷·날카로운 인상에 "
                "영향을 줄 수 있어 보여요. 밝기 자체는 충분히 비교되지 않았어요."
            )
            focus = FACTOR_PRESENCE
            guidance = GUIDANCE_SONG_DIRECT
            evidence = [_evidence_item("presence", "HIGH", used_for="primary_explanation", scope=scope)]
        else:
            focus, interpretation = _fallback_interpretation("timbre", concern_id)
            guidance = GUIDANCE_SAFE_GENERAL
            evidence = []
    elif bb == "LOW":
        interpretation = (
            f"{lead} 밝기가 어두운 쪽에 가까워 날카로움의 주된 설명으로는 보이지 않아요. "
            "특정 모음·고음 구간에서만 날카롭게 느껴지는지 확인하는 방향이 좋아요."
        )
        focus = FACTOR_MAINTAIN
        guidance = GUIDANCE_SAFE_GENERAL
        evidence = [_evidence_item("brightness", "LOW", used_for="less_likely", scope=scope)]
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


def _reason_controlish(concern_id: str, snap: dict[str, Any], scope: str, sem: dict[str, Any]) -> dict[str, Any]:
    register = _reg(snap)
    stab = _stability(snap)
    effort = _effort(snap)
    lead = _scope_label(scope)
    category = str(sem.get("category") or "control")
    factors = list(sem.get("candidate_factors") or [])

    if FACTOR_REGISTER in factors and register in ("DISRUPTED", "PARTIAL"):
        interpretation = (
            f"{lead} 음역이 올라가는 구간의 연결이 "
            + ("급격히 달라지는 " if register == "DISRUPTED" else "일부만 안정적으로 이어지는 ")
            + "패턴이 보여요."
        )
        focus = FACTOR_REGISTER
        guidance = GUIDANCE_SONG_DIRECT
        evidence = [_evidence_item("register", register, used_for="primary_explanation", scope=scope)]
    elif FACTOR_STABILITY in factors and stab is False:
        interpretation = f"{lead} 안정성이 떨어지는 구간이 보여, 흔들림·불안정감과 관련될 가능성이 있어 보여요."
        focus = FACTOR_STABILITY
        guidance = GUIDANCE_SONG_DIRECT
        evidence = [_evidence_item("stability", "UNSTABLE", used_for="primary_explanation", scope=scope)]
    elif FACTOR_EFFORT in factors and effort in ("HIGH", "MODERATE"):
        interpretation = f"{lead} 힘 사용이 큰 구간이 함께 보여, 조절이 더 어렵게 느껴질 수 있어 보여요."
        focus = FACTOR_EFFORT
        guidance = GUIDANCE_SONG_DIRECT
        evidence = [_evidence_item("effort", effort, used_for="primary_explanation", scope=scope)]
    elif FACTOR_DYNAMICS in factors:
        focus = FACTOR_DYNAMICS
        interpretation = (
            f"{lead} 강약·지속 관련 특징을 하나로 좁히기는 어려워요. "
            "작은 강도에서 짧은 구간을 유지한 뒤 강약을 조금씩만 바꾸는 연습부터 시작해 보세요."
        )
        guidance = GUIDANCE_SAFE_GENERAL
        evidence = []
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
        out = _reason_descriptive_timbre(concern_id, snap, scope)
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
    elif concern_id in (
        "PITCH_UNSTABLE",
        "REGISTER_CONNECTION_DIFFICULT",
        "VIBRATO_UNSTABLE",
        "DYNAMICS_DIFFICULT",
        "PHRASE_END_WEAK",
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
                focus, interpretation = _fallback_interpretation("timbre", concern_id)
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
                "evidence_used": [],
                "interpretation": interpretation,
                "confidence_label": "medium",
                "causal_certainty": "FUNCTIONAL_HYPOTHESIS",
                "practice_required": True,
                "scope_note": None,
            }
        elif concern_id == "TIMBRE_CHANGES_HIGH":
            out = _reason_controlish(concern_id, snap, scope, {**sem, "type": TYPE_PERCEPTUAL})
        else:
            focus, interpretation = _fallback_interpretation("timbre", concern_id)
            out = {
                "concern_id": concern_id,
                "question_type": TYPE_PERCEPTUAL,
                "guidance_level": GUIDANCE_SAFE_GENERAL,
                "primary_focus": focus,
                "primary_explanation": {"factor": focus, "claim": "nasal percept uncertain", "scope": scope},
                "supporting_explanations": [],
                "less_likely_explanations": [],
                "uncertain_factors": ["nasality_proxy"],
                "evidence_used": [],
                "interpretation": (
                    f"{_scope_label(scope)} 콧소리처럼 들리는 느낌을 직접 확정할 음향 지표는 제한적이에요. "
                    "중역 존재감·밝기 쪽 관찰을 참고하며, 특정 모음에서만 나타나는지 확인하는 방향이 좋아요."
                ),
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
