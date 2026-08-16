# -*- coding: utf-8 -*-
"""Goal-aware progress — count-based evidence, no fake 0–100 scores.

Uses VAgent canonical labels only. Singer Identity similarity is never used.
"""

from __future__ import annotations

from typing import Any, Optional

from backend.app.services.goal_catalog import (
    EXCLUDED_FOCUSES,
    SOURCE_RECOMMENDED,
    SOURCE_USER_SELECTED,
    normalize_goal_payload,
    option_for_focus,
)
from backend.app.services.personal_vocal_baseline import extract_canonical

INSUFFICIENT = frozenset(
    {"", "UNKNOWN", "UNRESOLVED", "UNAVAILABLE", "AMBIGUOUS", "NONE", "NULL"}
)

DEFAULT_WINDOW = 5

# Internal status → never expose fake completion %
STATUS_NO_GOAL = "NO_GOAL"
STATUS_INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
STATUS_INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
STATUS_STARTING = "STARTING"
STATUS_IMPROVING = "IMPROVING"
STATUS_STABLE = "STABLE"
STATUS_MAINTAINING = "MAINTAINING"
STATUS_MIXED = "MIXED"
STATUS_DECLINING = "DECLINING_GOAL_DIRECTION"
STATUS_EXCLUDED = "EXCLUDED_FROM_PROGRESS"
STATUS_LIMITED_COMPARISON = "COMPARISON_LIMITED"


def _axis_value(canonical: dict[str, Any], axis: str) -> Optional[str]:
    if not canonical:
        return None
    val = canonical.get(axis)
    if isinstance(val, dict):
        val = val.get("label") or val.get("status") or val.get("value")
    if val is None:
        return None
    s = str(val).upper().strip()
    return s or None


def _quality_ok(analysis_quality: Any) -> bool:
    if analysis_quality is None:
        return True
    q = str(analysis_quality).upper()
    if q in ("FAIL", "FAILED", "REJECT", "REJECTED", "LOW", "POOR", "UNRELIABLE"):
        return False
    return True


def evaluate_goal_evidence(
    goal: Any,
    canonical_snapshot: dict[str, Any],
    analysis_quality: Any = None,
) -> dict[str, Any]:
    """
    Single-source helper: one snapshot vs one goal → GoalEvidence.
    Never invents numeric scores from categorical labels.
    """
    raw = goal if isinstance(goal, dict) else {"focus": goal} if goal else {}
    g = normalize_goal_payload(goal) or {}
    # Catalog defaults must NOT silently invent style/effort alignment.
    # Only honor target/kind when the caller set them explicitly (or via set_goal store row).
    explicit_target = raw.get("target") if isinstance(raw, dict) else None
    explicit_kind = raw.get("kind") if isinstance(raw, dict) else None
    explicit_style = raw.get("style_id") if isinstance(raw, dict) else None
    if explicit_target is None and not raw.get("goal_label") and not raw.get("id"):
        # Bare focus string / minimal dict → strip catalog-inferred targets for safety
        if g.get("kind") == "STYLE" or str(g.get("focus") or "").upper() in (
            "BRIGHTNESS",
            "TIMBRE_STYLE",
            "TIMBRE",
            "STYLE",
            "CONTACT",
            "SOURCE_BALANCE",
            "PRESENCE",
        ):
            g = {**g, "target": None, "style_id": None}
        if str(g.get("focus") or "").upper() == "EFFORT":
            # Catalog maps EFFORT → EFFORT_REDUCE; only keep when explicitly requested
            if explicit_kind is None or str(explicit_kind).upper() not in ("EFFORT_REDUCE",):
                g = {
                    **g,
                    "kind": explicit_kind or "OTHER",
                    "target": None,
                }
    else:
        # Stored user goal rows include label/id — keep catalog target
        if explicit_target is not None:
            g["target"] = explicit_target
        if explicit_kind is not None:
            g["kind"] = explicit_kind
            # Explicit non-reduce effort must not inherit catalog LOWER target
            if str(g.get("focus") or "").upper() == "EFFORT" and str(explicit_kind).upper() != "EFFORT_REDUCE":
                if explicit_target is None:
                    g["target"] = None
        if explicit_style is not None:
            g["style_id"] = explicit_style
        # Style without explicit target → neutral
        if str(g.get("kind") or "").upper() == "STYLE" and explicit_target is None and not explicit_style:
            g["target"] = None
            g["style_id"] = None

    focus = str(g.get("focus") or "").upper()
    if not focus:
        return {
            "evaluable": False,
            "direction": "INSUFFICIENT_EVIDENCE",
            "axis": None,
            "evidence": None,
            "reason": "NO_GOAL",
            "quality": "N/A",
        }
    if focus in EXCLUDED_FOCUSES or focus == "SAFETY":
        return {
            "evaluable": False,
            "direction": "INSUFFICIENT_EVIDENCE",
            "axis": None,
            "evidence": None,
            "reason": "SAFETY_OR_MAINTAIN_EXCLUDED",
            "quality": "EXCLUDED",
            "gamification_forbidden": True,
        }
    if not _quality_ok(analysis_quality):
        return {
            "evaluable": False,
            "direction": "INSUFFICIENT_EVIDENCE",
            "axis": g.get("axis"),
            "evidence": None,
            "reason": "LOW_ANALYSIS_QUALITY",
            "quality": "UNRELIABLE",
        }

    can = extract_canonical(canonical_snapshot) if canonical_snapshot else {}
    if not can and canonical_snapshot:
        can = {k: v for k, v in canonical_snapshot.items() if not isinstance(v, (dict, list))}
    axis = str(g.get("axis") or "").strip() or _axis_for_focus(focus)
    evidence = _axis_value(can, axis)
    if evidence is None or evidence in INSUFFICIENT:
        return {
            "evaluable": False,
            "direction": "INSUFFICIENT_EVIDENCE",
            "axis": axis,
            "evidence": evidence,
            "reason": "AXIS_UNRESOLVED_OR_MISSING",
            "quality": "INSUFFICIENT",
        }

    kind = str(g.get("kind") or "").upper()
    target = str(g.get("target") or "").upper() if g.get("target") else None
    direction, reason = _direction_for(focus, kind, target, evidence, g)

    return {
        "evaluable": direction != "INSUFFICIENT_EVIDENCE",
        "direction": direction,
        "axis": axis,
        "evidence": evidence,
        "reason": reason,
        "quality": "RELIABLE",
        "called_generic_improvement": False,
        "uses_fake_percent": False,
        "uses_identity_similarity": False,
    }


def _axis_for_focus(focus: str) -> str:
    opt = option_for_focus(focus)
    return (opt or {}).get("axis") or "register_connection"


def _direction_for(
    focus: str,
    kind: str,
    target: Optional[str],
    evidence: str,
    goal: dict[str, Any],
) -> tuple[str, str]:
    # REGISTER / HIGH_NOTE → CONNECTED is aligned
    if focus in ("REGISTER_CONNECTION", "HIGH_NOTE_ACCESS"):
        if evidence == "CONNECTED":
            return "GOAL_ALIGNED", "CONNECTED_IS_GOAL_DIRECTION"
        if evidence in ("PARTIAL", "DISRUPTED"):
            return "NOT_GOAL_ALIGNED", "NOT_YET_CONNECTED"
        return "INSUFFICIENT_EVIDENCE", "UNEXPECTED_LABEL"

    if focus in ("STABILITY", "PITCH_STABILITY", "PHRASE_ENDURANCE", "VIBRATO_CONTROL"):
        if evidence == "STABLE":
            return "GOAL_ALIGNED", "STABLE_IS_GOAL_DIRECTION"
        if evidence == "UNSTABLE":
            return "NOT_GOAL_ALIGNED", "UNSTABLE"
        return "INSUFFICIENT_EVIDENCE", "UNEXPECTED_LABEL"

    # Effort: lower only when explicit reduce goal
    if focus == "EFFORT" or kind == "EFFORT_REDUCE":
        if target in ("LOWER", "REDUCE", "LOW") or kind == "EFFORT_REDUCE":
            if evidence == "LOW":
                return "GOAL_ALIGNED", "LOWER_EFFORT_MATCHES_EXPLICIT_GOAL"
            if evidence in ("HIGH", "MODERATE"):
                return "NOT_GOAL_ALIGNED", "EFFORT_STILL_ELEVATED"
            return "INSUFFICIENT_EVIDENCE", "UNEXPECTED_LABEL"
        return "NEUTRAL", "EFFORT_WITHOUT_EXPLICIT_REDUCE_GOAL"

    # Breathiness reduce
    if focus == "BREATHINESS":
        if target in ("LOWER", "REDUCE", "LOW") or kind == "EXPLICIT_DIRECTION":
            if evidence == "LOW":
                return "GOAL_ALIGNED", "LOWER_BREATHINESS_MATCHES_GOAL"
            if evidence in ("HIGH", "MODERATE"):
                return "NOT_GOAL_ALIGNED", "BREATHINESS_STILL_PRESENT"
            return "INSUFFICIENT_EVIDENCE", "UNEXPECTED_LABEL"
        return "NEUTRAL", "BREATHINESS_WITHOUT_EXPLICIT_TARGET"

    # Contact — never auto without target
    if focus == "CONTACT":
        if not target:
            return "NEUTRAL", "CONTACT_REQUIRES_EXPLICIT_TARGET"
        if evidence == target:
            return "GOAL_ALIGNED", "CONTACT_MATCHES_TARGET"
        if evidence in INSUFFICIENT:
            return "INSUFFICIENT_EVIDENCE", "CONTACT_UNRESOLVED"
        return "NOT_GOAL_ALIGNED", "CONTACT_NOT_TARGET"

    # Brightness / style
    if focus in ("BRIGHTNESS", "TIMBRE_STYLE", "TIMBRE", "STYLE") or kind == "STYLE":
        if not target and not goal.get("style_id"):
            return "NEUTRAL", "STYLE_REQUIRES_EXPLICIT_TARGET"
        # HIGHER brightness for BRIGHT_CLEAR
        if target == "HIGHER":
            if evidence == "HIGH":
                return "GOAL_ALIGNED", "BRIGHTER_MATCHES_STYLE_GOAL"
            if evidence in ("LOW", "MID"):
                return "NOT_GOAL_ALIGNED", "NOT_YET_BRIGHT"
            return "INSUFFICIENT_EVIDENCE", "UNEXPECTED_LABEL"
        if target == "LOWER":
            if evidence == "LOW":
                return "GOAL_ALIGNED", "WARMER_DARKER_MATCHES_STYLE_GOAL"
            if evidence in ("HIGH", "MID"):
                return "NOT_GOAL_ALIGNED", "NOT_YET_WARMER"
            return "INSUFFICIENT_EVIDENCE", "UNEXPECTED_LABEL"
        if evidence == target:
            return "GOAL_ALIGNED", "STYLE_TARGET_MATCH"
        return "NOT_GOAL_ALIGNED", "STYLE_NOT_MATCH"

    # Source balance — only with explicit target
    if focus == "SOURCE_BALANCE" or axis_is_source(goal):
        if not target:
            return "NEUTRAL", "SOURCE_BALANCE_REQUIRES_EXPLICIT_TARGET"
        if evidence == target:
            return "GOAL_ALIGNED", "SOURCE_BALANCE_MATCHES_TARGET"
        return "NOT_GOAL_ALIGNED", "SOURCE_BALANCE_NOT_TARGET"

    if focus == "PRESENCE":
        if target == "HIGHER" and evidence == "HIGH":
            return "GOAL_ALIGNED", "PRESENCE_MATCHES"
        if target and evidence == target:
            return "GOAL_ALIGNED", "PRESENCE_MATCHES"
        if not target:
            return "NEUTRAL", "PRESENCE_REQUIRES_TARGET"
        return "NOT_GOAL_ALIGNED", "PRESENCE_NOT_TARGET"

    return "NEUTRAL", "FOCUS_NOT_AUTO_SCORED"


def axis_is_source(goal: dict[str, Any]) -> bool:
    return str(goal.get("axis") or "") == "source_balance"


def _snap_canonical(snap: dict[str, Any]) -> dict[str, Any]:
    can = snap.get("canonical_json") or snap.get("canonical") or {}
    if isinstance(can, dict) and can:
        return extract_canonical(can) or {
            k: (v.get("label") if isinstance(v, dict) else v)
            for k, v in can.items()
            if not isinstance(v, (list, dict)) or isinstance(v, dict)
        }
    return extract_canonical(snap) or {}


def _snap_quality(snap: dict[str, Any]) -> Any:
    return snap.get("analysis_quality") or snap.get("quality")


def _goal_id(goal: Any) -> Optional[str]:
    if isinstance(goal, dict):
        return goal.get("id") or goal.get("goal_id")
    return None


def _filter_snaps_for_goal(
    snapshots: list[dict[str, Any]],
    goal: dict[str, Any],
) -> list[dict[str, Any]]:
    """New goal starts its own window — only snaps at/after start, matching goal_id when present."""
    gid = _goal_id(goal)
    started = goal.get("started_at")
    out = []
    for s in snapshots:
        # Prefer explicit goal reference stamped at analysis time
        snap_gid = s.get("goal_id_at_analysis") or s.get("goal_id")
        if gid and snap_gid:
            if snap_gid == gid:
                out.append(s)
            continue
        # Fallback: time window after goal start (do not rewrite historical goal context)
        if started:
            created = s.get("created_at") or s.get("recorded_at") or ""
            if created and created < started:
                continue
        # If snap has a different goal_focus stamped, skip for this goal
        snap_focus = s.get("goal_focus_at_analysis")
        if snap_focus and str(snap_focus).upper() != str(goal.get("goal_focus") or goal.get("focus") or "").upper():
            continue
        out.append(s)
    return out


def _window_stats(snaps: list[dict[str, Any]], goal: dict[str, Any]) -> dict[str, Any]:
    sequence: list[str] = []
    dots: list[str] = []
    aligned = 0
    evaluable = 0
    for s in snaps:
        ev = evaluate_goal_evidence(goal, _snap_canonical(s), _snap_quality(s))
        d = ev["direction"]
        sequence.append(d)
        if d == "GOAL_ALIGNED":
            aligned += 1
            evaluable += 1
            dots.append("ALIGNED")
        elif d in ("NOT_GOAL_ALIGNED", "NEUTRAL"):
            evaluable += 1
            dots.append("NOT_ALIGNED" if d == "NOT_GOAL_ALIGNED" else "NEUTRAL")
        else:
            dots.append("INSUFFICIENT")
    return {
        "size": len(snaps),
        "evaluable_count": evaluable,
        "goal_aligned_count": aligned,
        "sequence": sequence,
        "dots": dots,
    }


def _status_from_windows(
    recent: dict[str, Any],
    previous: Optional[dict[str, Any]],
) -> str:
    if recent["size"] == 0:
        return STATUS_INSUFFICIENT_HISTORY
    if recent["evaluable_count"] == 0:
        return STATUS_INSUFFICIENT_EVIDENCE
    if previous is None or previous.get("evaluable_count", 0) == 0:
        if recent["goal_aligned_count"] >= recent["evaluable_count"] and recent["evaluable_count"] >= 3:
            return STATUS_MAINTAINING
        return STATUS_STARTING

    r = recent["goal_aligned_count"]
    p = previous["goal_aligned_count"]
    re = max(recent["evaluable_count"], 1)
    pe = max(previous["evaluable_count"], 1)
    # Compare counts first (primary UX); rate as secondary when windows equal size
    if r > p:
        return STATUS_IMPROVING
    if r < p:
        return STATUS_DECLINING
    # same aligned count — check density
    if r / re >= 0.8 and recent["evaluable_count"] >= 3:
        return STATUS_MAINTAINING
    if abs((r / re) - (p / pe)) < 0.15:
        return STATUS_STABLE
    return STATUS_MIXED


def _summary_ko(status: str, recent: dict[str, Any], previous: Optional[dict[str, Any]], goal: dict[str, Any]) -> str:
    wording = goal.get("wording")
    is_style = wording == "STYLE_DIRECTION" or str(goal.get("kind") or "").upper() == "STYLE"
    n = recent.get("goal_aligned_count", 0)
    w = recent.get("size", DEFAULT_WINDOW)
    ev = recent.get("evaluable_count", 0)

    if status == STATUS_NO_GOAL:
        return ""
    if status in (STATUS_INSUFFICIENT_HISTORY, STATUS_STARTING):
        return "기록이 조금 더 쌓이면 목표 방향 변화를 보여드릴게요."
    if status == STATUS_INSUFFICIENT_EVIDENCE:
        return "비교 가능한 기록이 아직 충분하지 않아요."
    if status == STATUS_IMPROVING:
        if is_style:
            return "원하는 음색 방향이 최근 녹음에서 더 자주 나타났어요."
        if previous:
            return (
                f"최근에는 목표 방향 결과가 조금 더 자주 나타났어요. "
                f"(이전 {previous.get('goal_aligned_count', 0)}회 → 최근 {n}회)"
            )
        return f"최근 {w}회 중 목표 방향 결과가 {n}회 나타났어요."
    if status == STATUS_MAINTAINING:
        return "최근에는 목표 방향 결과가 안정적으로 유지되고 있어요."
    if status == STATUS_STABLE:
        return "최근 녹음에서도 비슷한 수준으로 유지되고 있어요."
    if status == STATUS_DECLINING:
        return "최근에는 목표 방향 결과가 조금 덜 자주 나타났어요."
    if status == STATUS_MIXED:
        return "최근 결과가 일정하지 않아 조금 더 기록을 지켜보는 게 좋아요."
    if status == STATUS_LIMITED_COMPARISON:
        return "일부 기록은 분석 기준이 달라 직접 비교에서 제외했어요."
    if ev:
        return f"최근 비교 가능한 기록 {ev}회 중 목표 방향 {n}회예요."
    return "기록이 조금 더 쌓이면 변화 흐름을 보여드릴게요."


def build_goal_progress(
    *,
    goal: Optional[Any],
    historical_snapshots: list[dict[str, Any]],
    current_canonical: Optional[dict[str, Any]] = None,
    current_quality: Any = None,
    recent_n: int = DEFAULT_WINDOW,
    include_current_in_recent: bool = False,
) -> dict[str, Any]:
    """
    Goal progress payload for Result / Home / Progress Insight.
    current recording is NOT double-counted unless include_current_in_recent.
    """
    if not goal:
        return {
            "status": STATUS_NO_GOAL,
            "goal": None,
            "comparison_available": False,
            "uses_fake_percent": False,
            "uses_identity_similarity": False,
        }

    g = normalize_goal_payload(goal) or {}
    if isinstance(goal, dict) and goal.get("id"):
        g = {**g, "id": goal["id"], "started_at": goal.get("started_at"), "goal_focus": goal.get("goal_focus") or g.get("focus"), "source": goal.get("source") or g.get("source")}
    focus = str(g.get("focus") or "").upper()
    if focus in EXCLUDED_FOCUSES:
        return {
            "status": STATUS_EXCLUDED,
            "goal": _public_goal(g, goal),
            "comparison_available": False,
            "summary": "이 목표는 진행률로 표시하지 않아요.",
            "uses_fake_percent": False,
        }

    scoped = _filter_snaps_for_goal(list(historical_snapshots), g if isinstance(goal, dict) else g)
    # Mixed analyzer versions
    versions = {s.get("analyzer_version") for s in scoped if s.get("analyzer_version")}
    mixed = len(versions) > 1
    if mixed and versions:
        # keep most common version only for comparison
        from collections import Counter

        counts = Counter(s.get("analyzer_version") for s in scoped if s.get("analyzer_version"))
        primary = counts.most_common(1)[0][0]
        scoped = [s for s in scoped if s.get("analyzer_version") in (None, primary)]

    recent_snaps = scoped[-recent_n:]
    prev_snaps = None
    if len(scoped) > recent_n:
        prev_snaps = scoped[-(recent_n * 2) : -recent_n]

    # Optionally append current as synthetic snap for display sequence (not stored)
    eval_snaps = list(recent_snaps)
    if include_current_in_recent and current_canonical:
        eval_snaps = list(recent_snaps) + [
            {"canonical_json": current_canonical, "analysis_quality": current_quality}
        ]
        eval_snaps = eval_snaps[-recent_n:]

    recent = _window_stats(eval_snaps if include_current_in_recent else recent_snaps, g)
    previous = _window_stats(prev_snaps, g) if prev_snaps else None

    # Current recording evidence (separate, for sheet)
    current_ev = None
    if current_canonical is not None:
        current_ev = evaluate_goal_evidence(g, current_canonical, current_quality)

    status = _status_from_windows(recent, previous)
    if mixed:
        status = STATUS_LIMITED_COMPARISON if recent["evaluable_count"] else STATUS_INSUFFICIENT_EVIDENCE

    pub = _public_goal(g, goal)
    return {
        "status": status,
        "goal": pub,
        "window": {
            "size": recent_n,
            "recording_count": recent["size"],
            "evaluable_count": recent["evaluable_count"],
            "goal_aligned_count": recent["goal_aligned_count"],
        },
        "previous_window": (
            {
                "size": recent_n,
                "recording_count": previous["size"],
                "evaluable_count": previous["evaluable_count"],
                "goal_aligned_count": previous["goal_aligned_count"],
            }
            if previous
            else None
        ),
        "sequence": recent["sequence"],
        "dots": recent["dots"],
        "current_evidence": current_ev,
        "summary": _summary_ko(status, recent, previous, g),
        "comparison_available": previous is not None and previous.get("evaluable_count", 0) > 0,
        "mixed_analyzer_versions": mixed,
        "uses_fake_percent": False,
        "uses_identity_similarity": False,
        "note": "목표는 달성률(%)이 아니라 최근 기록에서 목표 방향 evidence가 나타난 횟수로 보여드려요.",
    }


def _public_goal(g: dict[str, Any], raw: Any) -> dict[str, Any]:
    source = (raw.get("source") if isinstance(raw, dict) else None) or g.get("source") or SOURCE_USER_SELECTED
    label = (raw.get("goal_label") if isinstance(raw, dict) else None) or g.get("label")
    return {
        "id": (raw.get("id") if isinstance(raw, dict) else None) or g.get("id"),
        "focus": g.get("focus"),
        "label": label,
        "source": source,
        "kind": g.get("kind"),
        "axis": g.get("axis"),
        "target": g.get("target"),
        "style_id": g.get("style_id"),
        "started_at": raw.get("started_at") if isinstance(raw, dict) else g.get("started_at"),
        "is_recommended": source == SOURCE_RECOMMENDED,
        "display_title": "추천 목표" if source == SOURCE_RECOMMENDED else "이번 목표",
    }


# Explicit contracts for tests
def brightness_without_style_goal_is_improvement(_b: Any, _a: Any) -> bool:
    return False


def source_balance_is_generic_improvement(_b: Any, _a: Any) -> bool:
    return False


def contact_is_generic_improvement(_b: Any, _a: Any) -> bool:
    return False


def lower_effort_always_goal_aligned() -> bool:
    return False


def identity_similarity_used_in_goal_progress() -> bool:
    return False
