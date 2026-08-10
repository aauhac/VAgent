"""Evidence graph helpers — Observation → family → hypothesis → alternatives."""

from __future__ import annotations

from typing import Any, Optional


def evidence_node(
    *,
    observation_ids: list[str],
    families: list[str],
    hypothesis: str,
    alternatives: list[str],
    confidence_cap: str,
    grade: str,
    time_range: Optional[tuple[float, float]] = None,
    rule_id: str,
) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "observation_ids": observation_ids,
        "evidence_families": families,
        "functional_hypothesis": hypothesis,
        "alternative_explanations": alternatives,
        "confidence_cap": confidence_cap,
        "grade": grade,
        "time_range": {"start_sec": time_range[0], "end_sec": time_range[1]} if time_range else None,
        "layer": "LEVEL_3_FUNCTIONAL_STATE_ESTIMATE",
    }


def count_families(flags: dict[str, bool]) -> int:
    return sum(1 for v in flags.values() if v)
