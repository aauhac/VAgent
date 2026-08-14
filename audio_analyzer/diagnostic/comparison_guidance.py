"""Comparison protocols for Precision Coaching v6.

Protocols are selected by comparison family (concern semantics + focus),
not by hard-coding every concern × evidence combination.
"""

from __future__ import annotations

from typing import Any, Optional

from audio_analyzer.diagnostic.coaching_primitives import (
    COMPARISON_FAMILIES,
    GENERIC_FALLBACK_FAMILIES,
    resolve_comparison_family,
)

RESPONSE_EVIDENCE = "EVIDENCE_EXPLANATION"
RESPONSE_EXPERIMENT = "GUIDED_EXPERIMENT"

_STYLE_BY_TARGET: dict[str, dict[str, str]] = {
    "INTENSE_DISTINCT": {
        "working_direction": "음량을 키우지 않고 짧은 구절에서 질감·존재감만 더 분명하게 표현",
        "what_to_change": "짧은 구절에서 질감이 느껴지되 과하게 밀지 않기",
        "baseline_label": "평소 표현",
        "baseline_instruction": "평소 표현으로 한 번",
        "variant_label": "비교 표현",
        "variant_instruction": "음량을 키우지 않고 짧은 구절에서 질감·존재감만 더 분명하게 표현한 한 번",
        "success_condition": "질감은 더 느껴지지만 힘·불편감 증가 없음",
        "if_better": "그 표현을 유지하세요.",
        "if_not_better": "차이가 거의 없다면, 질감이 필요한 짧은 구절만 따로 비교해보세요.",
        "lead": "강렬하고 개성 있는 느낌을 위해 같은 짧은 구절을 표현만 바꿔 비교해보세요.",
        "avoid": "강렬함을 위해 처음부터 세게 밀기",
    },
    "SOFT_SWEET": {
        "working_direction": "작은~중간 강도에서 구절 연결을 더 매끄럽게 유지",
        "what_to_change": "부드럽게 들리되 숨을 과도하게 섞지 않기",
        "baseline_label": "평소 표현",
        "baseline_instruction": "평소 표현으로 한 번",
        "variant_label": "비교 표현",
        "variant_instruction": "작은~중간 강도에서 구절 연결을 더 매끄럽게 유지한 한 번",
        "success_condition": "더 부드럽게 느껴지지만 숨을 과도하게 섞지 않음",
        "if_better": "그 표현을 유지하세요.",
        "if_not_better": "차이가 거의 없다면, 부드럽게 만들고 싶은 짧은 구절만 따로 비교해보세요.",
        "lead": "부드럽고 감미로운 느낌을 위해 같은 짧은 구절을 표현만 바꿔 비교해보세요.",
        "avoid": "부드러움을 위해 숨을 과도하게 흘리기",
    },
    "DENSE_SOLID": {
        "working_direction": "음량을 더 키우지 않고 소리 중심이 흐려지지 않게 짧은 구절 유지",
        "what_to_change": "밀도감을 유지하되 힘을 더 늘리지 않기",
        "baseline_label": "평소 표현",
        "baseline_instruction": "평소 표현으로 한 번",
        "variant_label": "비교 표현",
        "variant_instruction": "음량을 더 키우지 않고 소리 중심이 흐려지지 않게 짧은 구절을 유지한 한 번",
        "success_condition": "밀도감은 유지되고 effort 증가 없음",
        "if_better": "그 표현을 유지하세요.",
        "if_not_better": "차이가 거의 없다면, 밀도감이 필요한 짧은 구절만 따로 비교해보세요.",
        "lead": "단단하고 밀도 있는 느낌을 위해 같은 짧은 구절을 표현만 바꿔 비교해보세요.",
        "avoid": "밀도를 위해 세게 붙이기",
    },
}

# Banned universal generic leads (must not be the only fallback for all concerns)
_BANNED_GENERIC_LEADS = (
    "같은 구절을 두 가지 방식으로 비교하세요.",
    "평소대로 한 번, 조금 작은 강도로 한 번.",
)


def _reg(snap: Optional[dict[str, Any]]) -> str:
    st = str(((snap or {}).get("register") or {}).get("status") or "").upper()
    if st in ("DISRUPTED", "UNSTABLE", "TRANSITION_EVENTS", "BREAK", "FAIL", "ABRUPT"):
        return "DISRUPTED"
    if st in ("PARTIAL", "INSUFFICIENT", "MIXED"):
        return "PARTIAL"
    if st in ("CONNECTED", "SMOOTH", "STABLE", "CONTINUOUS", "STABLE_LIKE"):
        return "CONNECTED"
    return st or "UNKNOWN"


def _breath(snap: Optional[dict[str, Any]]) -> str:
    return str(((snap or {}).get("breathiness") or {}).get("level") or "").upper()


def _effort(snap: Optional[dict[str, Any]]) -> str:
    return str(((snap or {}).get("effort") or {}).get("level") or "").upper()


def _goal_id(timbre_goal: Any) -> Optional[str]:
    if isinstance(timbre_goal, str) and timbre_goal:
        return timbre_goal.upper()
    if isinstance(timbre_goal, dict):
        tid = str(timbre_goal.get("id") or "").upper()
        return tid or None
    return None


def _pack(raw: dict[str, str], *, family_id: str) -> dict[str, Any]:
    avoid_raw = str(raw.get("avoid") or "")
    avoid = [x.strip() for x in avoid_raw.split(";") if x.strip()]
    lead = str(raw.get("lead") or "")
    for banned in _BANNED_GENERIC_LEADS:
        if lead.strip() == banned:
            lead = str(raw.get("working_direction") or lead)
    return {
        "comparison_family": family_id,
        "working_direction": raw.get("working_direction") or "",
        "what_to_change": raw.get("what_to_change") or "",
        "lead": lead,
        "baseline_label": raw.get("baseline_label") or "평소 방식",
        "baseline_instruction": raw.get("baseline_instruction") or raw.get("A") or "",
        "variant_label": raw.get("variant_label") or "비교 방식",
        "variant_instruction": raw.get("variant_instruction") or raw.get("B") or "",
        "success_condition": raw.get("success_condition") or raw.get("success") or "",
        "if_better": raw.get("if_better") or "그 방향을 유지하세요.",
        "if_not_better": raw.get("if_not_better")
        or "차이가 거의 없다면, 해당 구절의 짧은 구간만 따로 비교해보세요.",
        "avoid": avoid,
        "A": raw.get("baseline_instruction") or raw.get("A") or "",
        "B": raw.get("variant_instruction") or raw.get("B") or "",
        "success": raw.get("success_condition") or raw.get("success") or "",
        "is_generic_fallback": family_id in GENERIC_FALLBACK_FAMILIES,
    }


def build_comparison_protocol(
    concern_id: Optional[str],
    *,
    snap: Optional[dict[str, Any]] = None,
    primary_focus: Optional[str] = None,
    timbre_goal: Any = None,
    evidence_used: Optional[list[Any]] = None,
) -> dict[str, Any]:
    """Return a fully specified A/B protocol from a comparison family."""
    cid = str(concern_id or "").upper()
    focus = str(primary_focus or "").upper()
    snap = snap or {}
    register = _reg(snap)
    breath = _breath(snap)
    effort = _effort(snap)
    tid = _goal_id(timbre_goal)

    family_id = resolve_comparison_family(cid, primary_focus=focus)
    base = dict(COMPARISON_FAMILIES.get(family_id) or COMPARISON_FAMILIES["GENERAL_COMPARE"])

    # Target-driven style exploration for descriptive timbre dissatisfaction
    if cid == "TIMBRE_DISSATISFIED" and tid and tid in _STYLE_BY_TARGET:
        base.update(_STYLE_BY_TARGET[tid])
        family_id = "TIMBRE_STYLE_COMPARE"

    # Evidence overlays (modifiers, not new hard-coded matrices)
    if cid == "VOICE_TOO_NASAL_PERCEPT" and register in ("PARTIAL", "DISRUPTED"):
        family_id = "REGISTER_BRIDGE_COMPARE"
        base = dict(COMPARISON_FAMILIES[family_id])
        base["lead"] = (
            "콧소리처럼 느껴지는 구간에서는 소리를 더 세게 바꾸기보다, "
            "음역이 바뀌는 구간을 매끄럽게 이어보는 쪽을 비교해보세요."
        )
        base["success_condition"] = "콧소리처럼 느껴지는 인상이 줄고 전환도 덜 갑작스러움"
        base["what_to_change"] = "특정 모음·전환 구간에서 소리가 몰리지 않게 연결하기"
        base["avoid"] = "소리를 크게 밀기;코소리를 없애려고 과하게 힘주기;비강 공명·연구개 문제로 단정"

    if cid == "VOICE_TOO_THIN":
        if breath == "LOW" and register in ("PARTIAL", "DISRUPTED"):
            family_id = "REGISTER_BRIDGE_COMPARE"
            base = dict(COMPARISON_FAMILIES[family_id])
            base["lead"] = (
                "숨이 많이 새는 패턴은 두드러지지 않아, 숨을 더 막는 방향은 우선이 아니에요. "
                "지금은 음역이 변할 때도 소리 중심이 유지되는 방식을 먼저 찾아보는 게 좋아요."
            )
            base["working_direction"] = (
                "숨을 더 막는 게 아니라 음역 변화 중 소리 중심이 유지되는 방식 탐색"
            )
        elif breath == "LOW" and focus == "PRESENCE":
            family_id = "PRESENCE_COMPARE"
            base = dict(COMPARISON_FAMILIES[family_id])
            base["lead"] = (
                "이번 분석에서는 숨이 많이 새는 유형은 강하게 보이지 않아, "
                "숨을 더 막는 방향보다 중역 존재감이 유지되는지 비교하는 게 좋아요."
            )
        elif breath == "HIGH":
            family_id = "BREATHINESS_COMPARE"
            base = dict(COMPARISON_FAMILIES[family_id])

    if cid == "VOICE_TOO_DARK_MUFFLED":
        if focus == "BRIGHTNESS":
            family_id = "TIMBRE_STYLE_COMPARE"
            base = dict(COMPARISON_FAMILIES[family_id])
        elif focus == "PRESENCE":
            family_id = "PRESENCE_COMPARE"
            base = dict(COMPARISON_FAMILIES[family_id])
        elif register in ("PARTIAL", "DISRUPTED"):
            family_id = "REGISTER_BRIDGE_COMPARE"
            base = dict(COMPARISON_FAMILIES[family_id])
            base["working_direction"] = "답답한 느낌보다 전환 구간 연결을 먼저 비교"
            base["what_to_change"] = "전환 구간에서도 소리 중심이 유지되도록 연결하기"

    if cid == "VOICE_TOO_BREATHY" and breath == "LOW":
        base["lead"] = (
            "이번 녹음에서 숨 섞임이 전반적으로 높게 보이지는 않았어요. "
            "그래도 느껴지는 구간이 있다면 그 짧은 구간만 따로 비교해보세요."
        )
        base["variant_instruction"] = (
            "숨이 섞여 들리는 짧은 구간만 골라 작은 강도로 한 번 더 유지"
        )

    if cid == "HIGH_NOTE_TOO_EFFORTFUL":
        if effort in ("HIGH", "MODERATE"):
            family_id = "HIGH_NOTE_EFFORT_COMPARE"
            base = dict(COMPARISON_FAMILIES[family_id])
        elif register in ("PARTIAL", "DISRUPTED") and effort == "LOW":
            family_id = "REGISTER_BRIDGE_COMPARE"
            base = dict(COMPARISON_FAMILIES[family_id])
            base["success_condition"] = "전환이 덜 갑작스럽고 힘 증가 없음"

    if cid == "HIGH_NOTE_CANNOT_REACH":
        if focus == "REGISTER_CONNECTION" or register in ("PARTIAL", "DISRUPTED"):
            family_id = "REGISTER_BRIDGE_COMPARE"
            base = dict(COMPARISON_FAMILIES[family_id])
        elif focus == "EFFORT" or effort in ("HIGH", "MODERATE"):
            family_id = "HIGH_NOTE_EFFORT_COMPARE"
            base = dict(COMPARISON_FAMILIES[family_id])
        elif focus == "STABILITY":
            family_id = "HIGH_NOTE_STABILITY_COMPARE"
            base = dict(COMPARISON_FAMILIES[family_id])
        else:
            family_id = "HIGH_NOTE_ACCESS_COMPARE"
            base = dict(COMPARISON_FAMILIES[family_id])

    if cid == "HIGH_NOTE_FLIPS":
        family_id = "REGISTER_BRIDGE_COMPARE"
        base = dict(COMPARISON_FAMILIES[family_id])
        base["success_condition"] = "뒤집힘 감소, 전환이 한 흐름으로 이어짐, 힘 증가 없음"
        base["lead"] = (
            "고음에서 뒤집히는 느낌을 줄이려면, "
            "세게 밀기보다 전환 구간을 작은 강도로 이어서 비교해보세요."
        )

    if cid == "HIGH_NOTE_UNSTABLE":
        family_id = "HIGH_NOTE_STABILITY_COMPARE"
        base = dict(COMPARISON_FAMILIES[family_id])

    if cid == "REGISTER_CONNECTION_DIFFICULT":
        family_id = "REGISTER_BRIDGE_COMPARE"
        base = dict(COMPARISON_FAMILIES[family_id])

    if cid == "TIMBRE_CHANGES_HIGH" and register in ("PARTIAL", "DISRUPTED"):
        family_id = "REGISTER_BRIDGE_COMPARE"
        base = dict(COMPARISON_FAMILIES[family_id])
        base["lead"] = (
            "이번 노래에서는 음역이 올라갈 때 연결이 일부 구간에서만 안정적으로 이어졌어요. "
            "그래서 고음에서 음색이 갑자기 달라지는 느낌을 줄이려면, "
            "높은 음을 더 세게 만드는 것보다 전환 구간을 더 일정하게 연결하는 것을 먼저 해보는 게 좋아요."
        )

    if cid == "THROAT_EFFORT":
        if effort in ("HIGH", "MODERATE"):
            family_id = "HIGH_NOTE_EFFORT_COMPARE"
            base = dict(COMPARISON_FAMILIES[family_id])
        elif register in ("PARTIAL", "DISRUPTED"):
            family_id = "REGISTER_BRIDGE_COMPARE"
            base = dict(COMPARISON_FAMILIES[family_id])
        base["avoid"] = "목 근육 긴장으로 진단하기;세게 밀기"

    if cid in ("VOCAL_FATIGUE", "AFTER_SINGING_FATIGUE"):
        base["lead"] = (
            "피로감의 원인을 음원만으로 단정하지는 않아요. "
            "짧은 반복과 충분한 휴식으로 증상이 늘지 않는지 확인하세요."
        )
        base["avoid"] = "과도한 반복 연습;증상 증가 시에도 계속하기"

    if cid == "HIGH_NOTE_THINS" and tid == "INTENSE_DISTINCT":
        base["variant_instruction"] = (
            "음량은 더 키우지 않고 연결을 유지하면서 "
            "소리 중심이 급격히 가벼워지지 않게 한 번"
        )
        base["success_condition"] = "고음에서 원하는 질감은 유지되지만 힘 증가·불편감 없음"

    packed = _pack(base, family_id=family_id)
    packed["concern_id"] = cid or None
    packed["primary_focus"] = focus or None
    packed["evidence_used_count"] = len(evidence_used or [])
    return packed


def format_comparison_user_block(proto: dict[str, Any]) -> str:
    a = str(proto.get("baseline_instruction") or proto.get("A") or "").strip()
    b = str(proto.get("variant_instruction") or proto.get("B") or "").strip()
    success = str(proto.get("success_condition") or proto.get("success") or "").strip()
    if_better = str(proto.get("if_better") or "").strip()
    lines = ["비교해보기", f"① {a}", f"② {b}"]
    if success:
        lines.append("")
        lines.append("잘 맞는 방향")
        success_core = success
        for prefix in ("두 번째에서 ", "두번째에서 "):
            if success_core.startswith(prefix):
                success_core = success_core[len(prefix) :]
                break
        if if_better and if_better not in success_core:
            # Avoid "…면면" when success already ends with 면/음
            joiner = "" if success_core.endswith(("면", "음", "다", "요")) else "면"
            lines.append(f"두 번째에서 {success_core}{joiner} {if_better}".replace("면면", "면"))
        else:
            lines.append(f"두 번째에서 {success_core}")
    return "\n".join(lines)


def legacy_compat_aliases(proto: dict[str, Any]) -> dict[str, str]:
    """Aliases for callers that still expect A/B/success/lead/what_to_change."""
    return {
        "A": str(proto.get("baseline_instruction") or ""),
        "B": str(proto.get("variant_instruction") or ""),
        "success": str(proto.get("success_condition") or ""),
        "lead": str(proto.get("lead") or ""),
        "what_to_change": str(proto.get("what_to_change") or ""),
        "working_direction": str(proto.get("working_direction") or ""),
    }
