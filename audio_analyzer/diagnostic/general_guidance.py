"""Static low-risk vocal guidance for Precision QA v4.

General knowledge supports ACTION. It never invents a personal diagnosis
and never mutates canonical measurements.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Optional

from audio_analyzer.diagnostic.practice_library import get_practice, practice_for_focus
from audio_analyzer.diagnostic.timbre_goals import option_for

KNOWLEDGE_SCOPE = "GENERAL_VOCAL_GUIDANCE"

MISSING_DATA_MARKERS = (
    "충분히 비교되지 않았어요",
    "비교가 충분하지 않아요",
    "하나로 좁히기 어려워요",
    "이번 노래만으로 알기 어려워요",
    "추가 확인이 필요해요",
    "판단하기 어려워요",
    "확인하기 어려워요",
    "알기 어려워요",
    "충분히 비교되지 않아",
    "밝기 비교가",
    "밝기나 세부 음색 분포는",
    "밝기 자체는 충분히 비교되지",
)

# User-facing A. must not lead with epistemic meta-disclaimers.
EPISTEMIC_DISCLAIMER_MARKERS = (
    "직접 확정할 음향 지표는 제한적이에요",
    "뚜렷한 음향 특징이 강하지 않아요",
    "한 원인으로 단정하지는 않아요",
    "특정 원인을 가정하기보다는",
    "확인하는 방향이 좋아요",
    "확인하는 방향이 적합해 보여요",
    "직접 연결되는 특징이 뚜렷하게 잡히지 않았어요",
    "직접 연결되는 음색 특징이 뚜렷하게 잡히지 않았어요",
    "힘과 직접 연결되는 특징이 뚜렷하게 잡히지 않았어요",
    "이 고민과 직접 연결되는 특징이 뚜렷하게 잡히지 않았어요",
    "이 고민과 직접 연결되는 음색 특징이 뚜렷하게 잡히지 않았어요",
    "두 가지 방식으로 짧게 비교",
    "두 가지 방식으로 비교",
)

ANSWER_MODE_EVIDENCE = "EVIDENCE_EXPLANATION"
ANSWER_MODE_EXPERIMENT = "GUIDED_EXPERIMENT"

from audio_analyzer.diagnostic.comparison_guidance import (
    RESPONSE_EVIDENCE,
    RESPONSE_EXPERIMENT,
    build_comparison_protocol,
    format_comparison_user_block,
)

BAD_KOREAN_SUFFIX_RE = re.compile(r"(적|높|낮)예요")

_BANNED_DIAGNOSIS = (
    "복압 부족",
    "횡격막 약",
    "후두가 올라",
    "목 근육 긴장",
    "성대를 너무 붙",
    "성대가 벌어",
)

GUIDANCE_BY_FOCUS: dict[str, dict[str, Any]] = {
    "REGISTER_CONNECTION": {
        "knowledge": (
            "음역 전환이 급격할 때는 고음을 더 크게 밀기보다 "
            "편안한 강도에서 전환을 연결하는 연습을 우선 시도할 수 있어요."
        ),
        "what_to_change": "우선 음역 연결을 다듬는 것이 좋아요.",
        "short_instruction": (
            "편안한 중음에서 작은 강도로 시작해 위쪽 음역까지 천천히 연결하세요."
        ),
        "success_cues": [
            "전환 지점의 갑작스러운 변화가 줄어듦",
            "힘 증가 없음",
            "불편감 없음",
        ],
        "avoid": ["고음을 세게 밀어 통과하기", "음량을 먼저 키워 넘어가기"],
        "practice_id": "REGISTER_GLIDE_LIGHT",
    },
    "EFFORT": {
        "knowledge": (
            "높은 음이나 큰 소리에서 힘 사용이 증가하는 경우 "
            "음량을 먼저 키우지 않고 편안한 강도에서 범위를 확장하는 방식을 사용할 수 있어요."
        ),
        "what_to_change": "우선 힘 사용이 갑자기 커지지 않게 하는 것이 좋아요.",
        "short_instruction": (
            "작은~중간 강도를 유지한 채 짧게 내고, 그 편안함으로 범위를 넓혀보세요."
        ),
        "success_cues": ["음량을 먼저 키우지 않음", "힘 느낌이 급증하지 않음"],
        "avoid": ["높은 음에 도달하려고 음량부터 키우기"],
        "practice_id": "REDUCE_HIGH_NOTE_EFFORT",
    },
    "STABILITY": {
        "knowledge": (
            "흔들림이 있는 경우 긴 지속보다 짧고 안정적인 구간부터 "
            "반복하며 범위를 확장하는 방식을 사용할 수 있어요."
        ),
        "what_to_change": "우선 짧게 안정되는 구간부터 넓히는 것이 좋아요.",
        "short_instruction": "편안한 중음에서 2~3초만 짧게 유지한 뒤, 안정되면 범위를 넓혀보세요.",
        "success_cues": ["짧은 구간에서 흔들림이 크지 않음", "불편감 없음"],
        "avoid": ["길게 버텨 흔들림을 키우기"],
        "practice_id": "STABILITY_SHORT_HOLD",
    },
    "PRESENCE": {
        "knowledge": (
            "소리 존재감을 유지하려고 음량을 과하게 키우기보다 "
            "편안한 강도에서 중심이 흐려지지 않는 패턴을 탐색할 수 있어요."
        ),
        "what_to_change": "우선 밀지 않으면서 소리 중심이 흐려지지 않게 하는 것이 좋아요.",
        "short_instruction": "편안한 강도에서 짧은 모음을 유지하며 소리가 얇아지지 않는지 비교해보세요.",
        "success_cues": ["중역 존재감이 유지됨", "음량을 과하게 키우지 않음"],
        "avoid": ["존재감을 위해 과하게 밀기"],
        "practice_id": "PRESENCE_WITHOUT_PUSHING",
    },
    "BRIGHTNESS": {
        "knowledge": (
            "밝기 인상을 바꿀 때도 음량을 먼저 키우기보다 "
            "짧은 구절에서 편안한 강도의 표현을 비교하는 방식이 좋아요."
        ),
        "what_to_change": "우선 짧은 구절에서 편안한 강도의 표현을 비교해보세요.",
        "short_instruction": (
            "같은 구절을 ① 평소대로, ② 작은 강도로 과하게 밀지 않고 짧게 비교해보세요."
        ),
        "success_cues": ["음량을 먼저 키우지 않음", "불편감 없음"],
        "avoid": ["밝게 하려고 세게 밀기"],
        "practice_id": "PRESENCE_WITHOUT_PUSHING",
    },
    "BREATHINESS": {
        "knowledge": (
            "숨 섞임이 클 때는 숨을 갑자기 막기보다 "
            "편안한 강도에서 짧은 지속을 유지하는 쪽을 먼저 시도할 수 있어요."
        ),
        "what_to_change": "우선 짧은 지속에서 숨이 과하게 새지 않는 패턴을 찾는 것이 좋아요.",
        "short_instruction": "편안한 중음에서 짧게 유지하며 숨이 과하게 새지 않는 쪽을 비교해보세요.",
        "success_cues": ["짧은 구간이 유지됨", "불편감 없음"],
        "avoid": ["숨을 갑자기 막아 세게 붙이기"],
        "practice_id": "BREATHINESS_CONTROL",
    },
    "AIRINESS": {
        "knowledge": (
            "공기감이 클 때도 숨을 과도하게 흘리거나 갑자기 막기보다 "
            "짧은 구간에서 편안한 중심을 유지하는 비교가 좋아요."
        ),
        "what_to_change": "우선 짧은 구간에서 중심이 흐려지지 않는 쪽을 비교해보세요.",
        "short_instruction": "같은 구절을 작은 강도로 짧게 비교하며 더 안정적인 쪽을 찾아보세요.",
        "success_cues": ["짧은 구간이 이어짐", "힘을 급증시키지 않음"],
        "avoid": ["공기감을 위해 숨을 과도하게 흘리기"],
        "practice_id": "BREATHINESS_CONTROL",
    },
    "CONTACT": {
        "knowledge": (
            "접촉 느낌을 바꾸려 할 때도 세게 붙이거나 힘을 빼 연결을 끊기보다 "
            "편안한 강도의 짧은 지속부터 비교하는 방식이 좋아요."
        ),
        "what_to_change": "우선 편안한 강도의 짧은 지속부터 비교해보세요.",
        "short_instruction": "작은 강도로 짧게 유지하며 더 편안한 쪽을 찾아보세요.",
        "success_cues": ["불편감 없이 짧은 구간 유지"],
        "avoid": ["세게 붙여 통과하기"],
        "practice_id": "MAINTAIN_LOW_EFFORT",
    },
    "TIMBRE": {
        "knowledge": (
            "뚜렷한 기능적 제한이 없다면 목표 음색을 작은 강도로 "
            "짧은 구절에서 비교 탐색할 수 있어요."
        ),
        "what_to_change": "우선 짧은 구절에서 원하는 느낌에 가까운 표현을 비교해보세요.",
        "short_instruction": "편안한 강도로 짧은 구절을 부르며 과하게 밀지 마세요.",
        "success_cues": ["음색이 갑자기 과하게 바뀌지 않음", "불편감 없음"],
        "avoid": ["음색을 바꾸려고 세게 밀기"],
        "practice_id": "TIMBRE_PRESERVE",
    },
    "TEXTURE": {
        "knowledge": (
            "질감 인상은 긴 프레이즈보다 짧은 구절에서 "
            "작은 강도로 비교하는 쪽이 안전해요."
        ),
        "what_to_change": "우선 짧은 구절에서 질감이 과하지 않은 쪽을 비교해보세요.",
        "short_instruction": "작은 강도로 짧게 부르며 질감이 갑자기 거칠어지지 않는지 확인해보세요.",
        "success_cues": ["짧은 구간 유지", "힘을 급증시키지 않음"],
        "avoid": ["질감을 위해 세게 밀어붙이기"],
        "practice_id": "TIMBRE_PRESERVE",
    },
    "DYNAMICS": {
        "knowledge": (
            "강약 조절은 긴 프레이즈보다 짧은 구간에서 작은 강도로 시작해 "
            "편안함이 유지되는 범위를 먼저 찾는 방식이 좋아요."
        ),
        "what_to_change": "우선 짧은 구간에서 작은 강약 차이만 비교해보세요.",
        "short_instruction": "같은 구절을 작은 강도로 유지한 뒤, 강약을 조금씩만 바꿔보세요.",
        "success_cues": ["음량이 갑자기 커지지 않음", "불편감 없음"],
        "avoid": ["강약을 위해 처음부터 세게 밀기"],
        "practice_id": "MAINTAIN_LOW_EFFORT",
    },
    "HIGH_NOTE": {
        "knowledge": (
            "고음 연습에서는 음량을 먼저 키우지 않고 "
            "편안한 중음에서 위쪽 음역까지 작은 강도로 연결하는 접근을 사용할 수 있어요."
        ),
        "what_to_change": "우선 고음을 더 세게 내기보다 연결을 다듬는 것이 좋아요.",
        "short_instruction": "편안한 중음에서 작은 강도로 시작해 위쪽 음역까지 천천히 연결하세요.",
        "success_cues": ["음량이 갑자기 커지지 않음", "힘 증가 없음"],
        "avoid": ["높은 음을 세게 밀어 통과하기"],
        "practice_id": "REGISTER_GLIDE_LIGHT",
    },
    "MAINTAIN": {
        "knowledge": (
            "같은 구절을 평소 방식과 작은 강도 방식으로 짧게 비교하며 "
            "더 편안하고 안정적인 쪽을 찾는 것부터 시작할 수 있어요."
        ),
        "what_to_change": "우선 같은 구절을 작은 강도로 짧게 비교해보세요.",
        "short_instruction": (
            "같은 구절을 ① 평소대로, ② 작은 강도로 과하게 밀지 않고 짧게 비교하며 "
            "더 편안하고 안정적인 쪽을 찾아보세요."
        ),
        "success_cues": ["불편감 없이 짧은 구간 유지", "음량을 갑자기 키우지 않음"],
        "avoid": ["원인을 가정하고 세게 바꾸기"],
        "practice_id": "MAINTAIN_LOW_EFFORT",
    },
    "SAFETY": {
        "knowledge": "통증이나 지속 불편이 있으면 강한 연습보다 휴식이 우선이에요.",
        "what_to_change": "지금은 강한 고음·큰 소리 반복을 멈추는 것이 좋아요.",
        "short_instruction": "불편감이 있으면 강한 고음과 큰 소리 반복을 멈추고 짧게 쉬세요.",
        "success_cues": ["불편감이 늘지 않음"],
        "avoid": ["통증 상태에서의 강한 고음 반복", "적극적인 음색 탐색"],
        "practice_id": "SAFETY_STOP",
    },
}

_STYLE_FOCUS = {
    "DENSE_SOLID": "STYLE_DENSE_SOLID",
    "BRIGHT_CLEAR": "STYLE_BRIGHT_CLEAR",
    "SOFT_SWEET": "STYLE_SOFT_SWEET",
    "LIGHT_CLEAR": "STYLE_LIGHT_CLEAR",
    "WARM_FULL": "STYLE_WARM_FULL",
    "AIRY_DELICATE": "STYLE_AIRY_DELICATE",
    "INTENSE_DISTINCT": "STYLE_INTENSE_DISTINCT",
}


def guidance_for_focus(primary_focus: str, *, timbre_goal_id: Optional[str] = None) -> dict[str, Any]:
    focus = str(primary_focus or "MAINTAIN").upper()
    if focus == "STYLE" and timbre_goal_id:
        focus = _STYLE_FOCUS.get(str(timbre_goal_id).upper(), "TIMBRE")
    base = GUIDANCE_BY_FOCUS.get(focus) or GUIDANCE_BY_FOCUS["MAINTAIN"]
    out = dict(base)
    if focus.startswith("STYLE_"):
        p = get_practice(focus) or get_practice("TIMBRE_PRESERVE") or {}
        out = {
            "knowledge": (
                "뚜렷한 기능적 제한이 없다면 목표 음색을 작은 강도로 "
                "짧은 구절에서 비교 탐색할 수 있어요."
            ),
            "what_to_change": "우선 짧은 구절에서 원하는 느낌에 가까운 표현을 비교해보세요.",
            "short_instruction": str(p.get("instruction") or out.get("short_instruction") or ""),
            "success_cues": list(p.get("success_cues") or out.get("success_cues") or []),
            "avoid": list(p.get("avoid") or out.get("avoid") or []),
            "practice_id": p.get("practice_id") or "TIMBRE_PRESERVE",
        }
    return out


def observed_facts_from_snapshot(snap: Optional[dict[str, Any]]) -> list[dict[str, str]]:
    """User-facing observed facts from canonical snapshot. Skips unavailable axes."""
    snap = snap or {}
    facts: list[dict[str, str]] = []

    effort = str((snap.get("effort") or {}).get("level") or "").upper()
    if effort in ("LOW", "MODERATE", "HIGH"):
        label = {"LOW": "힘 사용이 낮은 편", "MODERATE": "힘 사용이 중간 정도", "HIGH": "힘 사용이 큰 편"}[effort]
        facts.append({"axis": "effort", "status": effort, "text": label})

    breath = str((snap.get("breathiness") or {}).get("level") or "").upper()
    if breath in ("LOW", "MODERATE", "HIGH"):
        label = {
            "LOW": "숨 섞임이 적은 편",
            "MODERATE": "숨 섞임이 중간 정도",
            "HIGH": "숨 섞임이 큰 편",
        }[breath]
        facts.append({"axis": "breathiness", "status": breath, "text": label})

    contact = str((snap.get("contact") or {}).get("status") or "").upper()
    if contact in ("MID", "FIRM", "LIGHT"):
        label = {
            "MID": "접촉 특성은 중간 정도",
            "FIRM": "접촉 특성은 다소 단단한 편",
            "LIGHT": "접촉 특성은 가벼운 편",
        }[contact]
        facts.append({"axis": "contact", "status": contact, "text": label})

    stab = str((snap.get("stability") or {}).get("status") or "").upper()
    if stab in ("STABLE", "LOW", "NORMAL", "OK_PROXY"):
        facts.append({"axis": "stability", "status": "STABLE", "text": "발성 안정성은 비교적 유지되는 편"})
    elif stab in ("UNSTABLE", "HIGH", "IRREGULAR"):
        facts.append({"axis": "stability", "status": "UNSTABLE", "text": "발성 안정성이 떨어지는 구간이 있는 편"})

    register = str((snap.get("register") or {}).get("status") or "").upper()
    if register in ("DISRUPTED", "UNSTABLE", "TRANSITION_EVENTS", "BREAK", "FAIL"):
        facts.append(
            {
                "axis": "register",
                "status": "DISRUPTED",
                "text": "음역이 올라갈 때 발성 특성이 급격하게 달라지는 구간이 있음",
            }
        )
    elif register in ("PARTIAL", "INSUFFICIENT", "MIXED"):
        facts.append(
            {
                "axis": "register",
                "status": "PARTIAL",
                "text": "음역이 올라가는 연결이 일부 구간에서만 안정적으로 이어짐",
            }
        )
    elif register in ("CONNECTED", "SMOOTH", "STABLE", "CONTINUOUS", "STABLE_LIKE"):
        facts.append(
            {
                "axis": "register",
                "status": "CONNECTED",
                "text": "음역이 올라갈 때 연결이 비교적 유지되는 편",
            }
        )

    chest = chest_tendency(snap)
    if chest == "CHEST":
        facts.append({"axis": "head_chest", "status": "CHEST", "text": "흉성 쪽 음향 성향이 비교적 분명함"})
    elif chest == "HEAD":
        facts.append({"axis": "head_chest", "status": "HEAD", "text": "두성 쪽 음향 성향이 비교적 분명함"})

    timbre = snap.get("timbre") or {}
    presence = timbre.get("presence")
    try:
        pv = float(presence) if presence is not None else None
    except (TypeError, ValueError):
        pv = None
    if pv is not None:
        if pv <= 0.42:
            facts.append({"axis": "presence", "status": "LOW", "text": "중역 존재감이 낮은 편"})
        elif pv >= 0.58:
            facts.append({"axis": "presence", "status": "HIGH", "text": "중역 존재감이 다소 높은 편"})
        else:
            facts.append({"axis": "presence", "status": "MID", "text": "중역 존재감은 중간 정도"})

    brightness = timbre.get("brightness")
    try:
        bv = float(brightness) if brightness is not None else None
    except (TypeError, ValueError):
        bv = None
    if bv is not None:
        if bv <= 0.42:
            facts.append({"axis": "brightness", "status": "LOW", "text": "밝기는 어두운 쪽에 가까운 편"})
        elif bv >= 0.58:
            facts.append({"axis": "brightness", "status": "HIGH", "text": "밝기는 밝은 쪽에 가까운 편"})
        else:
            facts.append({"axis": "brightness", "status": "MID", "text": "밝기는 중간 정도"})

    return facts


def chest_tendency(snap: Optional[dict[str, Any]]) -> Optional[str]:
    snap = snap or {}
    reg = snap.get("register") or {}
    hc = reg.get("head_chest") or {}
    label = str(hc.get("broad_label") or hc.get("label") or "")
    mods = [str(m).upper() for m in (reg.get("modifiers") or [])]
    ratio = hc.get("chest_ratio")
    if any("CHEST" in m and "HEAD" not in m for m in mods) or "흉" in label:
        return "CHEST"
    if any("HEAD" in m and "CHEST" not in m for m in mods) or "두성" in label or "헤드" in label:
        return "HEAD"
    try:
        if ratio is not None:
            r = float(ratio)
            if r >= 0.55:
                return "CHEST"
            if r <= 0.40:
                return "HEAD"
    except (TypeError, ValueError):
        return None
    return None


_GOAL_DIRECTION = {
    "DENSE_SOLID": "단단하고 밀도 있는",
    "BRIGHT_CLEAR": "밝고 선명한",
    "SOFT_SWEET": "부드럽고 감미로운",
    "LIGHT_CLEAR": "맑고 가벼운",
    "WARM_FULL": "따뜻하고 풍성한",
    "AIRY_DELICATE": "공기감 있고 여린",
    "INTENSE_DISTINCT": "강렬하고 개성 있는",
}


def timbre_goal_support_line(timbre_goal: Any, snap: Optional[dict[str, Any]] = None) -> str:
    """Perceptual target sentence. Does not rewrite measurements."""
    tid = ""
    if isinstance(timbre_goal, str):
        tid = timbre_goal.upper()
    elif isinstance(timbre_goal, dict):
        tid = str(timbre_goal.get("id") or "").upper()
    if not tid or tid == "RECOMMEND_FOR_ME":
        return ""
    noun = _GOAL_DIRECTION.get(tid)
    if not noun:
        opt = option_for(tid) or {}
        noun = str(opt.get("label") or "").strip().rstrip("게")
    if not noun:
        return ""
    effort = (snap or {}).get("effort") or {}
    effort_level = str(effort.get("level") or "").upper()
    keep_effort = (
        "현재의 편안한 힘 사용은 유지하면서, "
        if (
            effort_level == "LOW"
            and bool(effort.get("available"))
            and (
                bool(effort.get("reliable_for_preserve"))
                or str(effort.get("confidence_label") or "").lower() in ("medium", "high")
            )
        )
        else "음량을 먼저 키우지 않으면서, "
    )
    return (
        f"원하는 {noun} 방향을 위해서는 {keep_effort}"
        "짧은 구절에서 연결이 매끄러운 표현을 먼저 탐색해보는 것이 좋아요."
    )


def _split_sentences(text: str) -> list[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    parts = re.split(r"(?<=[요다])\.\s*", raw)
    out: list[str] = []
    for p in parts:
        s = p.strip(" \n")
        if not s:
            continue
        if not s.endswith(("요", "다", "음", ".", "예요", "이에요")):
            s = s + "."
        elif not s.endswith("."):
            s = s + "."
        out.append(s)
    return out


def strip_missing_data_phrases(text: str, *, has_related_evidence: bool) -> str:
    if not has_related_evidence:
        return str(text or "").strip()
    kept: list[str] = []
    for sent in _split_sentences(text):
        if any(m in sent for m in MISSING_DATA_MARKERS):
            continue
        kept.append(sent)
    return " ".join(kept).strip()


def strip_epistemic_disclaimers(text: str) -> str:
    """Remove user-facing meta-disclaimers. Keep content sentences only."""
    kept: list[str] = []
    for sent in _split_sentences(text):
        if any(m in sent for m in EPISTEMIC_DISCLAIMER_MARKERS):
            continue
        if any(m in sent for m in MISSING_DATA_MARKERS):
            continue
        kept.append(sent)
    return " ".join(kept).strip()


def comparison_protocol_for(
    concern_id: Optional[str],
    *,
    snap: Optional[dict[str, Any]] = None,
    primary_focus: Optional[str] = None,
    timbre_goal: Any = None,
    evidence_used: Optional[list[Any]] = None,
) -> dict[str, Any]:
    return build_comparison_protocol(
        concern_id,
        snap=snap,
        primary_focus=primary_focus,
        timbre_goal=timbre_goal,
        evidence_used=evidence_used,
    )


def format_comparison_block(proto: dict[str, Any]) -> str:
    return format_comparison_user_block(proto)


def fix_korean_suffixes(text: str) -> str:
    t = BAD_KOREAN_SUFFIX_RE.sub(lambda m: m.group(1) + "어요", str(text or ""))
    t = t.replace("적예요", "적어요").replace("높예요", "높아요").replace("낮예요", "낮아요")
    return t


def contains_banned_personal_diagnosis(text: str) -> bool:
    t = str(text or "")
    return any(b in t for b in _BANNED_DIAGNOSIS)


def _zero_evidence_scope_line(concern_id: Optional[str] = None) -> str:
    proto = comparison_protocol_for(concern_id)
    lead = str(proto.get("lead") or "").strip()
    return lead or "같은 짧은 구절을 두 방식으로 비교해보세요."


def finalize_actionable_qa(
    hyp: dict[str, Any],
    snap: Optional[dict[str, Any]] = None,
    *,
    timbre_goal: Any = None,
) -> dict[str, Any]:
    """Attach QA contract fields. Never mutates canonical snapshot. Never invents diagnosis."""
    out = dict(hyp or {})
    snap = snap or {}
    snap_before = copy.deepcopy(snap)

    focus = str(out.get("primary_focus") or "MAINTAIN")
    qtype = str(out.get("question_type") or "")
    concern_id = str(out.get("concern_id") or "")
    safety = str(out.get("guidance_level") or "") == "SAFETY_ONLY" or focus == "SAFETY"
    guidance_level = str(out.get("guidance_level") or "")

    observed = observed_facts_from_snapshot(snap)
    evidence_used = list(out.get("evidence_used") or [])
    has_related = bool(evidence_used) or bool(out.get("evidence"))
    if not has_related and observed:
        # Available canonical facts still count as related evidence for missing-data gating.
        has_related = True

    interpretation = fix_korean_suffixes(str(out.get("interpretation") or "").strip())
    if has_related:
        interpretation = strip_missing_data_phrases(interpretation, has_related_evidence=True)
    if not safety:
        interpretation = strip_epistemic_disclaimers(interpretation)

    if safety:
        g = guidance_for_focus("SAFETY")
    else:
        g = guidance_for_focus(focus, timbre_goal_id=_goal_id(timbre_goal) if qtype == "DESCRIPTIVE_PROFILE" else None)

    # knowledge_support is INTERNAL reasoning only — never appended to public answer.
    knowledge = str(g.get("knowledge") or "").strip()
    what = str(g.get("what_to_change") or "").strip()
    short = str(g.get("short_instruction") or "").strip()
    cues = list(g.get("success_cues") or [])
    avoid = list(g.get("avoid") or [])
    pid = str(g.get("practice_id") or "")

    proto = (
        comparison_protocol_for(
            concern_id,
            snap=snap,
            primary_focus=focus,
            timbre_goal=timbre_goal,
            evidence_used=evidence_used,
        )
        if not safety
        else {}
    )
    if proto.get("what_to_change"):
        what = str(proto["what_to_change"]).strip() or what
    if proto.get("avoid"):
        avoid = list(proto.get("avoid") or avoid)

    answer_mode = ANSWER_MODE_EVIDENCE
    if safety:
        answer_mode = "SAFETY"
    elif guidance_level in ("SAFE_GENERAL_GUIDANCE", "GUIDANCE_ONLY", "") and not evidence_used:
        answer_mode = ANSWER_MODE_EXPERIMENT
    elif not evidence_used and focus in ("MAINTAIN", "TIMBRE"):
        answer_mode = ANSWER_MODE_EXPERIMENT
    # Evidence explanation still carries an explicit comparison for actionability.

    if safety:
        knowledge = GUIDANCE_BY_FOCUS["SAFETY"]["knowledge"]
        what = GUIDANCE_BY_FOCUS["SAFETY"]["what_to_change"]
        short = GUIDANCE_BY_FOCUS["SAFETY"]["short_instruction"]
        cues = list(GUIDANCE_BY_FOCUS["SAFETY"]["success_cues"])
        avoid = list(GUIDANCE_BY_FOCUS["SAFETY"]["avoid"])
        pid = "SAFETY_STOP"
        if not interpretation:
            interpretation = (
                "통증이나 지속적인 불편감은 음향 분석만으로 원인을 판단할 수 없어요. "
                "지금은 강한 고음·큰 소리 반복보다 휴식이 우선이에요."
            )
    else:
        if not interpretation:
            if answer_mode == ANSWER_MODE_EXPERIMENT:
                interpretation = _zero_evidence_scope_line(concern_id)
            elif has_related:
                bits = [f["text"] for f in observed[:4]]
                interpretation = (
                    "이번 노래에서는 " + ", ".join(bits) + "이에요."
                    if bits
                    else _zero_evidence_scope_line(concern_id)
                )
            else:
                interpretation = _zero_evidence_scope_line(concern_id)
        goal_line = ""
        if qtype == "DESCRIPTIVE_PROFILE":
            goal_line = timbre_goal_support_line(timbre_goal, snap)
            if goal_line and goal_line not in interpretation:
                interpretation = (interpretation.rstrip() + " " + goal_line).strip()

    interpretation = fix_korean_suffixes(interpretation)
    if contains_banned_personal_diagnosis(interpretation):
        for bad in _BANNED_DIAGNOSIS:
            interpretation = interpretation.replace(bad, "")
        interpretation = re.sub(r"\s{2,}", " ", interpretation).strip()

    practice = out.get("practice") if isinstance(out.get("practice"), dict) else None
    if safety:
        practice = get_practice("SAFETY_STOP")
        out["practice"] = dict(practice) if practice else None
        out["practice_required"] = True
    elif out.get("practice_required") is False:
        pass
    elif not practice and pid:
        practice = practice_for_focus(focus) or get_practice(pid)
        if practice:
            out["practice"] = dict(practice)

    if practice:
        cues = list(practice.get("success_cues") or cues)
        avoid = list(practice.get("avoid") or avoid)
        pid = str(practice.get("practice_id") or pid)

    if not safety and proto.get("success_condition"):
        cues = list(
            dict.fromkeys(
                [
                    *(cues or []),
                    str(proto.get("success_condition")),
                    "힘 증가 없음",
                ]
            )
        )

    if not safety and proto:
        a = proto.get("baseline_instruction") or proto.get("A")
        b = proto.get("variant_instruction") or proto.get("B")
        short = f"① {a} / ② {b} 를 비교해보세요." if a and b else short

    comparison = None
    if not safety and proto:
        comparison = {
            "comparison_family": proto.get("comparison_family"),
            "baseline_label": proto.get("baseline_label"),
            "baseline_instruction": proto.get("baseline_instruction") or proto.get("A"),
            "variant_label": proto.get("variant_label"),
            "variant_instruction": proto.get("variant_instruction") or proto.get("B"),
            "success_condition": proto.get("success_condition") or proto.get("success"),
            "if_better": proto.get("if_better"),
            "if_not_better": proto.get("if_not_better"),
            # Compat
            "A": proto.get("baseline_instruction") or proto.get("A"),
            "B": proto.get("variant_instruction") or proto.get("B"),
            "success": proto.get("success_condition") or proto.get("success"),
            "lead": proto.get("lead"),
            "is_generic_fallback": bool(proto.get("is_generic_fallback")),
        }

    working = "" if safety else str(proto.get("working_direction") or "").strip()
    # Consensus eligibility: evidence-backed OR concern-specific guided experiment (not bare MAINTAIN)
    consensus_ok = False
    if not safety:
        if evidence_used and focus not in ("", "MAINTAIN", "TIMBRE", "STYLE"):
            consensus_ok = True
        elif answer_mode == ANSWER_MODE_EXPERIMENT and concern_id and focus not in ("", "MAINTAIN"):
            consensus_ok = True
        elif guidance_level in ("SONG_DIRECT", "SONG_COMPOSITE", "CONTROLLED_CONFIRMED") and focus not in (
            "",
            "MAINTAIN",
            "TIMBRE",
            "STYLE",
        ):
            consensus_ok = True

    out["observed"] = [f["text"] for f in observed]
    out["interpretation"] = interpretation
    out["knowledge_support"] = knowledge  # INTERNAL — do not append to public answer
    out["knowledge_support_internal"] = True
    out["what_to_change"] = what
    out["working_direction"] = working
    out["action"] = {
        "practice_id": pid or None,
        "short_instruction": short,
    }
    out["success_cues"] = cues
    out["avoid"] = avoid
    out["knowledge_scope"] = KNOWLEDGE_SCOPE
    out["answer_summary"] = interpretation
    out["answer_mode"] = answer_mode
    out["response_mode"] = answer_mode  # alias for v5 contract
    out["comparison"] = comparison
    out["comparison_protocol"] = comparison  # backward-compatible alias
    out["counts_for_consensus"] = consensus_ok
    if out.get("scope_note") is None:
        out["scope_note"] = None

    # Guard: general knowledge must not rewrite snapshot
    if snap != snap_before:
        snap.clear()
        snap.update(snap_before)

    return out


def _goal_id(timbre_goal: Any) -> Optional[str]:
    if isinstance(timbre_goal, str) and timbre_goal:
        return timbre_goal.upper()
    if isinstance(timbre_goal, dict):
        tid = str(timbre_goal.get("id") or "").upper()
        return tid or None
    return None


def public_answer_text(hyp: dict[str, Any]) -> str:
    """User-facing QA body: working direction text only.

    knowledge_support stays internal.
    Comparison A/B is exposed via `comparison` for UI (and embedded for API clients).
    Full practice instructions stay in the global practice section.
    """
    text = fix_korean_suffixes(str(hyp.get("interpretation") or "").strip())
    text = strip_epistemic_disclaimers(text)
    qtype = str(hyp.get("question_type") or "")
    safety = str(hyp.get("guidance_level") or "") == "SAFETY_ONLY"
    what = str(hyp.get("what_to_change") or "").strip()
    if safety:
        return text

    proto = hyp.get("comparison") or hyp.get("comparison_protocol")
    if not isinstance(proto, dict) or not (
        proto.get("baseline_instruction") or proto.get("A")
    ):
        proto = comparison_protocol_for(
            str(hyp.get("concern_id") or ""),
            primary_focus=str(hyp.get("primary_focus") or ""),
            evidence_used=list(hyp.get("evidence_used") or []),
        )

    block = format_comparison_block(proto)
    # Embed A/B for API / non-UI consumers; UI may also render structured `comparison`
    if "①" not in text and block:
        text = f"{text}\n\n{block}".strip() if text else block

    if qtype == "DESCRIPTIVE_PROFILE":
        if what and what not in text:
            text = (text + " " + what).strip()
        return text
    # Use "\n\n→ " — plain "→" also appears in labels like "중음→고음"
    if what and "\n\n→ " not in text and not text.rstrip().endswith(what):
        text = f"{text}\n\n→ {what}"
    return text.strip()
