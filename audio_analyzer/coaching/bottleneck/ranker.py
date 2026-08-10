"""Select primary/secondary bottlenecks — hard provenance rules (v2.2)."""

from __future__ import annotations

from typing import Any, Optional


def select_primary(
    hypotheses: list[dict[str, Any]],
    *,
    user_goal: str = "GENERAL_EASE_AND_CONTROL",
) -> tuple[Optional[dict[str, Any]], list[dict[str, Any]]]:
    """
    PRIMARY requires ALL of:
      confidence in {medium, high}
      supporting_episode_ids >= 1
      supporting_evidence non-empty
      eligibility != NEEDS_MEASUREMENT (if set)
      not _MEASUREMENT_ONLY placeholder

    LOW confidence NEVER becomes primary — even if goal impact is HIGH.
    """
    usable = []
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
        usable.append(h)

    if not usable:
        return None, []
    primary = usable[0]
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
    # dedupe by issue
    seen = set()
    deduped = []
    for m in out:
        key = m.get("issue")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(m)
    return deduped
