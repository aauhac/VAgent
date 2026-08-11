"""Adaptive Precision Diagnostic planner (deterministic, no LLM).

Selects the minimum set of standardized tasks that cover song-level
dimension uncertainty. Uncertainty ≠ abnormality.
"""

from __future__ import annotations

from typing import Any, Optional

from audio_analyzer.diagnostic.task_registry import (
    DIMENSION_ALIASES,
    DIMENSION_PRIORITY,
    DIMENSION_USER_LABELS,
    PLANNER_VERSION,
    PROTOCOL_VERSION,
    TASK_REGISTRY,
    normalize_recommended_task,
    user_labels_for_dimensions,
)

# Song engine dimension_id → planner key
_ENGINE_TO_PLANNER = {v: k for k, v in DIMENSION_ALIASES.items() if k != "roughness"}
_ENGINE_TO_PLANNER["phonation_regularity"] = "stability"

# Issue ids from measurement_candidates → planner dimension
_ISSUE_TO_DIM = {
    "EXCESS_EFFORT_HIGH_NOTE": "effort",
    "effort": "effort",
    "AIR_LEAK_BREATHINESS": "breathiness",
    "breathiness": "breathiness",
    "CONTACT_LIGHT": "contact",
    "CONTACT_FIRM": "contact",
    "contact": "contact",
    "REGISTER_TRANSITION_DISRUPTION": "register",
    "register": "register",
    "ROUGHNESS": "stability",
    "roughness": "stability",
    "stability": "stability",
    "RESONANCE_HIGH_NOTE_COLLAPSE": "resonance",
    "resonance": "resonance",
    "onset": "onset",
    "ABRUPT_ONSET": "onset",
}


def _confidence_rank(label: Optional[str]) -> int:
    m = {"high": 3, "medium": 2, "low": 1, "unknown": 0, None: 0}
    return m.get((label or "").lower(), 0)


def _resolve_state(row: dict[str, Any]) -> str:
    """Map criteria-matrix row → RESOLVED | PARTIALLY_RESOLVED | UNRESOLVED | UNAVAILABLE."""
    suf = (row.get("measurement_sufficiency") or "").upper()
    finding = (row.get("finding") or "").upper()
    elig = (row.get("coaching_eligibility") or "").upper()
    conf = _confidence_rank(row.get("confidence_label"))
    req_t = int(row.get("required_total") or 0)
    req_s = int(row.get("required_satisfied") or 0)

    if suf == "UNAVAILABLE":
        return "UNAVAILABLE"
    if suf in ("INSUFFICIENT",) or finding == "UNDETERMINED":
        return "UNRESOLVED"
    if elig in ("NEEDS_MEASUREMENT", "BLOCKED_INSUFFICIENT"):
        return "UNRESOLVED"
    if conf <= 1 and suf != "SUFFICIENT":
        return "UNRESOLVED"
    if conf <= 1:
        return "PARTIALLY_RESOLVED"
    if req_t and req_s < req_t:
        return "PARTIALLY_RESOLVED"
    if suf == "SUFFICIENT" and conf >= 2 and finding not in ("UNDETERMINED",):
        return "RESOLVED"
    if suf == "PARTIAL":
        return "PARTIALLY_RESOLVED"
    return "PARTIALLY_RESOLVED"


def build_uncertainty_profile(
    *,
    criteria_matrix: Optional[list[dict[str, Any]]] = None,
    dimensions: Optional[dict[str, Any]] = None,
    measurement_candidates: Optional[list[dict[str, Any]]] = None,
    song_context: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Build planner-readable uncertainty profile from song analysis."""
    criteria_matrix = criteria_matrix or []
    dimensions = dimensions or {}
    measurement_candidates = measurement_candidates or []
    song_context = song_context or {}

    by_engine = {r.get("dimension_id"): r for r in criteria_matrix if r.get("dimension_id")}
    entries: list[dict[str, Any]] = []

    for planner_key in DIMENSION_PRIORITY:
        engine_id = DIMENSION_ALIASES.get(planner_key, planner_key)
        row = by_engine.get(engine_id) or {}
        dim = dimensions.get(engine_id) or {}
        if not row and dim:
            # Fallback from dimension alone
            conf = dim.get("confidence_label") or "low"
            status = (dim.get("status") or "UNKNOWN").upper()
            state = (
                "UNRESOLVED"
                if status in ("UNKNOWN",) or _confidence_rank(conf) <= 1
                else "RESOLVED"
                if _confidence_rank(conf) >= 2 and status not in ("UNKNOWN",)
                else "PARTIALLY_RESOLVED"
            )
            miss = []
            req_s = req_t = 0
            suf = "INSUFFICIENT" if state == "UNRESOLVED" else "SUFFICIENT"
            estimate = dim.get("summary") or dim.get("status")
            conf_label = conf
        elif row:
            state = _resolve_state(row)
            miss = [
                c.get("criterion_id")
                for c in (row.get("criteria") or [])
                if c.get("required") and c.get("availability") in ("INSUFFICIENT", "NOT_AVAILABLE")
            ]
            req_s = int(row.get("required_satisfied") or 0)
            req_t = int(row.get("required_total") or 0)
            suf = row.get("measurement_sufficiency")
            estimate = row.get("finding") or dim.get("status")
            conf_label = row.get("confidence_label") or dim.get("confidence_label")
        else:
            continue

        entries.append(
            {
                "dimension_id": planner_key,
                "engine_dimension_id": engine_id,
                "state": state,
                "estimate": estimate,
                "confidence": conf_label,
                "measurement_sufficiency": suf,
                "required_satisfied": req_s,
                "required_total": req_t,
                "missing_criteria": miss,
                "song_context": song_context,
            }
        )

    # measurement_candidates can force UNRESOLVED / add candidate tasks
    cand_by_dim: dict[str, list[dict[str, Any]]] = {}
    unsupported: list[dict[str, Any]] = []
    for m in measurement_candidates:
        issue = m.get("issue") or m.get("id")
        dim_key = _ISSUE_TO_DIM.get(str(issue or ""), None)
        norm = normalize_recommended_task(m.get("recommended_task"))
        if not norm.get("supported"):
            unsupported.append({**m, "normalize": norm})
        if dim_key:
            cand_by_dim.setdefault(dim_key, []).append({**m, "normalize": norm})
            for e in entries:
                if e["dimension_id"] == dim_key and e["state"] == "RESOLVED":
                    # needs_confirmation soft-demotes only when eligibility says so
                    if (m.get("eligibility") or "").upper() in (
                        "NEEDS_MEASUREMENT",
                        "LOW_CONFIDENCE",
                    ):
                        e["state"] = "PARTIALLY_RESOLVED"
                elif e["dimension_id"] == dim_key and e["state"] != "UNAVAILABLE":
                    if (m.get("eligibility") or "").upper() == "NEEDS_MEASUREMENT":
                        e["state"] = "UNRESOLVED"

    for e in entries:
        e["measurement_candidates"] = cand_by_dim.get(e["dimension_id"]) or []

    unresolved = [e for e in entries if e["state"] in ("UNRESOLVED", "PARTIALLY_RESOLVED")]
    # Planner targets UNRESOLVED first; PARTIALLY only if still needs confirmation
    target = [e for e in entries if e["state"] == "UNRESOLVED"]
    # Include PARTIALLY when confidence low
    for e in entries:
        if e["state"] == "PARTIALLY_RESOLVED" and _confidence_rank(e.get("confidence")) <= 1:
            if e not in target:
                target.append(e)

    return {
        "planner_version": PLANNER_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "dimensions": entries,
        "unresolved_dimensions": [e["dimension_id"] for e in target],
        "resolved_dimensions": [e["dimension_id"] for e in entries if e["state"] == "RESOLVED"],
        "partial_dimensions": [
            e["dimension_id"] for e in entries if e["state"] == "PARTIALLY_RESOLVED"
        ],
        "unsupported_recommendations": unsupported,
    }


def _task_gain(task_id: str, remaining: set[str]) -> float:
    meta = TASK_REGISTRY.get(task_id) or {}
    gains = meta.get("expected_gain") or {}
    primary = set(meta.get("covers") or [])
    score = 0.0
    for d in remaining:
        g = float(gains.get(d) or 0.0)
        if d in primary:
            score += g
        elif g > 0:
            score += g * 0.5
    # Priority bonus
    for i, d in enumerate(DIMENSION_PRIORITY):
        if d in remaining and d in primary:
            score += 0.15 * (len(DIMENSION_PRIORITY) - i) / len(DIMENSION_PRIORITY)
    return score


def select_diagnostic_tasks(
    uncertainty_profile: dict[str, Any],
    *,
    fallback_all_if_empty_song: bool = False,
    force_tasks: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Greedy set-cover: minimize recordings while maximizing unresolved coverage."""
    if force_tasks is not None:
        selected = [t for t in force_tasks if t in TASK_REGISTRY]
        return {
            "planner_version": PLANNER_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "resolved_dimensions": uncertainty_profile.get("resolved_dimensions") or [],
            "unresolved_dimensions": uncertainty_profile.get("unresolved_dimensions") or [],
            "selected_tasks": selected,
            "expected_coverage": {t: task_covers_primary(t) for t in selected},
            "rationale": {"mode": "forced", "tasks": selected},
        }

    remaining = set(uncertainty_profile.get("unresolved_dimensions") or [])
    if not remaining and fallback_all_if_empty_song:
        selected = list(TASK_REGISTRY.keys())
        return {
            "planner_version": PLANNER_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "resolved_dimensions": [],
            "unresolved_dimensions": [],
            "selected_tasks": selected,
            "expected_coverage": {t: task_covers_primary(t) for t in selected},
            "rationale": {"mode": "standalone_full_battery"},
        }

    selected: list[str] = []
    coverage: dict[str, list[str]] = {}
    rationale_steps: list[dict[str, Any]] = []
    available = list(TASK_REGISTRY.keys())

    while remaining:
        best_id = None
        best_score = 0.0
        for tid in available:
            if tid in selected:
                continue
            # Must cover at least one primary remaining dim
            primary = set((TASK_REGISTRY[tid].get("covers") or []))
            if not (primary & remaining):
                # allow secondary-only only if nothing else can cover
                gains = TASK_REGISTRY[tid].get("expected_gain") or {}
                if not any(d in remaining and float(gains.get(d) or 0) >= 0.5 for d in remaining):
                    continue
            score = _task_gain(tid, remaining) / float(TASK_REGISTRY[tid].get("cost") or 1.0)
            if score > best_score:
                best_score = score
                best_id = tid
        if best_id is None or best_score <= 0:
            break
        selected.append(best_id)
        covered = set(TASK_REGISTRY[best_id].get("covers") or [])
        # Also remove dims with high secondary gain when selected for them
        gains = TASK_REGISTRY[best_id].get("expected_gain") or {}
        for d in list(remaining):
            if d in covered or float(gains.get(d) or 0) >= 0.7:
                remaining.discard(d)
        coverage[best_id] = sorted(covered)
        rationale_steps.append(
            {
                "selected": best_id,
                "gain": round(best_score, 3),
                "covers": sorted(covered),
                "remaining_after": sorted(remaining),
            }
        )

    # Stable order: registry order
    order = list(TASK_REGISTRY.keys())
    selected = sorted(selected, key=lambda t: order.index(t) if t in order else 99)

    return {
        "planner_version": PLANNER_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "resolved_dimensions": uncertainty_profile.get("resolved_dimensions") or [],
        "unresolved_dimensions": uncertainty_profile.get("unresolved_dimensions") or [],
        "selected_tasks": selected,
        "expected_coverage": coverage,
        "rationale": {"mode": "set_cover", "steps": rationale_steps},
        "debug": {
            "dimension_states": [
                {"dimension": e["dimension_id"], "state": e["state"], "confidence": e.get("confidence")}
                for e in (uncertainty_profile.get("dimensions") or [])
            ],
            "unsupported": uncertainty_profile.get("unsupported_recommendations") or [],
        },
    }


def task_covers_primary(task_id: str) -> list[str]:
    return list((TASK_REGISTRY.get(task_id) or {}).get("covers") or [])


def explain_task_selection(plan: dict[str, Any]) -> dict[str, Any]:
    """User-safe explanation (no criterion ids)."""
    unresolved = plan.get("unresolved_dimensions") or []
    selected = plan.get("selected_tasks") or []
    labels = user_labels_for_dimensions(unresolved)
    purposes = []
    for tid in selected:
        meta = TASK_REGISTRY.get(tid) or {}
        purposes.append(
            {
                "task_id": tid,
                "purpose_labels": meta.get("purpose_labels") or [],
            }
        )
    n = len(selected)
    if n == 0:
        cta = (
            "이번 음원에서는 주요 발성 특성이 이미 충분히 확인됐어요."
        )
        lead = "추가 표준 녹음이 필수는 아니에요."
    else:
        joined = "·".join(labels[:3]) if labels else "일부 발성 요소"
        cta = (
            f"노래만으로 확인하기 어려운 부분이 있어요. "
            f"{joined}은(는) 이번 노래만으로 구분하기 어려웠어요. "
            f"짧은 표준 발성 {n}가지를 추가하면 이 부분을 더 정밀하게 확인할 수 있어요."
        )
        lead = f"이번에 확인할 항목: {' · '.join(labels[:4])}" if labels else "추가 확인"
    est_min = max(1, int(round(n * 0.75))) if n else 0
    return {
        "lead": lead,
        "cta_text": cta,
        "unresolved_labels": labels,
        "task_purposes": purposes,
        "selected_task_count": n,
        "estimated_duration_text": f"약 {est_min}분" if n else "추가 녹음 없음",
        "diagnostic_offer": {
            "unresolved_count": len(unresolved),
            "unresolved_labels": labels,
            "selected_task_count": n,
            "estimated_duration_text": f"약 {est_min}분" if n else "추가 녹음 없음",
            "required": n > 0,
            "required_tasks": n > 0,
        },
    }


def plan_from_song_analysis(song: dict[str, Any]) -> dict[str, Any]:
    """Convenience: song public/internal analysis → full plan + UX copy."""
    vf = song.get("vocal_function_profile") or song.get("vocal_function") or {}
    if not vf and isinstance(song.get("report"), dict):
        vf = (song["report"].get("vocal_function_profile") or {})
    criteria = vf.get("criteria_matrix") or song.get("criteria_matrix") or []
    dims = vf.get("dimensions") or {}
    coach = vf.get("coaching_decision") or {}
    cands = coach.get("measurement_candidates") or vf.get("measurement_candidates") or []
    profile = build_uncertainty_profile(
        criteria_matrix=criteria,
        dimensions=dims,
        measurement_candidates=cands,
        song_context={"has_song": True},
    )
    plan = select_diagnostic_tasks(profile)
    explain = explain_task_selection(plan)
    return {**plan, **explain, "uncertainty_profile": profile}
