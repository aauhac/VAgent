"""Select primary/secondary bottlenecks — hard provenance + criteria gates."""

from __future__ import annotations

from typing import Any, Optional


def select_primary(
    hypotheses: list[dict[str, Any]],
    *,
    user_goal: str = "GENERAL_EASE_AND_CONTROL",
    criteria_matrix: Optional[list[dict[str, Any]]] = None,
) -> tuple[Optional[dict[str, Any]], list[dict[str, Any]]]:
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
    """
    from audio_analyzer.vocal_function.criteria_registry import (
        BOTTLENECK_DIMENSION,
        coaching_min_required,
    )

    by_dim = {r["dimension_id"]: r for r in (criteria_matrix or [])}
    usable = []
    rejected_for_criteria = []
    for h in hypotheses:
        if h.get("id") == "_MEASUREMENT_ONLY":
            continue
        if h.get("support_level") == "not_supported":
            continue
        if h.get("confidence_label") not in ("medium", "high"):
            continue
        if not (h.get("supporting_episode_ids") or []):
            continue
        if not h.get("supporting_evidence"):
            continue
        if h.get("eligibility") == "NEEDS_MEASUREMENT":
            continue

        dim_id = BOTTLENECK_DIMENSION.get(h.get("id") or "")
        crow = by_dim.get(dim_id) if dim_id else None
        if criteria_matrix is not None and crow is not None:
            if crow.get("coaching_eligibility") != "YES":
                rejected_for_criteria.append(
                    {
                        "id": h.get("id"),
                        "reason": "criteria_not_coaching_eligible",
                        "sufficiency": crow.get("measurement_sufficiency"),
                        "eligibility": crow.get("coaching_eligibility"),
                    }
                )
                continue
            if int(crow.get("required_satisfied") or 0) < coaching_min_required(dim_id):
                rejected_for_criteria.append(
                    {
                        "id": h.get("id"),
                        "reason": "required_criteria_below_minimum",
                        "satisfied": crow.get("required_satisfied"),
                        "minimum": coaching_min_required(dim_id),
                    }
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
                    rejected_for_criteria.append(
                        {"id": h.get("id"), "reason": "register_core_span_missing"}
                    )
                    continue

        usable.append(h)

    if not usable:
        return None, []
    primary = usable[0]
    primary = dict(primary)
    primary["_criteria_reject_log"] = rejected_for_criteria
    secondary = usable[1:3]
    return primary, secondary


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
