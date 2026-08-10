"""Select primary/secondary bottlenecks; drop unsupported / low-conf noise."""

from __future__ import annotations

from typing import Any, Optional


def select_primary(
    hypotheses: list[dict[str, Any]],
    *,
    user_goal: str = "GENERAL_EASE_AND_CONTROL",
) -> tuple[Optional[dict[str, Any]], list[dict[str, Any]]]:
    usable = [
        h
        for h in hypotheses
        if h.get("support_level") != "not_supported"
        and h.get("confidence_label") in ("medium", "high")
        and h.get("supporting_evidence")
    ]
    if not usable:
        # allow single medium-low only if impact HIGH for goal
        usable = [
            h
            for h in hypotheses
            if h.get("supporting_evidence") and h.get("impact") == "HIGH"
        ][:1]
    if not usable:
        return None, []
    primary = usable[0]
    secondary = usable[1:3]
    return primary, secondary
