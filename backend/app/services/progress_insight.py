# -*- coding: utf-8 -*-
"""Progress Insight presentation — CHANGE vs IMPROVEMENT, count-based 'how much' (no fake %)."""

from __future__ import annotations

from typing import Any, Optional

from backend.app.services.personal_vocal_baseline import (
    DESCRIPTIVE_AXES,
    compare_progress,
)

AXIS_TITLE_KO = {
    "register_connection": "성구 연결",
    "effort": "힘 사용",
    "contact": "접촉감",
    "breathiness": "숨 섞임",
    "stability": "발성 안정성",
    "brightness": "밝기",
    "source_balance": "흉성·두성 음향 성향",
    "presence": "중역 존재감",
}

AXIS_USER_LABEL = {
    "CONNECTED": "자연스럽게 연결되는 편",
    "PARTIAL": "일부 구간만 연결되는 편",
    "DISRUPTED": "연결이 끊기는 구간이 있는 편",
    "UNRESOLVED": "이번에는 연결 상태를 판단하기 어려워요",
    "LOW": "낮은 편",
    "MODERATE": "중간 정도",
    "HIGH": "높은 편",
    "STABLE": "안정적인 편",
    "UNSTABLE": "흔들림이 있는 편",
    "FIRM": "단단한 편",
    "LIGHT": "가벼운 편",
    "AMBIGUOUS": "구간에 따라 다른 편",
    "MID": "중간 편",
    "UNKNOWN": "이번에는 확인이 어려워요",
    "UNAVAILABLE": "이번엔 확인이 어려워요",
    "CHEST_LEANING": "흉성 쪽",
    "CHEST_DOMINANT": "흉성 쪽 성향이 강한 편",
    "HEAD_LEANING": "두성 쪽",
    "HEAD_DOMINANT": "두성 쪽 성향이 강한 편",
    "BALANCED": "균형적인 편",
    "BALANCED_ACOUSTIC": "균형적인 편",
    "CONFLICTED": "구간마다 다른 편",
}

AXIS_CHIP_KO = {
    "CONNECTED": "연결",
    "PARTIAL": "일부",
    "DISRUPTED": "끊김",
    "STABLE": "안정",
    "UNSTABLE": "흔들림",
    "FIRM": "단단함",
    "MID": "중간",
    "LIGHT": "가벼움",
    "LOW": "낮음",
    "MODERATE": "보통",
    "HIGH": "높음",
}


def _user_label(raw: Any) -> str:
    s = str(raw or "")
    return AXIS_USER_LABEL.get(s, s)


def _chip(raw: Any) -> str:
    s = str(raw or "")
    return AXIS_CHIP_KO.get(s, _user_label(s)[:4])


def _recent_window_label(actual: int, requested: int = 5) -> str:
    if actual <= 0:
        return "이전 기록"
    if actual == 1:
        return "이전 기록"
    if actual < requested:
        return f"최근 {actual}회"
    return f"최근 {requested}회"


def _how_much_summary(actual: int, hits: int, requested: int = 5) -> str:
    if actual <= 0:
        return "비교할 이전 기록이 아직 없어요."
    if actual == 1:
        return (
            "이전 기록에서도 안정적인 편이었어요."
            if hits > 0
            else "이전 기록과 비교해 보면 아직 안정적으로 보이진 않았어요."
        )
    return f"{_recent_window_label(actual, requested)} 중 안정적인 결과 {hits}회"


def _change_copy(axis: str, previous: str, current: str) -> str:
    prev_l = _user_label(previous)
    cur_l = _user_label(current)
    if axis == "effort":
        order = {"LOW": 0, "MODERATE": 1, "HIGH": 2}
        a, b = order.get(str(previous)), order.get(str(current))
        if a is not None and b is not None and b < a:
            return "이전 기록보다 힘을 덜 쓰는 쪽으로 나타났어요."
        if a is not None and b is not None and b > a:
            return "이전 기록보다 힘이 더 들어가는 쪽으로 나타났어요."
        return f"힘 사용이 {prev_l}에서 {cur_l}으로 나타났어요."
    if axis == "contact":
        return f"접촉감이 {prev_l.replace(' 편', '')} 쪽에서 {cur_l}으로 바뀌었어요."
    if axis == "brightness":
        return f"이전보다 {cur_l.replace(' 편', '')} 쪽으로 이동했어요."
    if axis == "source_balance":
        return f"이번에는 이전보다 {cur_l} 음향 성향이 더 나타났어요."
    if axis == "register_connection":
        return f"이전보다 성구가 {cur_l}으로 나타났어요."
    if axis == "stability":
        return f"발성 안정성이 {prev_l}에서 {cur_l}으로 나타났어요."
    if axis == "breathiness":
        return f"숨 섞임이 {prev_l}에서 {cur_l}으로 나타났어요."
    title = AXIS_TITLE_KO.get(axis, axis)
    return f"이전에는 {prev_l}이었고, 이번에는 {cur_l}으로 나타났어요. ({title})"


def _maintained_copy(axis: str, current: str) -> str:
    cur = _user_label(current)
    if axis == "effort":
        return "최근 기록과 비슷하게 힘을 쓰는 편이에요."
    if axis == "stability":
        return "최근 기록과 비슷하게 안정적인 편이에요."
    if axis == "register_connection":
        return "최근 기록과 비슷한 성구 연결 상태예요."
    return f"최근 기록과 비슷하게 {cur}이에요."


def _count_in_window(snaps: list[dict[str, Any]], axis: str, target: str) -> int:
    n = 0
    for s in snaps:
        can = s.get("canonical_json") or s.get("canonical") or {}
        val = can.get(axis)
        if isinstance(val, dict):
            val = val.get("label") or val.get("status")
        if str(val) == str(target):
            n += 1
    return n


def _sequence(snaps: list[dict[str, Any]], axis: str) -> list[dict[str, str]]:
    out = []
    for s in snaps:
        can = s.get("canonical_json") or {}
        val = can.get(axis)
        if isinstance(val, dict):
            val = val.get("label") or val.get("status")
        raw = str(val or "UNKNOWN")
        out.append({"raw": raw, "label": _user_label(raw), "chip": _chip(raw)})
    return out


def build_progress_insight(
    *,
    current_canonical: dict[str, Any],
    historical_snapshots: list[dict[str, Any]],
    goal: Optional[Any] = None,
    recent_n: int = 5,
    today_highlights: Optional[list[dict[str, str]]] = None,
    goal_progress: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    User-facing Progress Insight payload.
    Never invents percentage improvements for categorical axes.
    """
    from backend.app.services.goal_progress import build_goal_progress

    gp = goal_progress
    if gp is None and goal is not None:
        gp = build_goal_progress(
            goal=goal,
            historical_snapshots=historical_snapshots,
            current_canonical=current_canonical,
            recent_n=recent_n,
            include_current_in_recent=False,
        )

    if not historical_snapshots:
        return {
            "status": "NO_BASELINE",
            "today": today_highlights or [],
            "improved": [],
            "changed": [],
            "maintained": [],
            "practice_hint": None,
            "insight_available": False,
            "history_count": 0,
            "goal_progress": gp or {"status": "NO_GOAL", "uses_fake_percent": False},
        }

    recent = historical_snapshots[-recent_n:]
    actual_window = len(recent)
    older = (
        historical_snapshots[-(actual_window * 2) : -actual_window]
        if len(historical_snapshots) > actual_window
        else []
    )
    compared = compare_progress(
        current_canonical=current_canonical,
        historical_snapshots=historical_snapshots,
        goal=goal,
        recent_n=recent_n,
    )

    improved: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []
    maintained: list[dict[str, Any]] = []

    for row in compared.get("comparisons") or []:
        axis = row["axis"]
        title = AXIS_TITLE_KO.get(axis, axis)
        current = str(row.get("current"))
        modal = str(row.get("historical_modal") or "")
        dist = row.get("historical_distribution") or {}
        improvement = row.get("improvement")
        change = row.get("change")

        target_for_count = None
        if axis == "register_connection":
            target_for_count = "CONNECTED"
        elif axis == "stability":
            target_for_count = "STABLE"

        how_much = None
        if target_for_count:
            prev_n = _count_in_window(older, axis, target_for_count) if older else 0
            recent_n_count = _count_in_window(recent, axis, target_for_count)
            how_much = {
                "type": "COUNT_IN_WINDOW",
                "window": actual_window,
                "actual_count": actual_window,
                "label": "안정적으로 나타난 기록",
                "previous_count": prev_n if older else recent_n_count,
                "recent_count": recent_n_count,
                "current_counts_as_hit": current == target_for_count,
                "summary": _how_much_summary(actual_window, recent_n_count, recent_n),
            }

        card = {
            "axis": axis,
            "title": title,
            "current_raw": current,
            "current_label": _user_label(current),
            "baseline_modal_raw": modal,
            "baseline_modal_label": _user_label(modal),
            "historical_distribution": dist,
            "recent_sequence": _sequence(recent, axis),
            "how_much": how_much,
            "interpretation": row.get("interpretation"),
            "kind": None,
            "headline": None,
            "detail": None,
            "why_improvement": None,
        }

        if improvement is True:
            card["kind"] = "IMPROVED"
            card["headline"] = "목표 방향으로 좋아지고 있어요"
            if axis == "register_connection":
                card["detail"] = "이전보다 성구가 자연스럽게 이어지는 쪽으로 나타났어요."
                card["why_improvement"] = "현재 목표인 성구 연결 안정화 방향과 일치하는 변화예요."
            else:
                card["detail"] = "목표 방향과 맞는 변화예요."
                card["why_improvement"] = "등록된 목표 방향과 일치해요."
            improved.append(card)
        elif change == "UNCHANGED":
            card["kind"] = "MAINTAINED"
            card["headline"] = "잘 유지하고 있어요"
            card["detail"] = _maintained_copy(axis, current)
            maintained.append(card)
        elif axis in DESCRIPTIVE_AXES or axis in (
            "brightness",
            "source_balance",
            "timbre",
            "effort",
            "contact",
            "breathiness",
        ):
            card["kind"] = "CHANGED"
            card["headline"] = "달라진 부분"
            card["detail"] = _change_copy(axis, modal, current)
            card["why_improvement"] = None
            changed.append(card)
        elif improvement is False:
            card["kind"] = "NEEDS_PRACTICE"
            card["headline"] = "조금 더 연습할 부분"
            card["detail"] = "최근보다 목표와 멀어진 편이에요."
            changed.append(card)
        else:
            card["kind"] = "CHANGED"
            card["headline"] = "달라진 부분"
            card["detail"] = _change_copy(axis, modal, current)
            changed.append(card)

    improved = improved[:1]
    changed = changed[:1]
    maintained = maintained[:1]

    today = today_highlights or []
    if not today:
        for axis in ("register_connection", "effort", "contact", "stability"):
            if axis in current_canonical:
                today.append(
                    {
                        "axis": axis,
                        "title": AXIS_TITLE_KO.get(axis, axis),
                        "label": _user_label(current_canonical.get(axis)),
                    }
                )
            if len(today) >= 3:
                break

    return {
        "status": compared.get("status") or "AVAILABLE",
        "insight_available": True,
        "history_count": compared.get("history_count", 0),
        "goal_aware": compared.get("goal_aware", False) or bool(goal),
        "today": today[:3],
        "improved": improved,
        "changed": changed,
        "maintained": maintained,
        "practice_hint": None,
        "comparability": (compared.get("baseline_recent") or {}).get("comparability"),
        "goal_progress": gp,
        "note": None,
    }
