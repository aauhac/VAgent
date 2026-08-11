"""Common dimension_evidence schema helpers (diagnostic protocol v1.2)."""

from __future__ import annotations

from typing import Any, Optional


def conf_label_from_score(score: Optional[float]) -> Optional[str]:
    if score is None:
        return None
    s = float(score)
    if s >= 0.75:
        return "high"
    if s >= 0.5:
        return "medium"
    if s >= 0.25:
        return "low"
    return "low"


def empty_evidence(
    dimension_id: str,
    *,
    reason: str,
    quality_valid: bool = False,
) -> dict[str, Any]:
    return {
        "dimension_id": dimension_id,
        "available": False,
        "estimate": None,
        "status": None,
        "confidence_score": None,
        "confidence_label": None,
        "family_count": 0,
        "evidence_families": {},
        "evidence_mass": 0.0,
        "resolution_eligible": False,
        "quality_valid": quality_valid,
        "reason": reason,
        "confidence_source": None,
    }


def make_evidence(
    dimension_id: str,
    *,
    available: bool,
    estimate: Any = None,
    status: Any = None,
    confidence_score: Optional[float] = None,
    family_count: int = 0,
    evidence_families: Optional[dict[str, Any]] = None,
    evidence_mass: float = 0.0,
    resolution_eligible: bool = False,
    quality_valid: bool = True,
    reason: str = "",
    confidence_source: Optional[str] = None,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    out = {
        "dimension_id": dimension_id,
        "available": bool(available),
        "estimate": estimate,
        "status": status,
        "confidence_score": None if confidence_score is None else round(float(confidence_score), 4),
        "confidence_label": conf_label_from_score(confidence_score),
        "family_count": int(family_count),
        "evidence_families": evidence_families or {},
        "evidence_mass": round(float(evidence_mass), 4),
        "resolution_eligible": bool(resolution_eligible and available and quality_valid),
        "quality_valid": bool(quality_valid),
        "reason": reason,
        "confidence_source": confidence_source,
    }
    if extra:
        out.update(extra)
    return out


def obs_map(observations: list[dict[str, Any]] | dict[str, Any] | None) -> dict[str, Any]:
    """Flatten physiology observation list → metric_id → value dict."""
    if not observations:
        return {}
    if isinstance(observations, dict):
        return dict(observations)
    out: dict[str, Any] = {}
    for m in observations:
        if not isinstance(m, dict):
            continue
        mid = m.get("metric_id") or m.get("id")
        if mid:
            out[str(mid)] = m
    return out


def metric_value(omap: dict[str, Any], metric_id: str) -> Any:
    m = omap.get(metric_id) or {}
    if not m.get("valid", True) and m.get("value") is None:
        return None
    return m.get("value")
