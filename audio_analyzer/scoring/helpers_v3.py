"""
scoring/helpers_v3.py
---------------------
Piecewise curves, ceilings, worst-segment / bad-ratio penalties.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

import numpy as np

from . import config_v3 as cfg


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def score_piecewise(
    value: float,
    anchors: Sequence[tuple[float, float]],
    *,
    lower_is_better: bool,
) -> float:
    """
    Multi-point engineering curve.
    Anchors are (raw, score). Sorted automatically by raw for the direction.
    Never saturates an entire target band to 100.
    """
    if not anchors:
        return 0.0
    pts = sorted(anchors, key=lambda a: a[0], reverse=not lower_is_better)
    # Normalize to ascending raw for interpolation
    ordered = sorted(anchors, key=lambda a: a[0])
    raws = [p[0] for p in ordered]
    scores = [p[1] for p in ordered]
    v = float(value)
    if v <= raws[0]:
        return clamp(scores[0])
    if v >= raws[-1]:
        return clamp(scores[-1])
    for i in range(len(raws) - 1):
        if raws[i] <= v <= raws[i + 1]:
            t = (v - raws[i]) / (raws[i + 1] - raws[i] + 1e-12)
            return clamp(scores[i] + t * (scores[i + 1] - scores[i]))
    return clamp(scores[-1])


def score_abs_deviation(
    value: float,
    center: float,
    anchors: Sequence[tuple[float, float]],
) -> float:
    """Map |value - center| through lower-is-better anchors."""
    return score_piecewise(abs(float(value) - float(center)), anchors, lower_is_better=True)


def coverage_ceiling(coverage: float) -> float:
    c = float(coverage)
    for thr, ceil in cfg.COVERAGE_CEILINGS:
        if c >= thr:
            return float(ceil)
    return 70.0


def confidence_ceiling(confidence: float) -> float:
    c = float(confidence)
    for thr, ceil in cfg.CONFIDENCE_CEILINGS:
        if c >= thr:
            return float(ceil)
    return 0.0


def apply_worst_segment_penalty(base_score: float, worst_segment: Optional[float]) -> float:
    if worst_segment is None:
        return float(base_score)
    w = float(worst_segment)
    scale = 0.78
    for thr, sc in cfg.WORST_SEGMENT_PENALTY:
        if w >= thr:
            scale = sc
            break
    return clamp(float(base_score) * scale)


def apply_bad_ratio_penalty(score: float, bad_ratio: Optional[float]) -> float:
    if bad_ratio is None:
        return float(score)
    r = float(bad_ratio)
    scale = 0.75
    for thr, sc in cfg.BAD_RATIO_PENALTY:
        if r <= thr:
            scale = sc
            break
    return clamp(float(score) * scale)


def elite_100_eligible(
    *,
    submetric_scores: list[Optional[float]],
    required_count: int,
    coverage: float,
    confidence: float,
    worst_segment: Optional[float],
    bad_ratio: Optional[float],
    contradiction: bool = False,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    valid = [s for s in submetric_scores if s is not None]
    if len(valid) < required_count:
        reasons.append("required_submetrics_incomplete")
    elif any(s < cfg.ELITE_100["min_required_submetric_score"] for s in valid):
        reasons.append("submetric_below_elite")
    if coverage < cfg.ELITE_100["min_coverage"]:
        reasons.append("coverage_below_elite")
    if confidence < cfg.ELITE_100["min_confidence"]:
        reasons.append("confidence_below_elite")
    if worst_segment is None or worst_segment < cfg.ELITE_100["min_worst_segment"]:
        reasons.append("worst_segment_below_elite")
    if bad_ratio is None or bad_ratio > cfg.ELITE_100["max_bad_segment_ratio"]:
        reasons.append("bad_ratio_above_elite")
    if contradiction:
        reasons.append("severe_contradiction")
    return (len(reasons) == 0), reasons


def apply_score_ceilings(
    score: float,
    *,
    coverage: float,
    confidence: float,
    submetric_scores: list[Optional[float]],
    required_count: int,
    worst_segment: Optional[float],
    bad_ratio: Optional[float],
    contradiction: bool = False,
) -> tuple[float, float, list[str]]:
    """Returns (final_score, ceiling, ceiling_reasons)."""
    reasons: list[str] = []
    ceil = 100.0
    cov_c = coverage_ceiling(coverage)
    if cov_c < ceil:
        ceil = cov_c
        reasons.append(f"coverage_ceiling:{cov_c}")
    conf_c = confidence_ceiling(confidence)
    if conf_c < ceil:
        ceil = conf_c
        reasons.append(f"confidence_ceiling:{conf_c}")

    eligible, elite_reasons = elite_100_eligible(
        submetric_scores=submetric_scores,
        required_count=required_count,
        coverage=coverage,
        confidence=confidence,
        worst_segment=worst_segment,
        bad_ratio=bad_ratio,
        contradiction=contradiction,
    )
    if not eligible and ceil > cfg.ELITE_100["fail_ceiling"]:
        ceil = cfg.ELITE_100["fail_ceiling"]
        reasons.extend(elite_reasons)

    final = min(float(score), ceil)
    return clamp(final), ceil, reasons


def distribution_stats(values: Sequence[float]) -> dict[str, Any]:
    arr = np.asarray(list(values), dtype=float)
    if arr.size == 0:
        return {
            "median": None,
            "p25": None,
            "p75": None,
            "p90": None,
            "worst": None,
            "std": None,
            "iqr": None,
            "count": 0,
        }
    p25, p75 = np.percentile(arr, [25, 75])
    return {
        "median": round(float(np.median(arr)), 3),
        "p25": round(float(p25), 3),
        "p75": round(float(p75), 3),
        "p90": round(float(np.percentile(arr, 90)), 3),
        "worst": round(float(np.min(arr)), 3),
        "std": round(float(np.std(arr)), 3),
        "iqr": round(float(p75 - p25), 3),
        "count": int(arr.size),
    }


def weighted_mean_skip_none(
    items: list[tuple[Optional[float], float]],
) -> Optional[float]:
    num = 0.0
    den = 0.0
    for score, w in items:
        if score is None:
            continue
        num += float(score) * float(w)
        den += float(w)
    if den <= 0:
        return None
    return num / den


def geometric_mean_positive(scores: list[float], weights: list[float] | None = None) -> Optional[float]:
    vals = [max(1e-6, float(s)) for s in scores if s is not None]
    if not vals:
        return None
    if weights is None:
        return float(np.exp(np.mean(np.log(vals))))
    w = np.asarray(weights[: len(vals)], dtype=float)
    w = w / (np.sum(w) + 1e-12)
    return float(np.exp(np.sum(w * np.log(vals))))
