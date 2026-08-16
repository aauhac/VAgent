"""Deterministic coaching goal planner (precision-goal-v1.0).

No LLM. Target timbre is a perceptual goal — never a direct acoustic mapping.
Canonical snapshot is the only current-state source of truth.
"""

from __future__ import annotations

from typing import Any, Optional

from audio_analyzer.diagnostic.practice_library import practice_for_focus
from audio_analyzer.diagnostic.question_semantics import semantics_for
from audio_analyzer.diagnostic.song_evidence import get_canonical_snapshot
from audio_analyzer.diagnostic.timbre_goals import (
    HIGH_NOTE_DESIRED_OUTCOMES,
    option_for,
)
from audio_analyzer.diagnostic.coaching_protocol import build_coaching_protocol

GOAL_VERSION = "precision-goal-v1.2"

FOCUS_LABELS = {
    "REGISTER_CONNECTION": "성구 연결",
    "EFFORT": "힘 사용",
    "STABILITY": "안정성",
    "PRESENCE": "중역 존재감",
    "BRIGHTNESS": "밝기",
    "BREATHINESS": "숨 섞임",
    "CONTACT": "접촉감",
    "TIMBRE": "음색 표현",
    "DYNAMICS": "강약 조절",
    "STYLE": "목표 음색 표현",
    "SAFETY": "안전",
    "MAINTAIN": "현재 패턴 유지",
}

STYLE_TARGET_LABELS = {
    "BRIGHT_CLEAR": "밝고 선명한 표현",
    "DENSE_SOLID": "밀도 있는 표현",
    "SOFT_SWEET": "부드러운 표현",
    "LIGHT_CLEAR": "가볍고 맑은 표현",
    "WARM_FULL": "따뜻하고 풍성한 표현",
    "AIRY_DELICATE": "섬세한 표현",
    "INTENSE_DISTINCT": "강렬한 표현",
}

PRESERVE_LABELS = {
    "LOW_EFFORT": "힘 사용이 낮은 편",
    "STABILITY": "발성 안정성이 비교적 유지됨",
    "LOW_BREATHINESS": "숨 섞임이 낮은 편",
    "CONNECTED_REGISTER": "성구 연결이 비교적 유지됨",
}

_GUIDANCE_RANK = {
    "SAFETY_ONLY": 0,
    "CONTROLLED_CONFIRMED": 1,
    "SONG_DIRECT": 2,
    "SONG_COMPOSITE": 3,
    "SAFE_GENERAL_GUIDANCE": 5,
}

_STATUS_RANK = {
    "SAFETY_ONLY": 0,
    "CONFIRMED": 1,
    "PARTIALLY_SUPPORTED": 2,
    "CONTEXT_DEPENDENT": 3,
    "UNRESOLVED": 5,
    "NOT_SUPPORTED": 6,
    "NOT_SUPPORTED_IN_THIS_RECORDING": 6,
}


def _effort(snap: dict[str, Any]) -> str:
    return str((snap.get("effort") or {}).get("level") or "UNKNOWN").upper()


def _contact(snap: dict[str, Any]) -> str:
    return str((snap.get("contact") or {}).get("status") or "UNKNOWN").upper()


def _breath(snap: dict[str, Any]) -> str:
    return str((snap.get("breathiness") or {}).get("level") or "UNKNOWN").upper()


def _reg(snap: dict[str, Any]) -> str:
    st = str((snap.get("register") or {}).get("status") or "").upper()
    if st in ("DISRUPTED", "UNSTABLE", "TRANSITION_EVENTS", "TRANSITION_UNSTABLE", "BREAK"):
        return "DISRUPTED"
    if st in ("PARTIAL", "INSUFFICIENT", "MIXED"):
        return "PARTIAL"
    if st in ("CONNECTED", "SMOOTH", "STABLE", "CONTINUOUS", "STABLE_LIKE"):
        return "CONNECTED"
    return "UNKNOWN"


def _presence_bucket(snap: dict[str, Any]) -> str:
    p = (snap.get("timbre") or {}).get("presence")
    try:
        v = float(p) if p is not None else None
    except (TypeError, ValueError):
        v = None
    if v is None:
        return "UNAVAILABLE"
    if v <= 0.42:
        return "LOW"
    if v >= 0.58:
        return "HIGH"
    return "MID"


def _brightness_bucket(snap: dict[str, Any]) -> str:
    b = (snap.get("timbre") or {}).get("brightness")
    try:
        v = float(b) if b is not None else None
    except (TypeError, ValueError):
        v = None
    if v is None:
        return "UNAVAILABLE"
    if v <= 0.42:
        return "LOW"
    if v >= 0.58:
        return "HIGH"
    return "MID"


def _stab_ok(snap: dict[str, Any]) -> Optional[bool]:
    st = str((snap.get("stability") or {}).get("status") or "").upper()
    if not st or st == "UNKNOWN":
        return None
    if st in ("STABLE", "LOW", "NORMAL", "OK_PROXY"):
        return True
    if st in ("UNSTABLE", "HIGH", "IRREGULAR"):
        return False
    return None


def _preserve_factors(snap: dict[str, Any]) -> list[str]:
    out: list[str] = []
    effort = snap.get("effort") or {}
    level = str(effort.get("level") or "").upper()
    conf = str(effort.get("confidence_label") or "").lower()
    status = str(effort.get("status") or "").upper()
    # Reliable LOW: available + not UNKNOWN, confidence medium/high or unset (legacy fixtures)
    reliable_low = bool(effort.get("reliable_for_preserve")) or (
        level == "LOW"
        and status not in ("UNKNOWN", "UNAVAILABLE", "AMBIGUOUS")
        and conf in ("medium", "high", "")
        and not effort.get("hidden")
    )
    # Suspicious conflict: firm + disrupted + low effort → do not claim comfort strength
    contact = _contact(snap)
    reg = _reg(snap)
    suspicious = contact == "FIRM" and reg == "DISRUPTED" and level == "LOW"
    if reliable_low and not suspicious:
        out.append("LOW_EFFORT")
    if _stab_ok(snap) is True:
        out.append("STABILITY")
    if _breath(snap) == "LOW":
        out.append("LOW_BREATHINESS")
    if _reg(snap) == "CONNECTED":
        out.append("CONNECTED_REGISTER")
    return out


def _eval_rank(ev: dict[str, Any]) -> tuple[int, int, int]:
    gl = str(ev.get("guidance_level") or "").upper()
    st = str(ev.get("status") or "").upper()
    return (
        _GUIDANCE_RANK.get(gl, 4),
        _STATUS_RANK.get(st, 4),
        int(ev.get("_selection_index") or 99),
    )


def recommend_accessible_target(snap: dict[str, Any]) -> dict[str, Any]:
    """Low-risk style direction that does not fight current strengths.

    Not 'the objectively best timbre'. Never maps genre → acoustics.
    """
    known = 0
    if _effort(snap) not in ("UNKNOWN", ""):
        known += 1
    if _contact(snap) not in ("UNKNOWN", ""):
        known += 1
    if _reg(snap) not in ("UNKNOWN", ""):
        known += 1
    if _presence_bucket(snap) != "UNAVAILABLE":
        known += 1
    if _stab_ok(snap) is not None:
        known += 1
    weak = known < 2
    weak_reason = (
        "한 가지 방향을 추천하기보다는 현재 강점을 유지하며 여러 스타일을 짧게 비교해보는 것이 좋아요."
    )
    effort = _effort(snap)
    contact = _contact(snap)
    breath = _breath(snap)
    # Avoid pushing more density when already firm/high effort. Never pick DENSE_SOLID
    # just because the user wants density, and never pick AIRY when breath is already HIGH.
    if effort in ("HIGH", "MODERATE") or contact == "FIRM":
        opt = option_for("SOFT_SWEET") or {}
        return {
            "id": "SOFT_SWEET",
            "label": opt.get("label") or "부드럽고 감미롭게",
            "source": "SYSTEM_RECOMMENDED",
            "reason": weak_reason if weak else "현재 힘·접촉을 더 키우지 않고 시도하기 좋은 방향",
            "weak": weak,
        }
    if breath == "HIGH":
        opt = option_for("SOFT_SWEET") or {}
        return {
            "id": "SOFT_SWEET",
            "label": opt.get("label") or "부드럽고 감미롭게",
            "source": "SYSTEM_RECOMMENDED",
            "reason": weak_reason if weak else "숨을 더 늘리기보다 매끄러운 표현부터 시도하기 좋은 방향",
            "weak": weak,
        }
    if _presence_bucket(snap) == "LOW":
        opt = option_for("WARM_FULL") or {}
        return {
            "id": "WARM_FULL",
            "label": opt.get("label") or "따뜻하고 풍성하게",
            "source": "SYSTEM_RECOMMENDED",
            "reason": weak_reason if weak else "힘을 더하지 않으면서 존재감을 탐색하기 좋은 방향",
            "weak": weak,
        }
    opt = option_for("LIGHT_CLEAR") or {}
    return {
        "id": "LIGHT_CLEAR",
        "label": opt.get("label") or "맑고 가볍게",
        "source": "SYSTEM_RECOMMENDED",
        "reason": weak_reason if weak else "현재 편안한 패턴을 유지하며 시도하기 좋은 방향",
        "weak": weak,
    }


def _desired_outcome(
    concerns: list[dict[str, Any]],
    timbre_goal: Optional[dict[str, Any]],
    snap: dict[str, Any],
) -> dict[str, Any]:
    if timbre_goal:
        tid = str(timbre_goal.get("id") or "")
        if tid == "RECOMMEND_FOR_ME":
            rec = recommend_accessible_target(snap)
            opt = option_for(rec["id"]) or {}
            return {
                "type": "TIMBRE",
                "id": rec["id"],
                "label": rec["label"],
                "description": opt.get("description") or "",
                "source": rec["source"],
                "recommendation_reason": rec.get("reason"),
            }
        opt = option_for(tid) or {}
        return {
            "type": "TIMBRE",
            "id": tid,
            "label": timbre_goal.get("label") or opt.get("label") or tid,
            "description": opt.get("description") or timbre_goal.get("description") or "",
            "source": timbre_goal.get("source") or "USER_SELECTED",
        }
    for c in concerns:
        cid = str(c.get("id") or "")
        if cid in HIGH_NOTE_DESIRED_OUTCOMES:
            d = HIGH_NOTE_DESIRED_OUTCOMES[cid]
            return {"type": "HIGH_NOTE", "id": d["id"], "label": d["label"], "source": "CONCERN_DEFAULT"}
    if concerns:
        cid = str(concerns[0].get("id") or "")
        label = str(concerns[0].get("label") or cid)
        return {"type": "CONCERN", "id": cid, "label": label, "source": "CONCERN_DEFAULT"}
    return {"type": "GENERAL", "id": "EXPLORE", "label": "현재 발성을 안전하게 탐색", "source": "DEFAULT"}


def _majority_actionable_focus(evs: list[dict[str, Any]]) -> Optional[str]:
    """If 2+ evidence-backed / concern-specific QAs share a focus, promote over STYLE.

    Generic MAINTAIN fallback votes do not count (prevents fake consensus).
    """
    from collections import Counter

    counts: Counter[str] = Counter()
    for ev in evs:
        focus = str(ev.get("primary_focus") or "").upper()
        if focus in ("", "MAINTAIN", "TIMBRE", "STYLE", "SAFETY"):
            continue
        # Prefer explicit flag; fall back to evidence/guidance heuristics
        if ev.get("counts_for_consensus") is False:
            continue
        if ev.get("counts_for_consensus") is True:
            counts[focus] += 1
            continue
        gl = str(ev.get("guidance_level") or "")
        mode = str(ev.get("response_mode") or ev.get("answer_mode") or "")
        has_ev = bool(ev.get("evidence_used") or ev.get("evidence"))
        if gl in ("CONTROLLED_CONFIRMED", "SONG_DIRECT", "SONG_COMPOSITE") and has_ev:
            counts[focus] += 1
        elif mode == "GUIDED_EXPERIMENT" and has_ev:
            counts[focus] += 1
        elif mode == "EVIDENCE_EXPLANATION" and has_ev:
            counts[focus] += 1
        # else: generic unknown fallback — do not vote
    if not counts:
        return None
    focus, n = counts.most_common(1)[0]
    return focus if n >= 2 else None


def _has_functional_limitation(evs: list[dict[str, Any]], snap: dict[str, Any]) -> bool:
    for ev in evs:
        focus = str(ev.get("primary_focus") or "")
        if focus in ("MAINTAIN", "TIMBRE", "STYLE", ""):
            continue
        gl = str(ev.get("guidance_level") or "")
        st = str(ev.get("status") or "")
        if gl == "SAFETY_ONLY" or st == "SAFETY_ONLY":
            return True
        if gl in ("CONTROLLED_CONFIRMED", "SONG_DIRECT", "SONG_COMPOSITE"):
            if st not in ("NOT_SUPPORTED", "NOT_SUPPORTED_IN_THIS_RECORDING"):
                return True
        if st in ("CONFIRMED", "PARTIALLY_SUPPORTED"):
            return True
    if _reg(snap) == "DISRUPTED":
        return True
    if _effort(snap) in ("HIGH", "MODERATE"):
        return True
    if _stab_ok(snap) is False:
        return True
    return False


def _pick_primary_evaluation(
    evaluations: list[dict[str, Any]],
    concerns: list[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    ranked = sorted(evaluations, key=_eval_rank)
    for ev in ranked:
        focus = str(ev.get("primary_focus") or "")
        gl = str(ev.get("guidance_level") or "")
        st = str(ev.get("status") or "")
        if gl == "SAFETY_ONLY" or st == "SAFETY_ONLY":
            return ev
        if st in ("NOT_SUPPORTED", "NOT_SUPPORTED_IN_THIS_RECORDING") and gl != "SONG_DIRECT":
            continue
        if focus and focus not in ("MAINTAIN",):
            return ev
        if gl in ("CONTROLLED_CONFIRMED", "SONG_DIRECT", "SONG_COMPOSITE"):
            return ev
    return ranked[0] if ranked else None


def _gap_text(desired: dict[str, Any], snap: dict[str, Any], focus: str) -> str:
    tid = str(desired.get("id") or "")
    effort = _effort(snap)
    reg = _reg(snap)
    pb = _presence_bucket(snap)
    bits: list[str] = []
    if effort in ("HIGH", "MODERATE"):
        bits.append("힘 사용이 큰 구간이 있어 음량부터 키우는 방향은 우선이 아니에요")
    if reg in ("DISRUPTED", "PARTIAL"):
        bits.append("음역이 올라갈 때 연결이 일정하지 않은 구간이 있어요")
    if pb == "LOW":
        bits.append("중역 존재감이 낮은 편이에요")
    lead = " ".join(bits) if bits else "현재 확보된 발성 특징을 기준으로"
    if tid in ("BRIGHT_CLEAR", "WARM_FULL", "DENSE_SOLID") and (effort in ("HIGH", "MODERATE") or reg in ("DISRUPTED", "PARTIAL")):
        return (
            f"{lead}. 더 선명하거나 밀도 있는 인상을 만들기 전에, "
            "음량과 힘을 더 늘리지 않고 전환 중에도 소리 존재감이 유지되는 패턴을 만드는 것이 우선이에요."
        )
    if tid == "AIRY_DELICATE" and _breath(snap) == "HIGH":
        return (
            "이미 숨 섞임이 큰 편이므로 숨을 더 늘리기보다, "
            "작은 강도에서 섬세한 표현이 불편 없이 이어지는지부터 확인하는 것이 좋아요."
        )
    if tid == "DENSE_SOLID" and _contact(snap) == "FIRM":
        return (
            "이미 단단한 접촉 특성이 있으므로 접촉을 더 키우지 않고, "
            "연결과 소리 존재감을 안정시키는 방향이 좋아요."
        )
    if focus == "STYLE":
        return (
            f"{lead} 큰 기능적 교정보다, "
            "음량을 키우지 않고 짧은 구절에서 목표 음색을 만드는 것이 적합해 보여요."
        )
    return f"{lead} 이 부분을 먼저 다루는 것이 목표 음색에 가까워지는 데 더 적합해 보여요."


def _goal_copy(
    desired: dict[str, Any],
    focus: str,
    snap: dict[str, Any],
    *,
    style: bool,
    safety: bool,
    concerns: Optional[list[dict[str, Any]]] = None,
) -> tuple[str, str]:
    if safety:
        return (
            "음색 변화보다 불편감이 가라앉는 것이 우선",
            "통증이나 지속 불편이 있을 때는 강한 고음·큰 소리·음색 탐색 연습을 하지 마세요.",
        )
    preserve = _preserve_factors(snap)
    keep_effort = "LOW_EFFORT" in preserve
    keep = "현재의 편안한 힘 사용은 유지하면서, " if keep_effort else ""
    label = desired.get("label") or "원하는 방향"
    concern_ids = {str(c.get("id") or "") for c in (concerns or [])}
    if "HIGH_NOTE_THINS" in concern_ids and desired.get("type") == "TIMBRE":
        title = f"{keep}고음으로 이동할 때도 소리의 밀도와 존재감을 유지하기"
        desc = "힘을 더 늘리지 않으면서, 음역이 올라갈 때 소리가 갑자기 얇아지지 않게 이어 보세요."
        return title, desc
    if style:
        tid = str(desired.get("id") or "").upper()
        style_titles = {
            "BRIGHT_CLEAR": "음량을 키우지 않고 더 밝고 선명한 소리 만들기",
            "DENSE_SOLID": "음량을 키우지 않고 더 단단하고 밀도 있는 소리 만들기",
            "SOFT_SWEET": "힘을 더 쓰지 않고 더 부드럽고 자연스럽게 구절 이어가기",
            "LIGHT_CLEAR": "음량을 키우지 않고 더 가볍고 맑은 소리 만들기",
            "WARM_FULL": "음량을 키우지 않고 더 따뜻하고 풍성한 소리 만들기",
            "AIRY_DELICATE": "힘을 더 쓰지 않고 더 섬세하게 이어가기",
            "INTENSE_DISTINCT": "음량을 키우지 않고 표현으로 선명도 높이기",
        }
        # Target-specific titles stay short; do not prepend planner-like keep prefix.
        title = style_titles.get(tid) or f"{label} 소리 만들기"
        style_descs = {
            "BRIGHT_CLEAR": (
                "짧은 구절에서 발음과 모음 연결을 조절해 선명함을 만든 뒤, "
                "실제 가사에 적용해보세요."
            ),
            "DENSE_SOLID": (
                "편한 중음에서 한 음을 1~2초 짧게 유지한 뒤, "
                "같은 강도로 짧은 구절에 적용해보세요."
            ),
            "SOFT_SWEET": (
                "작은~중간 강도에서 짧은 구절을 급하게 끊지 말고 "
                "같은 편안한 강도로 이어보세요."
            ),
        }
        desc = style_descs.get(
            tid,
            "짧은 구절에서 목표 음색을 만든 뒤, 실제 가사에 적용해보세요.",
        )
        return title, desc
    if focus == "REGISTER_CONNECTION":
        title = f"{keep}음역이 올라갈 때 끊기지 않는 연결 만들기"
        if desired.get("type") == "TIMBRE":
            desc = (
                f"연결을 안정시킨 뒤 '{label}' 표현을 짧게 만들어보는 것이 좋아요. "
                "립트릴·빨대 등으로 작은 강도로 음역을 이어 올리는 연습을 먼저 하세요."
            )
        else:
            desc = "편안한 중음에서 위쪽으로 작은 강도로 음역을 이어 올리기 3~5회를 먼저 하세요."
        return title, desc
    if focus == "EFFORT":
        title = "같은 음을 더 세게 밀지 않고 편안한 힘으로 유지하기"
        desc = "높은 음이나 강한 구간에 도달하려고 음량부터 키우지 않는 것이 핵심이에요."
        return title, desc
    if focus == "PRESENCE":
        title = f"{keep}음량을 키우지 않고 중음에서 소리 존재감 유지하기"
        desc = (
            "편한 중음에서 짧은 모음을 1~2초 유지한 뒤 "
            "같은 강도로 2~3음 연결하세요. 존재감을 위해 음량부터 키우지 마세요."
        )
        return title, desc
    if focus == "BRIGHTNESS":
        title = f"{keep}음량을 더 키우지 않고 더 밝고 선명한 음색 만들기"
        desc = (
            "먼저 짧은 구절의 발음과 모음 표현을 조절해 선명함을 만들고, "
            "그다음 실제 가사에 적용해보세요."
        )
        return title, desc
    if focus == "BREATHINESS":
        title = "숨이 먼저 새지 않게, 짧은 구간에서 표현을 유지하기"
        desc = "숨을 더 막거나 더 흘리기보다 짧은 지속에서 섞임이 과해지지 않게 하세요."
        return title, desc
    if focus == "STABILITY":
        title = f"{keep}짧은 음부터 흔들림 없이 유지하기"
        desc = "길게 버티기보다 1~2초 짧은 유지부터 만든 뒤 2~3초·3음 pattern으로 옮기세요."
        return title, desc
    if focus == "MAINTAIN":
        title = f"{keep}{label}"
        desc = (
            "현재 기능적 문제를 억지로 바꾸기보다 "
            "짧은 구절에서 목표 음색을 만드는 것이 우선이에요."
        )
        return title, desc
    title = f"{keep}지금 가장 관련 있는 패턴부터 짧은 구절로 다루기"
    return title, "작은 강도로 짧은 구간부터 구체 동작을 반복한 뒤 원곡에 적용하세요."


def _why_first(focus: str, snap: dict[str, Any], preserve: list[str]) -> str:
    parts: list[str] = []
    if "LOW_EFFORT" in preserve:
        parts.append("힘 사용은 낮은 편이라 더 세게 부르는 것이 현재 우선은 아니에요.")
    if "LOW_BREATHINESS" in preserve:
        parts.append("숨 섞임은 낮은 편이라 숨을 더 막는 것이 현재 우선은 아니에요.")
    if focus == "REGISTER_CONNECTION" and _reg(snap) in ("DISRUPTED", "PARTIAL"):
        parts.append(
            "반면 음역이 올라갈 때 연결이 급격하게 달라지는 구간이 있어 "
            "이 부분을 먼저 안정시키는 것이 더 적합해 보여요."
        )
    elif focus == "EFFORT" and _effort(snap) in ("HIGH", "MODERATE"):
        parts.append("힘 사용이 큰 구간이 있어 이 패턴을 먼저 다루는 것이 좋아요.")
    elif focus == "BRIGHTNESS" or (
        focus in ("STYLE", "TIMBRE") and _brightness_bucket(snap) == "LOW"
    ):
        if "LOW_EFFORT" in preserve or "LOW_BREATHINESS" in preserve:
            parts.append("힘을 더 쓰거나 숨을 더 막을 필요는 없어 보여요.")
        if _presence_bucket(snap) == "HIGH":
            parts.append(
                "현재 소리 존재감은 유지되는 편이라, 이를 크게 바꾸기보다 "
                "발음과 모음 표현으로 선명함을 더하는 것을 먼저 해보는 게 좋아요."
            )
        parts.append(
            "밝기가 어두운 쪽으로 나타났기 때문에 "
            "음량을 키우기보다 발음·모음 표현으로 선명도를 만드는 것을 먼저 시도하는 게 우선이에요."
        )
    elif focus == "PRESENCE" and _presence_bucket(snap) == "LOW":
        parts.append(
            "중역 존재감이 낮은 편이라 "
            "음량을 키우기보다 짧은 모음 유지로 존재감을 먼저 다루는 게 우선이에요."
        )
    elif focus == "STYLE":
        pb = _presence_bucket(snap)
        if "LOW_EFFORT" in preserve or "LOW_BREATHINESS" in preserve:
            parts.append(
                "힘을 더 쓰거나 숨을 더 막을 필요는 없어 보여요. "
                + (
                    "현재 소리 존재감은 유지되는 편이라, 이를 크게 바꾸기보다 "
                    if pb == "HIGH"
                    else ""
                )
                + "발음과 모음 표현으로 목표 음색을 만드는 것을 먼저 해보는 게 좋아요."
            )
        else:
            parts.append(
                "뚜렷한 기능적 제한을 억지로 만들기보다, "
                "짧은 구절에서 목표 음색을 만드는 것이 우선이에요."
            )
    elif focus == "SAFETY":
        parts.append("불편감이 있을 때는 연습보다 휴식이 우선이에요.")
    if not parts:
        parts.append("현재 분석에서 이 축이 질문·목표와 가장 직접 관련되어 보여요.")
    return " ".join(parts)


def _style_practice_id(target_id: str) -> str:
    mapping = {
        "DENSE_SOLID": "STYLE_DENSE_SOLID",
        "BRIGHT_CLEAR": "STYLE_BRIGHT_CLEAR",
        "SOFT_SWEET": "STYLE_SOFT_SWEET",
        "LIGHT_CLEAR": "STYLE_LIGHT_CLEAR",
        "WARM_FULL": "STYLE_WARM_FULL",
        "AIRY_DELICATE": "STYLE_AIRY_DELICATE",
        "INTENSE_DISTINCT": "STYLE_INTENSE_DISTINCT",
    }
    return mapping.get(target_id, "STYLE_SOFT_SWEET")


def _pack_axis(
    *,
    available: bool,
    status: Any,
    continuum: Any,
    confidence: str = "medium",
    source_scope: str = "SONG",
) -> dict[str, Any]:
    return {
        "available": bool(available),
        "status": status,
        "continuum": continuum,
        "confidence": confidence,
        "source_scope": source_scope,
    }


def _current_state(snap: dict[str, Any]) -> dict[str, Any]:
    effort = snap.get("effort") or {}
    contact = snap.get("contact") or {}
    breath = snap.get("breathiness") or {}
    register = snap.get("register") or {}
    stab = snap.get("stability") or {}
    timbre = snap.get("timbre") or {}
    hn = snap.get("high_note") or {}
    presence = timbre.get("presence")
    brightness = timbre.get("brightness")
    airiness = timbre.get("airiness")
    return {
        "effort": _pack_axis(
            available=bool(effort.get("available")),
            status=effort.get("level") or effort.get("status"),
            continuum=None,
        ),
        "contact": _pack_axis(
            available=bool(contact.get("available")),
            status=contact.get("status"),
            continuum=contact.get("continuum"),
        ),
        "functional_breathiness": _pack_axis(
            available=bool(breath.get("available")),
            status=breath.get("level") or breath.get("status"),
            continuum=breath.get("airiness_continuum"),
        ),
        "register": _pack_axis(
            available=bool(register.get("available")),
            status=register.get("status"),
            continuum=None,
        ),
        "stability": _pack_axis(
            available=bool(stab.get("available")),
            status=stab.get("status"),
            continuum=None,
        ),
        "presence": _pack_axis(
            available=presence is not None,
            status=_presence_bucket(snap) if presence is not None else "UNAVAILABLE",
            continuum=presence,
        ),
        "brightness": _pack_axis(
            available=brightness is not None,
            status=_brightness_bucket(snap) if brightness is not None else "UNAVAILABLE",
            continuum=brightness,
        ),
        "timbre_airiness": _pack_axis(
            available=airiness is not None,
            status=None,
            continuum=airiness,
        ),
        "texture": _pack_axis(
            available=timbre.get("texture") is not None,
            status=None,
            continuum=timbre.get("texture"),
        ),
        "source_balance": _pack_axis(
            available=bool((register.get("head_chest") or {})),
            status=None,
            continuum=None,
        ),
        "high_note": _pack_axis(
            available=bool(hn.get("available")),
            status=hn.get("reason"),
            continuum=None,
        ),
        "dynamic_response": _pack_axis(available=False, status="UNAVAILABLE", continuum=None),
        "vibrato": _pack_axis(available=False, status="UNAVAILABLE", continuum=None),
    }


def plan_coaching_goal(
    *,
    user_concerns: list[dict[str, Any]] | None,
    timbre_goal: dict[str, Any] | None = None,
    concern_evaluations: list[dict[str, Any]] | None = None,
    song_profile: dict[str, Any] | None = None,
    pain: bool = False,
) -> dict[str, Any]:
    concerns = list(user_concerns or [])
    evs = [dict(ev) for ev in (concern_evaluations or [])]
    for i, ev in enumerate(evs):
        ev["_selection_index"] = i
        cid = str(ev.get("concern_id") or ev.get("concern") or "")
        for j, c in enumerate(concerns):
            if str(c.get("id") or "") == cid:
                ev["_selection_index"] = j
                break
    snap = get_canonical_snapshot(song_profile)
    desired = _desired_outcome(concerns, timbre_goal, snap)
    preserve = _preserve_factors(snap)
    current = _current_state(snap)

    if pain:
        practices = [practice_for_focus("SAFETY") or {}]
        protocol = build_coaching_protocol(
            "SAFETY",
            snap=snap,
            pain=True,
            why_this_first="통증·지속 불편에서는 연습보다 휴식이 우선이에요.",
            preserve_factors=preserve,
        )
        return {
            "version": GOAL_VERSION,
            "desired_outcome": desired,
            "current_state": current,
            "current_summary": "불편감이 있어 음색·고음 탐색보다 안전이 우선이에요.",
            "goal_title": "음색 변화보다 불편감이 가라앉는 것이 우선",
            "goal_description": "강한 고음·큰 소리·적극적인 음색 연습을 중단하고 짧게 쉬세요.",
            "primary_focus": "SAFETY",
            "primary_focus_label": FOCUS_LABELS["SAFETY"],
            "why_this_first": "통증·지속 불편에서는 연습보다 휴식이 우선이에요.",
            "supporting_factors": [],
            "preserve_factors": preserve,
            "preserve_labels": [PRESERVE_LABELS[p] for p in preserve if p in PRESERVE_LABELS],
            "practice_ids": ["SAFETY_STOP"],
            "practices": [p for p in practices if p],
            "mode": "SAFETY",
            "gap_interpretation": "목표 음색보다 현재 불편감을 줄이는 것이 먼저예요.",
            "evidence_used": [{"axis": "safety", "status": "FLAGGED", "scope": "USER_REPORTED"}],
            "coaching_protocol": protocol,
        }

    primary_ev = _pick_primary_evaluation(evs, concerns)
    functional = _has_functional_limitation(evs, snap)
    convergent = _majority_actionable_focus(evs)
    effort_elevated = _effort(snap) in ("HIGH", "MODERATE")
    # Strong register disruption overrides aesthetic STYLE exploration
    if _reg(snap) == "DISRUPTED":
        functional = True
    # Reliable elevated effort is a functional limitation — never STYLE-only
    if effort_elevated:
        functional = True
    # 2+ QAs converging on the same bottleneck beats STYLE exploration.
    if convergent:
        functional = True
    style = bool(desired.get("type") == "TIMBRE") and not functional

    if primary_ev and not style:
        focus = str(primary_ev.get("primary_focus") or "MAINTAIN")
        supporting = list(primary_ev.get("secondary_factors") or [])[:2]
        # DENSE_SOLID must not force firmer contact
        if desired.get("id") == "DENSE_SOLID" and focus == "CONTACT" and _contact(snap) == "FIRM":
            focus = "REGISTER_CONNECTION" if _reg(snap) in ("PARTIAL", "DISRUPTED") else "PRESENCE"
        if desired.get("id") == "AIRY_DELICATE" and focus == "BREATHINESS" and _breath(snap) == "HIGH":
            focus = "PRESENCE" if _presence_bucket(snap) == "LOW" else "MAINTAIN"
        if desired.get("id") == "SOFT_SWEET" and focus == "CONTACT" and _contact(snap) == "FIRM":
            focus = "EFFORT" if effort_elevated else "PRESENCE"
        mode = "GUIDE"
        if str(primary_ev.get("guidance_level")) == "CONTROLLED_CONFIRMED":
            mode = "CORRECT"
        elif str(primary_ev.get("status")) == "PARTIALLY_SUPPORTED":
            mode = "REFINE"
        if focus == "MAINTAIN" and desired.get("type") == "TIMBRE" and not effort_elevated:
            style = True
            focus = "STYLE"
            mode = "STYLE"
        elif focus == "MAINTAIN" and not functional:
            style = bool(desired.get("type") == "TIMBRE")
            if style:
                focus = "STYLE"
                mode = "STYLE"
    elif style:
        focus = "STYLE"
        supporting = []
        mode = "STYLE"
        primary_ev = None
    else:
        focus = str((primary_ev or {}).get("primary_focus") or "MAINTAIN")
        supporting = []
        mode = "GUIDE"

    if convergent and (style or focus in ("STYLE", "MAINTAIN", "TIMBRE")):
        style = False
        focus = convergent
        mode = "GUIDE"
        # Prefer an evaluation that already carries this focus
        for ev in evs:
            if str(ev.get("primary_focus") or "").upper() == convergent:
                primary_ev = ev
                break

    # Strong register disruption precedes aesthetic / presence-only goals
    if _reg(snap) == "DISRUPTED" and focus in (
        "STYLE",
        "TIMBRE",
        "MAINTAIN",
        "PRESENCE",
        "BRIGHTNESS",
        "CONTACT",
    ):
        style = False
        focus = "REGISTER_CONNECTION"
        mode = "GUIDE"

    # Functional high-note / register concerns beat target STYLE/TIMBRE (general priority)
    _FUNCTIONAL_HN = frozenset(
        {
            "HIGH_NOTE_FLIPS",
            "HIGH_NOTE_CANNOT_REACH",
            "HIGH_NOTE_TOO_EFFORTFUL",
            "HIGH_NOTE_UNSTABLE",
            "REGISTER_CONNECTION_DIFFICULT",
        }
    )
    concern_id_set = {str(c.get("id") or "") for c in concerns}
    if concern_id_set & _FUNCTIONAL_HN and focus in (
        "STYLE",
        "TIMBRE",
        "MAINTAIN",
        "BRIGHTNESS",
    ):
        picked = None
        for ev in evs:
            cid = str(ev.get("concern_id") or ev.get("concern") or "")
            if cid not in _FUNCTIONAL_HN:
                continue
            pf = str(ev.get("primary_focus") or "").upper()
            if pf and pf not in ("STYLE", "TIMBRE", "MAINTAIN", ""):
                picked = ev
                break
        if picked:
            style = False
            focus = str(picked.get("primary_focus") or "REGISTER_CONNECTION")
            primary_ev = picked
            mode = "GUIDE"
        elif _reg(snap) in ("DISRUPTED", "PARTIAL"):
            style = False
            focus = "REGISTER_CONNECTION"
            mode = "GUIDE"
        elif _effort(snap) in ("HIGH", "MODERATE"):
            style = False
            focus = "EFFORT"
            mode = "GUIDE"
        else:
            # Still prefer high-note access over aesthetic target when flips/cannot-reach present
            if concern_id_set & {"HIGH_NOTE_FLIPS", "HIGH_NOTE_CANNOT_REACH", "REGISTER_CONNECTION_DIFFICULT"}:
                style = False
                focus = "HIGH_NOTE" if "HIGH_NOTE_CANNOT_REACH" in concern_id_set else "REGISTER_CONNECTION"
                mode = "GUIDE"

    # Coherence lock: HIGH/MODERATE effort cannot yield STYLE-only / TIMBRE primary
    if effort_elevated and focus in ("STYLE", "TIMBRE", "MAINTAIN", "BRIGHTNESS"):
        style = False
        focus = "EFFORT"
        mode = "GUIDE"

    # Brightness-dark + BRIGHT_CLEAR: prefer BRIGHTNESS over vague STYLE exploration
    if (
        not effort_elevated
        and _brightness_bucket(snap) == "LOW"
        and str(desired.get("id") or "").upper() in ("BRIGHT_CLEAR", "LIGHT_CLEAR")
        and focus in ("STYLE", "TIMBRE", "MAINTAIN", "BRIGHTNESS")
        and _reg(snap) != "DISRUPTED"
    ):
        style = False
        focus = "BRIGHTNESS"
        mode = "GUIDE"

    if style and not effort_elevated:
        focus = "STYLE"
        mode = "STYLE"
    elif style and effort_elevated:
        style = False
        focus = "EFFORT"
        mode = "GUIDE"

    title, desc = _goal_copy(
        desired, focus, snap, style=style, safety=False, concerns=concerns
    )
    gap = _gap_text(desired, snap, focus)
    why = _why_first(focus, snap, preserve)

    if focus == "STYLE":
        pid = _style_practice_id(str(desired.get("id") or "SOFT_SWEET"))
        practice = practice_for_focus(pid, category="timbre") or practice_for_focus("STYLE")
        pids = [pid]
    elif focus == "BRIGHTNESS":
        # Focus/practice coherence: BRIGHTNESS must not emit PRESENCE practice
        tid = str(desired.get("id") or "BRIGHT_CLEAR")
        pid = _style_practice_id(tid if tid else "BRIGHT_CLEAR")
        if "BRIGHT" not in pid and "CLEAR" not in pid and "LIGHT" not in pid:
            pid = "STYLE_BRIGHT_CLEAR"
        practice = practice_for_focus(pid, category="timbre") or practice_for_focus("BRIGHTNESS")
        pids = [pid if practice else "STYLE_BRIGHT_CLEAR"]
    else:
        cat = str(semantics_for(str((primary_ev or {}).get("concern_id") or "")).get("category") or "")
        practice = practice_for_focus(focus, category=cat)
        pids = [practice.get("practice_id")] if practice else []
        # Never fall back to STYLE-only when effort is elevated
        if not practice and desired.get("type") == "TIMBRE" and not effort_elevated:
            pid = _style_practice_id(str(desired.get("id") or "SOFT_SWEET"))
            practice = practice_for_focus(pid, category="timbre")
            pids = [pid] if practice else []
            focus = "STYLE"
            mode = "STYLE"
            title, desc = _goal_copy(
                desired, focus, snap, style=True, safety=False, concerns=concerns
            )
        elif not practice and effort_elevated:
            practice = practice_for_focus("EFFORT") or practice_for_focus("REGISTER_CONNECTION")
            pids = [practice.get("practice_id")] if practice else ["EFFORT_EASY_RANGE"]
            focus = "EFFORT"
            mode = "GUIDE"
            title, desc = _goal_copy(
                desired, focus, snap, style=False, safety=False, concerns=concerns
            )

    # Hard coherence: BRIGHTNESS heading cannot ship PRESENCE main practice
    if focus == "BRIGHTNESS" and practice:
        pt = str(practice.get("title") or "") + str(practice.get("practice_id") or "")
        if "PRESENCE" in pt.upper() or "존재감" in pt:
            practice = practice_for_focus("STYLE_BRIGHT_CLEAR") or practice
            pids = ["STYLE_BRIGHT_CLEAR"]

    evidence_used = []
    if primary_ev:
        for item in (primary_ev.get("functional_hypothesis") or {}).get("evidence_used") or []:
            evidence_used.append(item)
        if not evidence_used:
            for axis in ("effort", "register", "presence", "breathiness"):
                evidence_used.append({"axis": axis, "status": "USED", "scope": "SONG"})

    concern_ids = [
        str(c.get("id") or "")
        for c in concerns
        if c.get("id")
    ]
    if primary_ev and (primary_ev.get("concern_id") or primary_ev.get("concern")):
        cid0 = str(primary_ev.get("concern_id") or primary_ev.get("concern"))
        if cid0 and cid0 not in concern_ids:
            concern_ids.insert(0, cid0)

    # Soften comfort copy when firm+disrupted+unreliable low effort
    if (
        _contact(snap) == "FIRM"
        and _reg(snap) == "DISRUPTED"
        and _effort(snap) == "LOW"
        and "LOW_EFFORT" not in preserve
        and focus == "REGISTER_CONNECTION"
    ):
        why = (
            "현재 분석에서 전반적인 힘 증가가 강하게 잡히지는 않았지만, "
            "음역 연결을 먼저 안정시키는 것이 우선이에요."
        )

    protocol = build_coaching_protocol(
        focus,
        snap=snap,
        concern_ids=concern_ids,
        target_timbre=desired if desired.get("type") == "TIMBRE" else None,
        pain=False,
        why_this_first=why,
        preserve_factors=preserve,
    )

    # Target timbre stays secondary when a functional bottleneck owns primary focus
    secondary_target = None
    if desired.get("type") == "TIMBRE" and focus not in ("STYLE", "TIMBRE"):
        secondary_target = {
            "id": desired.get("id"),
            "label": desired.get("label") or STYLE_TARGET_LABELS.get(str(desired.get("id") or "").upper()),
            "type": "TIMBRE",
        }
        tid = str(desired.get("id") or "").upper()
        if tid and tid not in [str(s).upper() for s in supporting]:
            supporting = list(supporting) + [tid]

    return {
        "version": GOAL_VERSION,
        "desired_outcome": desired,
        "current_state": current,
        "current_summary": gap,
        "goal_title": title,
        "goal_description": desc,
        "primary_focus": focus,
        "primary_focus_label": (
            STYLE_TARGET_LABELS.get(str(desired.get("id") or "").upper())
            if focus == "STYLE"
            else FOCUS_LABELS.get(focus, focus)
        ),
        "why_this_first": why,
        "supporting_factors": supporting,
        "secondary_target": secondary_target,
        "preserve_factors": preserve,
        "preserve_labels": [PRESERVE_LABELS[p] for p in preserve if p in PRESERVE_LABELS],
        "practice_ids": [p for p in pids if p],
        "practices": [practice] if practice else [],
        "mode": mode,
        "gap_interpretation": gap,
        "evidence_used": evidence_used[:6],
        "source_concern_id": (primary_ev or {}).get("concern_id") or (primary_ev or {}).get("concern"),
        "coaching_protocol": protocol,
    }
