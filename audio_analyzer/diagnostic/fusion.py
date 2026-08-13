"""Song + standardized-task evidence fusion (protocol v1.2).

TASK RECORDED ≠ DIMENSION RESOLVED.
Only dimension_evidence.resolution_eligible can resolve uncertainty.
No generic 'observed' presence markers. No fixed medium fallback.
No silent overwrite of strong song evidence.
"""

from __future__ import annotations

from typing import Any, Optional

from audio_analyzer.diagnostic.task_registry import (
    DIMENSION_USER_LABELS,
    PLANNER_VERSION,
    PROTOCOL_VERSION,
    REPORT_VERSION,
    TASK_REGISTRY,
)

_ENGINE_MAP = {
    "contact": "glottal_contact_profile",
    "breathiness": "air_leakage_breathiness",
    "effort": "vocal_effort_strain",
    "register": "register_configuration",
    "stability": "phonation_regularity",
    "resonance": "resonance_formant_strategy",
    "onset": "onset_offset_coordination",
    "dynamic_response": "respiratory_phonatory_coordination",
}


def _song_conf_score(dim: dict[str, Any]) -> Optional[float]:
    if dim.get("confidence_score") is not None:
        try:
            return float(dim["confidence_score"])
        except (TypeError, ValueError):
            pass
    # Presentation-only label mapping — marked as such, not invented evidence
    label = (dim.get("confidence_label") or "").lower()
    m = {"high": 0.85, "medium": 0.6, "low": 0.35}
    return m.get(label)


def _song_dim_snapshot(dims: dict[str, Any], engine_id: str, planner_key: str) -> dict[str, Any]:
    d = dims.get(engine_id) or {}
    return {
        "dimension": planner_key,
        "label": DIMENSION_USER_LABELS.get(planner_key, planner_key),
        "status": d.get("status"),
        "summary": d.get("summary") or d.get("user_summary"),
        "confidence": d.get("confidence_label"),
        "confidence_score": _song_conf_score(d),
        "confidence_source": "song_dimension",
        "source": "song",
    }


def _task_quality_ok(task_result: dict[str, Any]) -> bool:
    if task_result.get("invalid") or task_result.get("quality_fail"):
        return False
    q = task_result.get("quality") or {}
    if q.get("status") == "fail":
        return False
    if task_result.get("error"):
        return False
    compliance = task_result.get("compliance") or {}
    if compliance and compliance.get("ok") is False:
        return False
    return True


def _extract_dimension_evidence(task_results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Collect best resolution_eligible evidence per dimension. No covers fallback."""
    out: dict[str, dict[str, Any]] = {}
    for tr in task_results:
        tid = tr.get("task_id")
        if not tid:
            continue
        quality_ok = _task_quality_ok(tr)
        dim_ev = tr.get("dimension_evidence") or {}
        if not isinstance(dim_ev, dict):
            continue
        for dim, ev in dim_ev.items():
            if not isinstance(ev, dict):
                continue
            # Invalid quality → never resolution eligible
            if not quality_ok:
                ev = {
                    **ev,
                    "resolution_eligible": False,
                    "quality_valid": False,
                    "reason": ev.get("reason") or "task_quality_or_compliance_fail",
                }
            if not ev.get("available") and not ev.get("resolution_eligible"):
                # Keep first unavailable note if nothing better
                if dim not in out:
                    out[dim] = {
                        **ev,
                        "dimension": dim,
                        "label": DIMENSION_USER_LABELS.get(dim, dim),
                        "source": "task",
                        "task_id": tid,
                        "valid": False,
                    }
                continue
            score = ev.get("confidence_score")
            prev = out.get(dim)
            prev_score = (prev or {}).get("confidence_score")
            take = False
            if ev.get("resolution_eligible"):
                if not prev or not prev.get("resolution_eligible"):
                    take = True
                elif score is not None and (prev_score is None or float(score) > float(prev_score)):
                    take = True
            elif dim not in out:
                take = True
            if take:
                out[dim] = {
                    **ev,
                    "dimension": dim,
                    "label": DIMENSION_USER_LABELS.get(dim, dim),
                    "status": ev.get("status"),
                    "summary": ev.get("reason") or ev.get("status"),
                    "confidence": ev.get("confidence_label"),
                    "confidence_score": score,
                    "source": "task",
                    "task_id": tid,
                    "valid": bool(ev.get("resolution_eligible")),
                    "resolution_eligible": bool(ev.get("resolution_eligible")),
                    "confidence_source": ev.get("confidence_source"),
                }
    return out


def _statuses_conflict(song_status: Any, task_status: Any) -> bool:
    s = str(song_status or "").lower()
    t = str(task_status or "").lower()
    if not s or not t:
        return False
    if s in ("unknown",) or t in ("unknown", "insufficient", "observed"):
        return False
    # Normalize rough families
    lightish = ("light", "light_leaning", "breathy", "low", "connected")
    firmish = ("firm", "firm_leaning", "elevated", "high", "disrupted", "unstable")
    s_light = any(x in s for x in lightish)
    t_light = any(x in t for x in lightish)
    s_firm = any(x in s for x in firmish)
    t_firm = any(x in t for x in firmish)
    if (s_light and t_firm) or (s_firm and t_light):
        return True
    return s != t and s_light == t_light and s_firm == t_firm and False


def compare_contexts(
    song_snap: dict[str, Any],
    task_snap: dict[str, Any],
) -> Optional[dict[str, Any]]:
    if not song_snap or not task_snap:
        return None
    if not task_snap.get("resolution_eligible") and not task_snap.get("valid"):
        return None
    s_status = song_snap.get("status")
    t_status = task_snap.get("status")
    if not _statuses_conflict(s_status, t_status) and str(s_status).lower() == str(t_status).lower():
        return None
    if not _statuses_conflict(s_status, t_status):
        # still allow explicit different tokens
        if str(s_status or "").lower() == str(t_status or "").lower():
            return None
        if not s_status or not t_status:
            return None
    song_c = song_snap.get("confidence_score")
    task_c = task_snap.get("confidence_score")
    strong = (
        song_c is not None
        and task_c is not None
        and float(song_c) >= 0.6
        and float(task_c) >= 0.6
    )
    return {
        "dimension": song_snap.get("dimension"),
        "baseline": t_status,
        "song": s_status,
        "strong": strong,
        "resolution_state": "CONTEXT_DEPENDENT" if strong else "WEAK_CONTRADICTION",
        "interpretation": (
            "표준 과제와 실제 노래에서 발성 패턴이 다르게 나타났어요."
            if strong
            else "노래와 표준 과제 결과가 다소 다르게 보였어요."
        ),
        "song_summary": song_snap.get("summary"),
        "baseline_summary": task_snap.get("summary") or task_snap.get("reason"),
    }


def fuse_song_and_task_evidence(
    *,
    song_profile: Optional[dict[str, Any]] = None,
    task_results: Optional[list[dict[str, Any]]] = None,
    unresolved_before: Optional[list[str]] = None,
    selected_tasks: Optional[list[str]] = None,
    user_skipped_tasks: Optional[list[str]] = None,
    completed_tasks: Optional[list[str]] = None,
    safety_blocked_tasks: Optional[list[str]] = None,
) -> dict[str, Any]:
    song_profile = song_profile or {}
    task_results = task_results or []
    unresolved_before = list(unresolved_before or [])
    selected_tasks = list(selected_tasks or [])
    user_skipped_tasks = list(user_skipped_tasks or [])
    completed_tasks = list(completed_tasks or [])
    safety_blocked_tasks = list(safety_blocked_tasks or [])

    dims = song_profile.get("dimensions") or {}
    song_snaps = {
        k: _song_dim_snapshot(dims, eid, k) for k, eid in _ENGINE_MAP.items() if dims.get(eid)
    }
    task_snaps = _extract_dimension_evidence(task_results)
    from audio_analyzer.diagnostic.concern_resolver import (
        build_controlled_contrasts,
        build_task_profiles,
    )

    task_profiles = build_task_profiles(task_results)
    controlled_contrasts = build_controlled_contrasts(task_profiles)

    expected_coverage: dict[str, list[str]] = {}
    actual_coverage: dict[str, list[str]] = {}
    for tr in task_results:
        tid = tr.get("task_id")
        if not tid:
            continue
        expected_coverage[tid] = list(
            tr.get("expected_coverage")
            or ((TASK_REGISTRY.get(tid) or {}).get("covers") or [])
        )
        actual_coverage[tid] = list(tr.get("actual_coverage") or [])

    invalid_tasks = [
        tr.get("task_id")
        for tr in task_results
        if tr.get("task_id") and not _task_quality_ok(tr)
    ]

    resolved: dict[str, Any] = {}
    context_resolved: dict[str, Any] = {}
    remaining: list[str] = []
    contextual: list[dict[str, Any]] = []
    confidence_delta: list[dict[str, Any]] = []

    target_dims = set(unresolved_before) | set(task_snaps.keys()) | set(
        d for d in unresolved_before
    )
    for dim in sorted(target_dims, key=lambda d: list(_ENGINE_MAP.keys()).index(d) if d in _ENGINE_MAP else 99):
        s = song_snaps.get(dim)
        t = task_snaps.get(dim)
        song_c = (s or {}).get("confidence_score")
        task_c = (t or {}).get("confidence_score") if t else None
        eligible = bool(t and t.get("resolution_eligible"))

        conflict = compare_contexts(s or {}, t or {}) if (s and eligible) else None
        if conflict:
            contextual.append(conflict)

        # Strong conflict: never overwrite song with task
        if conflict and conflict.get("strong"):
            context_resolved[dim] = {
                "dimension": dim,
                "label": DIMENSION_USER_LABELS.get(dim, dim),
                "baseline": t,
                "song": s,
                "final_status": "CONTEXT_DEPENDENT",
                "resolution_state": "RESOLVED_CONTEXT_DEPENDENT",
                "song_confidence": song_c,
                "task_confidence": task_c,
                "final_confidence": max(
                    float(song_c or 0), float(task_c or 0)
                ),
                "resolved": True,
                "mode": "contextual_difference",
            }
            confidence_delta.append(
                {
                    "dimension": dim,
                    "label": DIMENSION_USER_LABELS.get(dim, dim),
                    "song_confidence": song_c,
                    "task_confidence": task_c,
                    "final_confidence": max(float(song_c or 0), float(task_c or 0)),
                    "note": "context_dependent_not_merged",
                }
            )
            continue

        if eligible and dim in unresolved_before:
            # Weak song + strong task → baseline resolve, keep weak song observation
            final_c = float(task_c) if task_c is not None else None
            resolved[dim] = {
                "dimension": dim,
                "label": DIMENSION_USER_LABELS.get(dim, dim),
                "baseline": t,
                "song": s,
                "final_status": (t or {}).get("status"),
                "resolution_state": "RESOLVED_SINGLE_PATTERN",
                "song_confidence": song_c,
                "task_confidence": task_c,
                "final_confidence": final_c,
                "resolved": True,
                "mode": "task_dimension_evidence",
            }
            confidence_delta.append(
                {
                    "dimension": dim,
                    "label": DIMENSION_USER_LABELS.get(dim, dim),
                    "song_confidence": song_c,
                    "task_confidence": task_c,
                    "final_confidence": final_c,
                }
            )
            continue

        if dim in unresolved_before:
            remaining.append(dim)
            resolved[dim] = {
                "dimension": dim,
                "label": DIMENSION_USER_LABELS.get(dim, dim),
                "baseline": t,
                "song": s,
                "final_status": (s or {}).get("status"),
                "resolution_state": (
                    "UNAVAILABLE"
                    if t and t.get("available") is False and t.get("reason") in (
                        "quality_fail",
                        "swell_compliance_fail",
                        "siren_compliance_fail",
                    )
                    else "UNRESOLVED_WEAK_EVIDENCE"
                ),
                "song_confidence": song_c,
                "task_confidence": task_c,
                "final_confidence": song_c,  # no boost without eligible evidence
                "resolved": False,
                "mode": "uncertainty_remains",
            }
            continue

        if s or (t and t.get("available")):
            resolved[dim] = {
                "dimension": dim,
                "label": DIMENSION_USER_LABELS.get(dim, dim),
                "baseline": t,
                "song": s,
                "final_status": (t or s or {}).get("status"),
                "resolution_state": "RESOLVED_SINGLE_PATTERN" if eligible or s else "UNRESOLVED_WEAK_EVIDENCE",
                "song_confidence": song_c,
                "task_confidence": task_c,
                "final_confidence": song_c if not eligible else (task_c if task_c is not None else song_c),
                "resolved": bool(eligible or s),
                "mode": "observed_without_prior_uncertainty",
            }

    return {
        "planner_version": PLANNER_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "report_version": REPORT_VERSION,
        "baseline_profile": {k: v for k, v in task_snaps.items() if v.get("resolution_eligible")},
        "song_profile": song_snaps,
        "contextual_differences": contextual,
        "resolved_dimensions": {
            k: v for k, v in resolved.items() if v.get("resolved") and v.get("resolution_state") != "RESOLVED_CONTEXT_DEPENDENT"
        },
        "context_resolved_dimensions": context_resolved,
        "remaining_uncertainties": remaining,
        "task_evidence": {
            "selected_tasks": selected_tasks,
            "task_ids_present": [tr.get("task_id") for tr in task_results if tr.get("task_id")],
            "invalid_tasks": invalid_tasks,
            "user_skipped_tasks": user_skipped_tasks,
            "completed_tasks": completed_tasks
            or [tr.get("task_id") for tr in task_results if tr.get("task_id")],
            "safety_blocked_tasks": safety_blocked_tasks,
            "expected_coverage": expected_coverage,
            "actual_coverage": actual_coverage,
        },
        "task_profiles": task_profiles,
        "controlled_contrasts": controlled_contrasts,
        "confidence_delta": confidence_delta,
        "fusion_rules": {
            "blind_average": False,
            "fixed_confidence_bonus": False,
            "invalid_task_boosts_confidence": False,
            "covers_implies_resolved": False,
            "observed_marker_fallback": False,
            "resolution_requires_dimension_evidence": True,
        },
    }


def build_final_diagnostic_profile(
    *,
    song_profile: Optional[dict[str, Any]] = None,
    task_results: Optional[list[dict[str, Any]]] = None,
    plan: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    plan = plan or {}
    fused = fuse_song_and_task_evidence(
        song_profile=song_profile,
        task_results=task_results,
        unresolved_before=plan.get("unresolved_dimensions") or [],
        selected_tasks=plan.get("selected_tasks") or [],
        user_skipped_tasks=plan.get("user_skipped_tasks") or [],
        completed_tasks=plan.get("completed_tasks") or [],
        safety_blocked_tasks=plan.get("safety_blocked_tasks") or [],
    )
    planned = list(plan.get("selected_tasks") or [])
    skipped = list(plan.get("user_skipped_tasks") or [])
    completed = list(plan.get("completed_tasks") or [])
    present = list((fused.get("task_evidence") or {}).get("task_ids_present") or [])
    # Prefer completed list; fall back to present task results
    has_valid = bool(completed or present)
    if skipped and has_valid:
        evidence_mode = "PARTIAL_PRECISION"
    elif not has_valid and (skipped or planned):
        evidence_mode = "CONCERN_ONLY"
    elif not has_valid and not planned:
        evidence_mode = "FULL_PRECISION"  # legacy song-only / empty plan
    else:
        evidence_mode = "FULL_PRECISION"
    measured = []
    for tr in task_results or []:
        measured.extend(tr.get("actual_coverage") or [])
    measured = sorted(set(measured))
    labels_resolved = [
        DIMENSION_USER_LABELS.get(d, d)
        for d in list(fused.get("resolved_dimensions") or {})
        + list(fused.get("context_resolved_dimensions") or {})
    ]
    labels_remain = [
        DIMENSION_USER_LABELS.get(d, d) for d in (fused.get("remaining_uncertainties") or [])
    ]
    fused["planned"] = planned
    fused["measured"] = measured
    fused["evidence_mode"] = evidence_mode
    headline = "고민 중심 분석" if evidence_mode == "CONCERN_ONLY" else "정밀 발성 진단"
    fused["user_summary"] = {
        "headline": headline,
        "planned_line": (
            f"확인하려고 녹음한 과제: {', '.join(planned)}" if planned else "추가 표준 녹음 없음"
        ),
        "measured_line": (
            f"실제로 측정된 항목: {' · '.join([DIMENSION_USER_LABELS.get(d, d) for d in measured])}"
            if measured
            else "이번에 확정 측정된 항목이 없어요."
        ),
        "confirmed_line": (
            f"이번 추가 측정으로 {('·'.join(labels_resolved[:3]))}을(를) 더 분명하게 확인했어요."
            if labels_resolved
            else None
        ),
        "remaining_line": (
            f"추가 확인이 남은 항목: {' · '.join(labels_remain)}" if labels_remain else None
        ),
        "confidence_note": "분석 신뢰도는 측정 근거에 따라 달라지며, 정확도 %가 아닙니다.",
    }
    return fused
