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
    "source_balance": "소스 밸런스",
    "presence": "중역 존재감",
}

AXIS_USER_LABEL = {
    "CONNECTED": "자연스럽게 연결되는 편",
    "PARTIAL": "일부 구간만 연결되는 편",
    "DISRUPTED": "연결이 끊기는 구간이 있는 편",
    "UNRESOLVED": "판단이 어려운 편",
    "LOW": "낮은 편",
    "MODERATE": "보통",
    "HIGH": "높은 편",
    "STABLE": "안정적인 편",
    "UNSTABLE": "흔들림이 있는 편",
    "FIRM": "단단한 편",
    "LIGHT": "가벼운 편",
    "AMBIGUOUS": "애매한 편",
    "MID": "중간 편",
    "UNKNOWN": "확인이 어려운 편",
    "UNAVAILABLE": "이번엔 확인이 어려워요",
}


def _user_label(raw: Any) -> str:
    s = str(raw or "")
    return AXIS_USER_LABEL.get(s, s)


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
        out.append({"raw": raw, "label": _user_label(raw)})
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
            "goal_progress": gp or {"status": "NO_GOAL", "uses_fake_percent": False},
        }

    recent = historical_snapshots[-recent_n:]
    older = historical_snapshots[-(recent_n * 2) : -recent_n] if len(historical_snapshots) > recent_n else []
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

        # Count-based "how much" for categorical axes
        target_for_count = None
        if axis == "register_connection":
            target_for_count = "CONNECTED"
        elif axis == "stability":
            target_for_count = "STABLE"

        how_much = None
        if target_for_count:
            prev_window = older if older else recent
            prev_n = _count_in_window(prev_window, axis, target_for_count)
            # recent including interpreting trend: count in recent historical only
            recent_n_count = _count_in_window(recent, axis, target_for_count)
            how_much = {
                "type": "COUNT_IN_WINDOW",
                "window": recent_n,
                "label": "안정적으로 나타난 기록",
                "previous_count": prev_n if older else recent_n_count,
                "recent_count": recent_n_count,
                "current_counts_as_hit": current == target_for_count,
                "summary": (
                    f"최근 {recent_n}회 중 안정적인 결과 {recent_n_count}회"
                    + (f" · 이전 {len(prev_window)}회 중 {prev_n}회" if older else "")
                ),
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
            card["headline"] = "목표 방향으로 개선되고 있어요"
            if axis == "register_connection":
                card["detail"] = "최근 녹음보다 안정적으로 이어지는 구간이 늘었어요"
                card["why_improvement"] = "현재 목표가 성구 연결 안정화 방향과 일치하는 변화입니다."
            else:
                card["detail"] = row.get("interpretation") or "목표 방향과 맞는 변화예요"
                card["why_improvement"] = "등록된 목표 방향과 일치합니다."
            improved.append(card)
        elif change == "UNCHANGED":
            card["kind"] = "MAINTAINED"
            card["headline"] = "잘 유지하고 있어요"
            card["detail"] = "최근 개인 범위와 비슷해요"
            maintained.append(card)
        elif axis in DESCRIPTIVE_AXES or axis in ("brightness", "source_balance", "timbre", "effort", "contact", "breathiness"):
            card["kind"] = "CHANGED"
            card["headline"] = "달라진 부분"
            if axis == "brightness":
                card["detail"] = f"최근보다 {_user_label(current)}으로 이동했어요"
            elif axis == "source_balance":
                card["detail"] = f"소스 밸런스가 {_user_label(current)} 쪽으로 변화했어요"
            elif axis == "effort":
                card["detail"] = f"힘 사용이 {_user_label(current)}으로 나타났어요"
            else:
                card["detail"] = f"{title}이(가) {_user_label(current)}으로 변화했어요"
            # never call descriptive change an improvement
            card["why_improvement"] = None
            changed.append(card)
        elif improvement is False:
            card["kind"] = "NEEDS_PRACTICE"
            card["headline"] = "조금 더 연습할 부분"
            card["detail"] = row.get("interpretation") or "최근보다 목표와 멀어진 편이에요"
            changed.append(card)  # show under changed/practice, not improved
        else:
            card["kind"] = "CHANGED"
            card["headline"] = "달라진 부분"
            card["detail"] = row.get("interpretation") or f"{title}이(가) 달라졌어요"
            changed.append(card)

    # Cap cards for main surface
    improved = improved[:2]
    changed = changed[:2]
    maintained = maintained[:2]

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
        "note": "개선은 목표 방향과 맞을 때만 표시합니다. 밝기·밸런스 변화는 개선으로 부르지 않습니다. 목표 진행은 달성률(%)이 아니라 횟수로 보여드려요.",
    }
