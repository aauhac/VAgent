"""Select primary/secondary bottlenecks — hard provenance + criteria gates.

Always retains a full primary_rejection_trace (even when primary is None).
"""

from __future__ import annotations

from typing import Any, Optional


def select_primary(
    hypotheses: list[dict[str, Any]],
    *,
    user_goal: str = "GENERAL_EASE_AND_CONTROL",
    criteria_matrix: Optional[list[dict[str, Any]]] = None,
) -> tuple[Optional[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """
    PRIMARY requires ALL of:
      confidence in {medium, high}
      supporting_episode_ids >= 1
      supporting_evidence non-empty
      eligibility != NEEDS_MEASUREMENT (if set)
      not _MEASUREMENT_ONLY placeholder
      criteria matrix coaching_eligibility == YES (when matrix provided)
      required criteria met for that dimension (not merely "others failed")

    LOW confidence NEVER becomes primary — even if goal impact is HIGH.
    Being the only surviving candidate is NOT enough.

    Returns: (primary, secondary, rejection_trace)
    """
    from audio_analyzer.vocal_function.criteria_registry import (
        BOTTLENECK_DIMENSION,
        coaching_min_required,
    )

    by_dim = {r["dimension_id"]: r for r in (criteria_matrix or [])}
    usable = []
    rejection_trace: list[dict[str, Any]] = []

    def _reject(h: dict[str, Any], reason: str, **extra: Any) -> None:
        rejection_trace.append(
            {
                "id": h.get("id"),
                "reason": reason,
                "confidence_label": h.get("confidence_label"),
                "eligibility": h.get("eligibility"),
                "supporting_episode_ids": list(h.get("supporting_episode_ids") or []),
                "n_supporting_episodes": len(h.get("supporting_episode_ids") or []),
                "has_supporting_evidence": bool(h.get("supporting_evidence")),
                **extra,
            }
        )

    for h in hypotheses:
        if h.get("id") == "_MEASUREMENT_ONLY":
            _reject(h, "measurement_only_placeholder")
            continue
        if h.get("support_level") == "not_supported":
            _reject(h, "support_level_not_supported")
            continue
        if h.get("confidence_label") not in ("medium", "high"):
            _reject(h, "confidence_below_medium", confidence_label=h.get("confidence_label"))
            continue
        if not (h.get("supporting_episode_ids") or []):
            _reject(h, "no_supporting_episode")
            continue
        if not h.get("supporting_evidence"):
            _reject(h, "no_supporting_evidence")
            continue
        if h.get("eligibility") == "NEEDS_MEASUREMENT":
            _reject(h, "eligibility_needs_measurement")
            continue

        dim_id = BOTTLENECK_DIMENSION.get(h.get("id") or "")
        crow = by_dim.get(dim_id) if dim_id else None
        if criteria_matrix is not None and crow is not None:
            if crow.get("coaching_eligibility") != "YES":
                _reject(
                    h,
                    "criteria_not_coaching_eligible",
                    sufficiency=crow.get("measurement_sufficiency"),
                    coaching_eligibility=crow.get("coaching_eligibility"),
                    dimension_id=dim_id,
                    required_satisfied=crow.get("required_satisfied"),
                    required_total=crow.get("required_total"),
                )
                continue
            if int(crow.get("required_satisfied") or 0) < coaching_min_required(dim_id):
                _reject(
                    h,
                    "required_criteria_below_minimum",
                    satisfied=crow.get("required_satisfied"),
                    minimum=coaching_min_required(dim_id),
                    dimension_id=dim_id,
                )
                continue
            if dim_id == "register_configuration":
                loc = next(
                    (
                        c
                        for c in (crow.get("criteria") or [])
                        if c.get("criterion_id") == "localization"
                    ),
                    None,
                )
                if not loc or loc.get("availability") != "SUFFICIENT":
                    _reject(h, "register_core_span_missing", dimension_id=dim_id)
                    continue

        usable.append(h)

    if not usable:
        return None, [], rejection_trace
    primary = dict(usable[0])
    primary["_criteria_reject_log"] = [
        r for r in rejection_trace if r.get("reason", "").startswith("criteria")
        or r.get("reason") in (
            "criteria_not_coaching_eligible",
            "required_criteria_below_minimum",
            "register_core_span_missing",
        )
    ]
    secondary = usable[1:3]
    return primary, secondary, rejection_trace


def collect_measurement_candidates(hypotheses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for h in hypotheses:
        for m in h.get("_all_measurement_candidates") or []:
            if m not in out:
                out.append(m)
        if h.get("confidence_label") == "low" and h.get("id") != "_MEASUREMENT_ONLY":
            out.append(
                {
                    "issue": h.get("id"),
                    "reason": h.get("why") or "신뢰도가 낮아 추가 확인이 필요해요.",
                    "recommended_task": "additional_measurement",
                    "eligibility": "NEEDS_MEASUREMENT",
                }
            )
    seen = set()
    deduped = []
    for m in out:
        key = m.get("issue")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(m)
    return deduped
