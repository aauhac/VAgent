"""Song + standardized-task evidence fusion (no blind averaging).

Song = actual singing context.
Task = controlled baseline/context.
Both are retained; conflicts become contextual differences.
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

# physiology mechanism_id → planner dimension
_MECH_TO_DIM = {
    "phonation_contact_pattern": "contact",
    "phonatory_efficiency": "effort",
    "intensity_phonation_coordination": "effort",
    "onset_coordination": "onset",
    "release_coordination": "onset",
    "register_transition_coordination": "register",
    "vocal_tract_resonance_balance": "resonance",
    "phonation_stability": "stability",
}

_TASK_DIM_HINT = {
    "sustain_a": ["contact", "breathiness", "stability"],
    "sustain_i": ["contact", "breathiness", "resonance"],
    "siren": ["register"],
    "dynamic_swell": ["effort", "dynamic_response"],
}


def _conf_num(label: Any) -> float:
    if isinstance(label, (int, float)):
        return float(label)
    m = {"high": 0.85, "medium": 0.6, "low": 0.35, "unknown": 0.2}
    return m.get(str(label or "low").lower(), 0.35)


def _song_dim_snapshot(dims: dict[str, Any], engine_id: str, planner_key: str) -> dict[str, Any]:
    d = dims.get(engine_id) or {}
    return {
        "dimension": planner_key,
        "label": DIMENSION_USER_LABELS.get(planner_key, planner_key),
        "status": d.get("status"),
        "summary": d.get("summary") or d.get("user_summary"),
        "confidence": d.get("confidence_label"),
        "confidence_score": _conf_num(d.get("confidence_label")),
        "source": "song",
    }


def _task_quality_ok(task_result: dict[str, Any]) -> bool:
    if task_result.get("invalid") or task_result.get("quality_fail"):
        return False
    q = task_result.get("quality") or {}
    if q.get("status") == "fail":
        return False
    # physiology observers usually embed metrics; absence of core metrics = weak
    if task_result.get("error"):
        return False
    return True


def _extract_task_estimates(task_results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Map task results → per-dimension baseline estimates (qualitative)."""
    out: dict[str, dict[str, Any]] = {}
    for tr in task_results:
        tid = tr.get("task_id")
        if not tid or not _task_quality_ok(tr):
            continue
        mechs = tr.get("mechanisms") or tr.get("mechanism_estimates") or []
        if isinstance(mechs, dict):
            mechs = list(mechs.values())
        hinted = _TASK_DIM_HINT.get(tid) or list(
            (TASK_REGISTRY.get(tid) or {}).get("covers") or []
        )
        # From mechanisms
        for m in mechs:
            if not isinstance(m, dict):
                continue
            mid = m.get("mechanism_id") or m.get("id")
            dim = _MECH_TO_DIM.get(str(mid or ""))
            if not dim:
                continue
            conf = m.get("confidence_label") or m.get("confidence")
            status = m.get("status") or m.get("summary")
            prev = out.get(dim)
            score = _conf_num(conf)
            if prev and prev.get("confidence_score", 0) >= score:
                continue
            out[dim] = {
                "dimension": dim,
                "label": DIMENSION_USER_LABELS.get(dim, dim),
                "status": status,
                "summary": m.get("summary") or status,
                "confidence": conf,
                "confidence_score": score,
                "source": "task",
                "task_id": tid,
                "valid": True,
            }
        # Ensure covered dims get a presence marker even without mechanism detail
        for dim in hinted:
            if dim not in out:
                # Use overall task confidence if present
                conf = tr.get("confidence_label") or "medium"
                out[dim] = {
                    "dimension": dim,
                    "label": DIMENSION_USER_LABELS.get(dim, dim),
                    "status": tr.get("status") or "observed",
                    "summary": f"{tid} 과제에서 관찰",
                    "confidence": conf,
                    "confidence_score": _conf_num(conf),
                    "source": "task",
                    "task_id": tid,
                    "valid": True,
                }
    return out


def compare_contexts(
    song_snap: dict[str, Any],
    task_snap: dict[str, Any],
) -> Optional[dict[str, Any]]:
    """Return contextual difference when song/task disagree; never drop either."""
    if not song_snap or not task_snap:
        return None
    s_status = str(song_snap.get("status") or "").lower()
    t_status = str(task_snap.get("status") or "").lower()
    s_sum = str(song_snap.get("summary") or "")
    t_sum = str(task_snap.get("summary") or "")
    # Soft conflict: both present with different status tokens
    if s_status and t_status and s_status != t_status and s_status not in ("unknown",) and t_status not in (
        "unknown",
        "observed",
    ):
        return {
            "dimension": song_snap.get("dimension"),
            "baseline": t_status,
            "song": s_status,
            "interpretation": (
                "표준 과제와 실제 노래에서 발성 패턴이 다르게 나타났어요."
            ),
            "song_summary": s_sum,
            "baseline_summary": t_sum,
        }
    # Numeric confidence gap with same family — not a conflict
    return None


def fuse_song_and_task_evidence(
    *,
    song_profile: Optional[dict[str, Any]] = None,
    task_results: Optional[list[dict[str, Any]]] = None,
    unresolved_before: Optional[list[str]] = None,
    selected_tasks: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Fuse without blind averaging. Invalid tasks do not boost confidence."""
    song_profile = song_profile or {}
    task_results = task_results or []
    unresolved_before = list(unresolved_before or [])
    selected_tasks = list(selected_tasks or [])

    dims = song_profile.get("dimensions") or {}
    engine_map = {
        "contact": "glottal_contact_profile",
        "breathiness": "air_leakage_breathiness",
        "effort": "vocal_effort_strain",
        "register": "register_configuration",
        "stability": "phonation_regularity",
        "resonance": "resonance_formant_strategy",
        "onset": "onset_offset_coordination",
        "dynamic_response": "respiratory_phonatory_coordination",
    }

    song_snaps = {
        k: _song_dim_snapshot(dims, eid, k) for k, eid in engine_map.items() if dims.get(eid)
    }
    task_snaps = _extract_task_estimates(task_results)

    # Invalid / missing task coverage for selected dims
    invalid_tasks = [
        tr.get("task_id")
        for tr in task_results
        if tr.get("task_id") and not _task_quality_ok(tr)
    ]

    resolved: dict[str, Any] = {}
    remaining: list[str] = []
    contextual: list[dict[str, Any]] = []
    confidence_delta: list[dict[str, Any]] = []

    target_dims = set(unresolved_before) | set(task_snaps.keys()) | set(song_snaps.keys())
    for dim in sorted(target_dims, key=lambda d: list(engine_map.keys()).index(d) if d in engine_map else 99):
        s = song_snaps.get(dim)
        t = task_snaps.get(dim)
        conflict = compare_contexts(s or {}, t or {}) if (s and t) else None
        if conflict:
            contextual.append(conflict)

        song_c = (s or {}).get("confidence_score") or 0.0
        task_c = (t or {}).get("confidence_score") or 0.0
        task_valid = bool(t and t.get("valid"))

        if task_valid and dim in unresolved_before:
            # Evidence-based confidence: take max of song/task, never fixed bonus
            final_c = max(song_c, task_c)
            # Slight blend weight toward task only when task conf higher — not average of estimates
            final_status = (t or {}).get("status") if task_c >= song_c else (s or {}).get("status")
            resolved[dim] = {
                "dimension": dim,
                "label": DIMENSION_USER_LABELS.get(dim, dim),
                "baseline": t,
                "song": s,
                "final_status": final_status,
                "song_confidence": song_c,
                "task_confidence": task_c,
                "final_confidence": final_c,
                "resolved": True,
                "mode": "task_confirms_or_contextualizes",
            }
            confidence_delta.append(
                {
                    "dimension": dim,
                    "label": DIMENSION_USER_LABELS.get(dim, dim),
                    "song_confidence": round(song_c, 2),
                    "task_confidence": round(task_c, 2),
                    "final_confidence": round(final_c, 2),
                }
            )
        elif conflict:
            resolved[dim] = {
                "dimension": dim,
                "label": DIMENSION_USER_LABELS.get(dim, dim),
                "baseline": t,
                "song": s,
                "final_status": "context_dependent",
                "song_confidence": song_c,
                "task_confidence": task_c,
                "final_confidence": max(song_c, task_c),
                "resolved": False,
                "mode": "contextual_difference",
            }
            remaining.append(dim)
        elif dim in unresolved_before:
            # No valid task evidence → uncertainty remains
            remaining.append(dim)
            resolved[dim] = {
                "dimension": dim,
                "label": DIMENSION_USER_LABELS.get(dim, dim),
                "baseline": t,
                "song": s,
                "final_status": (s or {}).get("status"),
                "song_confidence": song_c,
                "task_confidence": task_c if task_valid else None,
                "final_confidence": song_c,
                "resolved": False,
                "mode": "uncertainty_remains",
            }
        elif s or t:
            resolved[dim] = {
                "dimension": dim,
                "label": DIMENSION_USER_LABELS.get(dim, dim),
                "baseline": t,
                "song": s,
                "final_status": (t or s or {}).get("status"),
                "song_confidence": song_c,
                "task_confidence": task_c if t else None,
                "final_confidence": max(song_c, task_c) if t else song_c,
                "resolved": True,
                "mode": "already_resolved_or_observed",
            }

    baseline_profile = {k: v for k, v in task_snaps.items()}
    song_out = {k: v for k, v in song_snaps.items()}

    return {
        "planner_version": PLANNER_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "report_version": REPORT_VERSION,
        "baseline_profile": baseline_profile,
        "song_profile": song_out,
        "contextual_differences": contextual,
        "resolved_dimensions": {k: v for k, v in resolved.items() if v.get("resolved")},
        "remaining_uncertainties": remaining,
        "task_evidence": {
            "selected_tasks": selected_tasks,
            "task_ids_present": [tr.get("task_id") for tr in task_results if tr.get("task_id")],
            "invalid_tasks": invalid_tasks,
        },
        "confidence_delta": confidence_delta,
        "fusion_rules": {
            "blind_average": False,
            "fixed_confidence_bonus": False,
            "invalid_task_boosts_confidence": False,
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
    )
    labels_resolved = [
        DIMENSION_USER_LABELS.get(d, d) for d in (fused.get("resolved_dimensions") or {})
    ]
    labels_remain = [
        DIMENSION_USER_LABELS.get(d, d) for d in (fused.get("remaining_uncertainties") or [])
    ]
    confirmed = "·".join(labels_resolved[:3]) if labels_resolved else None
    fused["user_summary"] = {
        "headline": "정밀 발성 진단",
        "confirmed_line": (
            f"이번 추가 측정으로 {confirmed}을(를) 더 분명하게 확인했어요."
            if confirmed
            else "추가 측정으로 확인된 항목이 있어요."
            if task_results
            else "이번 음원에서는 추가 표준 녹음 없이 주요 특성을 확인했어요."
        ),
        "remaining_line": (
            f"추가 확인이 남은 항목: {' · '.join(labels_remain)}"
            if labels_remain
            else None
        ),
        "confidence_note": "분석 신뢰도는 측정 근거에 따라 달라지며, 정확도 %가 아닙니다.",
    }
    return fused
