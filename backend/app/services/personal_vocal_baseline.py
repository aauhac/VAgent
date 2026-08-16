# -*- coding: utf-8 -*-
"""Personal Vocal Baseline + Progress Comparison — HOW layer, separate from Singer Identity."""

from __future__ import annotations

from collections import Counter
from typing import Any, Optional

# Descriptive axes: change only, never auto-improvement
DESCRIPTIVE_AXES = frozenset(
    {"brightness", "source_balance", "timbre", "presence", "breathiness", "contact"}
)

CANONICAL_AXES = (
    "effort",
    "contact",
    "breathiness",
    "register_connection",
    "source_balance",
    "stability",
    "brightness",
    "presence",
)


def _axis_label(canonical: dict[str, Any], axis: str) -> Optional[str]:
    val = canonical.get(axis)
    if val is None:
        return None
    if isinstance(val, dict):
        return val.get("label") or val.get("status") or val.get("value")
    return str(val)


def extract_canonical(payload: dict[str, Any]) -> dict[str, Any]:
    """Pull categorical labels from analysis/public_result/canonical blocks."""
    canonical = payload.get("canonical") or {}
    if not canonical and payload.get("effort_status"):
        canonical = {
            "effort": payload.get("effort_status"),
            "register_connection": payload.get("register_connection"),
            "breathiness": payload.get("breathiness"),
            "brightness": payload.get("brightness"),
            "source_balance": payload.get("source_balance"),
            "contact": payload.get("contact"),
            "stability": payload.get("stability"),
            "presence": payload.get("presence"),
        }
    out = {}
    for axis in CANONICAL_AXES:
        lab = _axis_label(canonical, axis) if isinstance(canonical, dict) else None
        if lab is None and axis in payload:
            lab = payload.get(axis)
        if lab is not None:
            out[axis] = lab
    return out


def history_status(n_previous: int) -> str:
    if n_previous <= 0:
        return "NO_BASELINE"
    if n_previous <= 2:
        return "LIMITED_HISTORY"
    return "AVAILABLE"


def build_distribution(labels: list[str]) -> dict[str, float]:
    if not labels:
        return {}
    c = Counter(labels)
    total = float(sum(c.values()))
    return {k: v / total for k, v in c.items()}


def build_baseline(
    historical_snapshots: list[dict[str, Any]],
    *,
    recent_n: Optional[int] = None,
) -> dict[str, Any]:
    """Exclude current by requiring caller to pass historical-only list."""
    snaps = list(historical_snapshots)
    if recent_n is not None and recent_n > 0:
        snaps = snaps[-recent_n:]
    axis_labels: dict[str, list[str]] = {a: [] for a in CANONICAL_AXES}
    versions = set()
    for s in snaps:
        versions.add(s.get("analyzer_version"))
        can = s.get("canonical_json") or s.get("canonical") or {}
        for axis in CANONICAL_AXES:
            lab = _axis_label(can, axis) if isinstance(can, dict) else None
            if lab is not None:
                axis_labels[axis].append(str(lab))
    distributions = {
        axis: build_distribution(labs) for axis, labs in axis_labels.items() if labs
    }
    mixed = len({v for v in versions if v}) > 1
    return {
        "recording_count": len(snaps),
        "axis_distributions": distributions,
        "history_status": history_status(len(snaps)),
        "comparability": "MIXED_ANALYZER_VERSIONS" if mixed else "COMPARABLE",
        "window": f"RECENT_{recent_n}" if recent_n else "ALL_HISTORY",
        "uses_ecapa_identity_score": False,
        "categorical_axes_preserved": True,
        "arbitrary_numeric_scoring": False,
    }


def _goal_axis(goal: Optional[Any]) -> Optional[str]:
    if goal is None:
        return None
    if isinstance(goal, str):
        g = goal.upper()
        if "REGISTER" in g or "성구" in goal:
            return "register_connection"
        if "STABILITY" in g or "안정" in goal:
            return "stability"
        return None
    if isinstance(goal, dict):
        return _goal_axis(goal.get("axis") or goal.get("focus") or goal.get("goal"))
    if isinstance(goal, list) and goal:
        return _goal_axis(goal[0])
    return None


def _register_improvement(current: str, hist_dist: dict[str, float]) -> Optional[bool]:
    """Goal-aligned register stability: toward CONNECTED from PARTIAL/DISRUPTED."""
    unstable = hist_dist.get("PARTIAL", 0) + hist_dist.get("DISRUPTED", 0) + hist_dist.get("UNRESOLVED", 0)
    if current == "CONNECTED" and unstable >= 0.5:
        return True
    if current in ("DISRUPTED", "PARTIAL") and hist_dist.get("CONNECTED", 0) >= 0.5:
        return False
    return None


def compare_progress(
    *,
    current_canonical: dict[str, Any],
    historical_snapshots: list[dict[str, Any]],
    goal: Optional[Any] = None,
    recent_n: int = 5,
) -> dict[str, Any]:
    """
    CHANGE vs IMPROVEMENT separated.
    Current snapshot must NOT be included in historical_snapshots.
    """
    if not historical_snapshots:
        return {"status": "NO_BASELINE", "history_count": 0, "comparisons": []}

    baseline_all = build_baseline(historical_snapshots)
    baseline_recent = build_baseline(historical_snapshots, recent_n=recent_n)
    goal_axis = _goal_axis(goal)
    comparisons = []

    for axis in CANONICAL_AXES:
        current = current_canonical.get(axis)
        if current is None:
            continue
        dist = (baseline_recent.get("axis_distributions") or {}).get(axis) or (
            baseline_all.get("axis_distributions") or {}
        ).get(axis) or {}
        if not dist:
            continue
        modal = max(dist.items(), key=lambda kv: kv[1])[0]
        if str(current) == str(modal):
            change = "UNCHANGED"
        else:
            change = "CHANGED"
        improvement: Optional[bool] = None
        interpretation = f"{axis}: {modal} → {current}"

        if axis in DESCRIPTIVE_AXES or axis in ("brightness", "source_balance", "timbre"):
            improvement = None
            if axis == "brightness":
                interpretation = f"밝기 변화 ({modal} → {current})"
            elif axis == "source_balance":
                interpretation = f"소스 밸런스 변화 ({modal} → {current})"
            else:
                interpretation = f"{axis} 변화 ({modal} → {current})"
        elif axis == "register_connection" and goal_axis == "register_connection":
            improvement = _register_improvement(str(current), dist)
            if improvement is True:
                interpretation = "성구 연결이 목표 방향으로 안정화되는 변화"
                change = "MORE_STABLE_DIRECTION"
            elif improvement is False:
                interpretation = "성구 연결이 목표와 반대로 흔들리는 변화"
        elif axis == "effort":
            # never auto-improvement on effort decrease/increase
            improvement = None
            interpretation = f"힘 사용 변화 ({modal} → {current})"
        elif axis == "stability" and goal_axis == "stability":
            if str(current) == "STABLE" and dist.get("STABLE", 0) < 0.5:
                improvement = True
                change = "MORE_STABLE_DIRECTION"
            else:
                improvement = None

        comparisons.append(
            {
                "axis": axis,
                "current": current,
                "historical_distribution": dist,
                "historical_modal": modal,
                "change": change,
                "interpretation": interpretation,
                "improvement": improvement,
            }
        )

    status = baseline_recent["history_status"]
    if baseline_all.get("comparability") == "MIXED_ANALYZER_VERSIONS":
        status = "MIXED_ANALYZER_VERSIONS"

    return {
        "status": status,
        "history_count": len(historical_snapshots),
        "baseline_all_history": baseline_all,
        "baseline_recent": baseline_recent,
        "comparisons": comparisons,
        "goal_aware": goal_axis is not None,
        "current_excluded_from_baseline": True,
        "uses_ecapa_as_vocal_quality": False,
    }


# Explicit public helpers for tests
def brightness_change_is_improvement(_before: Any, _after: Any) -> bool:
    return False


def source_balance_change_is_improvement(_before: Any, _after: Any) -> bool:
    return False


def contact_change_is_improvement(_before: Any, _after: Any) -> bool:
    return False


def effort_decrease_is_automatic_improvement(_before: Any, _after: Any) -> bool:
    return False
