"""
scoring/score_v3.py
-------------------
Hierarchical precision scoring for Song Performance (v3).

Raw metrics → submetrics → temporal / worst / coverage / confidence → axis → overall

Does NOT touch physiology diagnostic inference.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from . import config_v3 as cfg
from .helpers_v3 import (
    apply_bad_ratio_penalty,
    apply_score_ceilings,
    apply_worst_segment_penalty,
    clamp,
    distribution_stats,
    geometric_mean_positive,
    score_abs_deviation,
    score_piecewise,
    weighted_mean_skip_none,
)
from .segments_v3 import compute_dynamic_segments, compute_spectral_segments


def status_from_score(score: Optional[float], confidence: float) -> str:
    if score is None or confidence < cfg.UNKNOWN_CONFIDENCE:
        return "unknown"
    if score >= cfg.STATUS_THRESHOLDS["excellent"]:
        return "excellent"
    if score >= cfg.STATUS_THRESHOLDS["good"]:
        return "good"
    if score >= cfg.STATUS_THRESHOLDS["normal"]:
        return "normal"
    return "needs_work"


def status_label(score: Optional[float], status: str) -> str:
    if status == "unknown" or score is None:
        return "판단 어려움"
    for thr, label in cfg.STATUS_BANDS:
        if score >= thr:
            return label
    return cfg.STATUS_BANDS[-1][1]


def overall_label(score: float) -> str:
    for threshold, label in cfg.OVERALL_LABELS:
        if score >= threshold:
            return label
    return cfg.OVERALL_LABELS[-1][1]


def _sub(
    submetric_id: str,
    score: Optional[float],
    *,
    confidence: float,
    coverage: float,
    raw_value: Any = None,
    unit: str = "",
    temporal_consistency: Optional[float] = None,
    worst_segment_score: Optional[float] = None,
    evidence: Optional[dict] = None,
    limitations: Optional[list] = None,
) -> dict[str, Any]:
    st = status_from_score(score, confidence)
    return {
        "submetric_id": submetric_id,
        "display_name": cfg.SUBMETRIC_DISPLAY.get(submetric_id, submetric_id),
        "score": None if score is None else round(float(score), 1),
        "status": st,
        "confidence": round(float(confidence), 3),
        "coverage": round(float(coverage), 3),
        "raw_value": raw_value,
        "unit": unit,
        "temporal_consistency": temporal_consistency,
        "worst_segment_score": (
            None if worst_segment_score is None else round(float(worst_segment_score), 1)
        ),
        "evidence": evidence or {},
        "limitations": limitations or [],
    }


def _apply_quality_penalties(area_id: str, confidence: float, codes: list[str]) -> float:
    conf = float(confidence)
    for code in codes:
        table = cfg.QUALITY_CODE_PENALTIES.get(code) or {}
        scale = table.get(area_id)
        if scale is not None:
            conf *= float(scale)
    return conf


def _weights_for(area_id: str) -> dict[str, float]:
    return {
        "stability": cfg.STABILITY_WEIGHTS,
        "projection": cfg.PROJECTION_WEIGHTS,
        "resonance": cfg.RESONANCE_WEIGHTS,
        "dynamic_control": cfg.DYNAMIC_WEIGHTS,
    }[area_id]


def _finalize_axis(
    area_id: str,
    *,
    base_score: Optional[float],
    submetrics: list[dict[str, Any]],
    coverage: float,
    confidence: float,
    temporal: dict[str, Any],
    segment_scores: list[dict[str, Any]],
    contradiction: bool = False,
    evidence: Optional[dict] = None,
) -> dict[str, Any]:
    weights = _weights_for(area_id)
    required = max(2, (len(weights) + 1) // 2)

    conf = float(confidence)
    if conf < cfg.UNKNOWN_CONFIDENCE:
        return {
            "area_id": area_id,
            "display_name": cfg.AREA_DISPLAY[area_id],
            "score": None,
            "status": "unknown",
            "status_label": "판단 어려움",
            "confidence": round(conf, 3),
            "coverage": round(float(coverage), 3),
            "submetrics": submetrics,
            "temporal": temporal,
            "segment_scores": segment_scores[:20],
            "score_ceiling": 0.0,
            "ceiling_reasons": ["confidence_below_unknown"],
            "weight": cfg.AREA_WEIGHTS[area_id],
            "evidence": evidence or {},
            "confidence_reason": "insufficient_confidence",
        }

    if base_score is None:
        return {
            "area_id": area_id,
            "display_name": cfg.AREA_DISPLAY[area_id],
            "score": None,
            "status": "unknown",
            "status_label": "판단 어려움",
            "confidence": round(conf, 3),
            "coverage": round(float(coverage), 3),
            "submetrics": submetrics,
            "temporal": temporal,
            "segment_scores": segment_scores[:20],
            "score_ceiling": 0.0,
            "ceiling_reasons": ["no_valid_submetrics"],
            "weight": cfg.AREA_WEIGHTS[area_id],
            "evidence": evidence or {},
            "confidence_reason": "missing_submetrics",
        }

    worst = temporal.get("worst")
    bad_ratio = temporal.get("bad_segment_ratio")
    scored = apply_worst_segment_penalty(base_score, worst)
    scored = apply_bad_ratio_penalty(scored, bad_ratio)

    sub_scores = [s.get("score") for s in submetrics]
    final, ceil, reasons = apply_score_ceilings(
        scored,
        coverage=coverage,
        confidence=conf,
        submetric_scores=sub_scores,
        required_count=required,
        worst_segment=worst,
        bad_ratio=bad_ratio,
        contradiction=contradiction,
    )
    st = status_from_score(final, conf)
    return {
        "area_id": area_id,
        "display_name": cfg.AREA_DISPLAY[area_id],
        "score": round(float(final), 1),
        "status": st,
        "status_label": status_label(final, st),
        "confidence": round(conf, 3),
        "coverage": round(float(coverage), 3),
        "submetrics": submetrics,
        "temporal": temporal,
        "segment_scores": segment_scores[:20],
        "score_ceiling": round(float(ceil), 1),
        "ceiling_reasons": reasons,
        "weight": cfg.AREA_WEIGHTS[area_id],
        "evidence": evidence or {},
        "confidence_reason": "ok" if conf >= 0.55 else "moderate_confidence",
    }


def _score_stability(phonation: dict[str, Any], quality: dict[str, Any]) -> dict[str, Any]:
    regions = list(phonation.get("sustained_regions") or [])
    residuals = [
        float(r["residual_std_cents"])
        for r in regions
        if r.get("residual_std_cents") is not None
    ]
    levels = [
        float(r["rms_variation_db"])
        for r in regions
        if r.get("rms_variation_db") is not None
    ]
    durations = [float(r.get("duration_sec") or 0) for r in regions]
    total_sustain = sum(durations)
    coverage = clamp(
        total_sustain / max(cfg.STABILITY_TARGET_SUSTAIN_SEC, 1e-6), 0.0, 1.0
    ) if regions else 0.0

    region_pitch_scores = [
        score_piecewise(v, cfg.STABILITY_PITCH_ANCHORS, lower_is_better=True) for v in residuals
    ]
    region_level_scores = [
        score_piecewise(v, cfg.STABILITY_LEVEL_ANCHORS, lower_is_better=True) for v in levels
    ]
    # Combined region score for temporal
    region_scores = []
    for i, r in enumerate(regions):
        ps = region_pitch_scores[i] if i < len(region_pitch_scores) else None
        ls = region_level_scores[i] if i < len(region_level_scores) else None
        if ps is None and ls is None:
            continue
        if ps is None:
            sc = ls
        elif ls is None:
            sc = ps
        else:
            sc = 0.65 * ps + 0.35 * ls
        region_scores.append(float(sc))

    dist = distribution_stats(region_scores)
    bad_ratio = (
        None
        if not region_scores
        else float(np.mean([s < 55.0 for s in region_scores]))
    )
    temporal = {**dist, "bad_segment_ratio": None if bad_ratio is None else round(bad_ratio, 3)}

    pitch_score = (
        None
        if not residuals
        else score_piecewise(
            float(np.median(residuals)), cfg.STABILITY_PITCH_ANCHORS, lower_is_better=True
        )
    )
    level_score = (
        None
        if not levels
        else score_piecewise(
            float(np.median(levels)), cfg.STABILITY_LEVEL_ANCHORS, lower_is_better=True
        )
    )
    consistency = None
    if len(region_scores) >= 2:
        consistency = score_piecewise(
            float(np.std(region_scores)),
            cfg.STABILITY_CONSISTENCY_STD_ANCHORS,
            lower_is_better=True,
        )
    unstable_ratio = None
    if residuals:
        unstable_ratio = float(
            np.mean([r >= cfg.UNSTABLE_REGION_RESIDUAL_THRESHOLD for r in residuals])
        )
    unstable_score = (
        None
        if unstable_ratio is None
        else score_piecewise(
            unstable_ratio, cfg.STABILITY_UNSTABLE_RATIO_ANCHORS, lower_is_better=True
        )
    )
    worst_score = dist.get("worst")

    # Contradiction: median good but many unstable
    contradiction = bool(
        pitch_score is not None
        and pitch_score >= 85
        and unstable_ratio is not None
        and unstable_ratio >= 0.35
    )

    subs = [
        _sub(
            "sustain_pitch_stability",
            pitch_score,
            confidence=0.85 if len(residuals) >= 2 else 0.55,
            coverage=coverage,
            raw_value=None if not residuals else round(float(np.median(residuals)), 2),
            unit="cents",
            worst_segment_score=worst_score,
        ),
        _sub(
            "sustain_level_stability",
            level_score,
            confidence=0.8 if levels else 0.2,
            coverage=coverage if levels else 0.0,
            raw_value=None if not levels else round(float(np.median(levels)), 2),
            unit="dB",
        ),
        _sub(
            "region_consistency",
            consistency,
            confidence=0.75 if consistency is not None else 0.2,
            coverage=min(1.0, len(region_scores) / cfg.STABILITY_MIN_REGIONS_FOR_FULL),
            raw_value=None if len(region_scores) < 2 else round(float(np.std(region_scores)), 2),
            temporal_consistency=None if consistency is None else round(consistency / 100.0, 3),
        ),
        _sub(
            "unstable_region_ratio",
            unstable_score,
            confidence=0.8 if unstable_ratio is not None else 0.2,
            coverage=coverage,
            raw_value=None if unstable_ratio is None else round(unstable_ratio, 3),
            unit="ratio",
        ),
        _sub(
            "stability_worst_region",
            worst_score,
            confidence=0.7 if worst_score is not None else 0.2,
            coverage=coverage,
            raw_value=worst_score,
        ),
    ]

    base = weighted_mean_skip_none(
        [
            (pitch_score, cfg.STABILITY_WEIGHTS["sustain_pitch_stability"]),
            (level_score, cfg.STABILITY_WEIGHTS["sustain_level_stability"]),
            (consistency, cfg.STABILITY_WEIGHTS["region_consistency"]),
            (unstable_score, cfg.STABILITY_WEIGHTS["unstable_region_ratio"]),
            (worst_score, cfg.STABILITY_WEIGHTS["stability_worst_region"]),
        ]
    )

    n_reg = len(residuals)
    if n_reg <= 0 or pitch_score is None:
        conf = 0.2
    elif n_reg == 1:
        conf = 0.62
    elif n_reg == 2:
        conf = 0.78
    else:
        conf = 0.88
    conf *= 0.75 + 0.25 * min(1.0, coverage)
    if contradiction:
        conf *= 0.75
    conf = _apply_quality_penalties("stability", conf, list(quality.get("codes") or []))

    segment_scores = [
        {
            "start_sec": r.get("start_sec"),
            "end_sec": r.get("end_sec"),
            "score": round(region_scores[i], 1) if i < len(region_scores) else None,
            "confidence": 0.8,
        }
        for i, r in enumerate(regions)
        if i < len(region_scores)
    ]

    return _finalize_axis(
        "stability",
        base_score=base,
        submetrics=subs,
        coverage=coverage,
        confidence=conf,
        temporal=temporal,
        segment_scores=segment_scores,
        contradiction=contradiction,
        evidence={
            "sustained_count": len(regions),
            "total_sustain_sec": round(total_sustain, 2),
        },
    )


def _score_from_spectral_segments(
    area_id: str,
    global_acoustic: dict[str, Any],
    spectral_segs: list[dict[str, Any]],
    quality: dict[str, Any],
    *,
    source_mode: str,
    artifact_flags: dict[str, Any],
) -> dict[str, Any]:
    if area_id == "projection":
        return _score_projection(
            global_acoustic, spectral_segs, quality, source_mode, artifact_flags
        )
    return _score_resonance(
        global_acoustic, spectral_segs, quality, source_mode, artifact_flags
    )


def _score_projection(
    acoustic: dict[str, Any],
    segs: list[dict[str, Any]],
    quality: dict[str, Any],
    source_mode: str,
    artifact_flags: dict[str, Any],
) -> dict[str, Any]:
    spr = acoustic.get("spr_db")
    prom = acoustic.get("singer_formant_prominence_db")

    seg_scores = []
    for s in segs:
        parts = []
        if s.get("spr_db") is not None:
            parts.append(
                score_piecewise(float(s["spr_db"]), cfg.PROJECTION_SPR_ANCHORS, lower_is_better=True)
            )
        if s.get("singer_formant_prominence_db") is not None:
            parts.append(
                score_piecewise(
                    float(s["singer_formant_prominence_db"]),
                    cfg.PROJECTION_PROMINENCE_ANCHORS,
                    lower_is_better=False,
                )
            )
        if parts:
            seg_scores.append(float(np.mean(parts)))

    dist = distribution_stats(seg_scores)
    bad_ratio = (
        None
        if not seg_scores
        else float(np.mean([x < cfg.WEAK_PROJECTION_SEGMENT_SCORE for x in seg_scores]))
    )
    temporal = {**dist, "bad_segment_ratio": None if bad_ratio is None else round(bad_ratio, 3)}

    spectral = (
        None
        if spr is None
        else score_piecewise(float(spr), cfg.PROJECTION_SPR_ANCHORS, lower_is_better=True)
    )
    presence = (
        None
        if prom is None
        else score_piecewise(
            float(prom), cfg.PROJECTION_PROMINENCE_ANCHORS, lower_is_better=False
        )
    )
    consistency = None
    if len(seg_scores) >= 2:
        consistency = score_piecewise(
            float(np.std(seg_scores)),
            cfg.STABILITY_CONSISTENCY_STD_ANCHORS,
            lower_is_better=True,
        )
    weak_score = (
        None
        if bad_ratio is None
        else score_piecewise(
            bad_ratio, cfg.STABILITY_UNSTABLE_RATIO_ANCHORS, lower_is_better=True
        )
    )
    worst = dist.get("worst")

    n_valid = sum(x is not None for x in (spectral, presence))
    coverage = 0.0
    if n_valid:
        coverage = 0.45 * (n_valid / 2.0) + 0.55 * min(1.0, len(seg_scores) / 4.0)

    subs = [
        _sub("spectral_projection", spectral, confidence=0.8 if spectral else 0.15, coverage=coverage, raw_value=spr, unit="dB"),
        _sub("presence_prominence", presence, confidence=0.8 if presence else 0.15, coverage=coverage, raw_value=prom, unit="dB"),
        _sub("projection_consistency", consistency, confidence=0.7 if consistency else 0.2, coverage=min(1.0, len(seg_scores) / 4.0)),
        _sub("weak_projection_segment_ratio", weak_score, confidence=0.7 if weak_score else 0.2, coverage=coverage, raw_value=bad_ratio),
        _sub("projection_worst_segment", worst, confidence=0.65 if worst else 0.2, coverage=coverage),
    ]
    base = weighted_mean_skip_none(
        [(subs[i]["score"], list(cfg.PROJECTION_WEIGHTS.values())[i]) for i in range(len(subs))]
    )
    conf = 0.85 * (0.5 + 0.5 * (n_valid / 2.0)) * min(1.0, 0.4 + 0.6 * (len(seg_scores) / 4.0))
    if source_mode == "separated":
        conf *= cfg.SEPARATED_SPECTRAL_CONFIDENCE_SCALE
    if artifact_flags.get("demucs_high_band_loss_likely"):
        conf *= cfg.DEMUCS_HF_LOSS_CONFIDENCE_SCALE
    conf = _apply_quality_penalties("projection", conf, list(quality.get("codes") or []))

    segment_scores = [
        {
            "start_sec": s.get("start_sec"),
            "end_sec": s.get("end_sec"),
            "score": round(seg_scores[i], 1),
            "confidence": 0.75,
        }
        for i, s in enumerate(segs)
        if i < len(seg_scores)
    ]
    return _finalize_axis(
        "projection",
        base_score=base,
        submetrics=subs,
        coverage=coverage,
        confidence=conf,
        temporal=temporal,
        segment_scores=segment_scores,
        evidence={"n_spectral_segments": len(segs), "spr_db": spr, "prominence": prom},
    )


def _score_resonance(
    acoustic: dict[str, Any],
    segs: list[dict[str, Any]],
    quality: dict[str, Any],
    source_mode: str,
    artifact_flags: dict[str, Any],
) -> dict[str, Any]:
    wg = acoustic.get("weight_gap_db")
    mg = acoustic.get("mouth_gap_db")
    sl = acoustic.get("spectral_slope_db_per_oct")

    weight = None if wg is None else score_abs_deviation(float(wg), cfg.RESONANCE_WEIGHT_CENTER, cfg.RESONANCE_ABS_DEV_ANCHORS)
    mid = None if mg is None else score_abs_deviation(float(mg), cfg.RESONANCE_MOUTH_CENTER, cfg.RESONANCE_ABS_DEV_ANCHORS)
    slope = None if sl is None else score_abs_deviation(float(sl), cfg.RESONANCE_SLOPE_CENTER, cfg.RESONANCE_ABS_DEV_ANCHORS)

    seg_scores = []
    for s in segs:
        parts = []
        if s.get("weight_gap_db") is not None:
            parts.append(score_abs_deviation(float(s["weight_gap_db"]), cfg.RESONANCE_WEIGHT_CENTER, cfg.RESONANCE_ABS_DEV_ANCHORS))
        if s.get("mouth_gap_db") is not None:
            parts.append(score_abs_deviation(float(s["mouth_gap_db"]), cfg.RESONANCE_MOUTH_CENTER, cfg.RESONANCE_ABS_DEV_ANCHORS))
        if s.get("spectral_slope_db_per_oct") is not None:
            parts.append(score_abs_deviation(float(s["spectral_slope_db_per_oct"]), cfg.RESONANCE_SLOPE_CENTER, cfg.RESONANCE_ABS_DEV_ANCHORS))
        if parts:
            seg_scores.append(float(np.mean(parts)))

    dist = distribution_stats(seg_scores)
    bad_ratio = None if not seg_scores else float(np.mean([x < cfg.EXTREME_RESONANCE_SEGMENT_SCORE for x in seg_scores]))
    temporal = {**dist, "bad_segment_ratio": None if bad_ratio is None else round(bad_ratio, 3)}
    consistency = None
    if len(seg_scores) >= 2:
        consistency = score_piecewise(float(np.std(seg_scores)), cfg.STABILITY_CONSISTENCY_STD_ANCHORS, lower_is_better=True)
    extreme = None if bad_ratio is None else score_piecewise(bad_ratio, cfg.STABILITY_UNSTABLE_RATIO_ANCHORS, lower_is_better=True)
    worst = dist.get("worst")

    n_valid = sum(x is not None for x in (weight, mid, slope))
    coverage = 0.0
    if n_valid:
        coverage = 0.5 * (n_valid / 3.0) + 0.5 * min(1.0, len(seg_scores) / 4.0)

    subs = [
        _sub("weight_balance", weight, confidence=0.75 if weight else 0.15, coverage=coverage, raw_value=wg, unit="dB"),
        _sub("mid_resonance_balance", mid, confidence=0.75 if mid else 0.15, coverage=coverage, raw_value=mg, unit="dB"),
        _sub("spectral_slope_balance", slope, confidence=0.75 if slope else 0.15, coverage=coverage, raw_value=sl, unit="dB/oct"),
        _sub("resonance_consistency", consistency, confidence=0.7 if consistency else 0.2, coverage=min(1.0, len(seg_scores) / 4.0)),
        _sub("extreme_resonance_ratio", extreme, confidence=0.7 if extreme else 0.2, coverage=coverage, raw_value=bad_ratio),
        _sub("resonance_worst_segment", worst, confidence=0.65 if worst else 0.2, coverage=coverage),
    ]
    base = weighted_mean_skip_none(
        [(subs[i]["score"], list(cfg.RESONANCE_WEIGHTS.values())[i]) for i in range(len(subs))]
    )
    conf = 0.8 * (0.35 + 0.65 * (n_valid / 3.0)) * min(1.0, 0.4 + 0.6 * (len(seg_scores) / 4.0))
    if source_mode == "separated":
        conf *= cfg.SEPARATED_SPECTRAL_CONFIDENCE_SCALE
    if artifact_flags.get("demucs_high_band_loss_likely"):
        conf *= cfg.DEMUCS_HF_LOSS_CONFIDENCE_SCALE
    conf = _apply_quality_penalties("resonance", conf, list(quality.get("codes") or []))

    segment_scores = [
        {"start_sec": s.get("start_sec"), "end_sec": s.get("end_sec"), "score": round(seg_scores[i], 1), "confidence": 0.7}
        for i, s in enumerate(segs)
        if i < len(seg_scores)
    ]
    return _finalize_axis(
        "resonance",
        base_score=base,
        submetrics=subs,
        coverage=coverage,
        confidence=conf,
        temporal=temporal,
        segment_scores=segment_scores,
        evidence={"n_spectral_segments": len(segs)},
    )


def _score_dynamic(
    waveform: dict[str, Any],
    dyn_segs: list[dict[str, Any]],
    quality: dict[str, Any],
) -> dict[str, Any]:
    gdr = waveform.get("dynamic_range_db")
    global_score = (
        None
        if gdr is None
        else score_abs_deviation(float(gdr), cfg.DYNAMIC_RANGE_CENTER, cfg.DYNAMIC_RANGE_DEV_ANCHORS)
    )

    local_drs = [float(s["dynamic_range_db"]) for s in dyn_segs if s.get("dynamic_range_db") is not None]
    abrupt_ratios = [float(s["abrupt_ratio"]) for s in dyn_segs if s.get("abrupt_ratio") is not None]
    local_scores = [
        score_abs_deviation(v, cfg.LOCAL_DYN_CENTER, cfg.LOCAL_DYN_DEV_ANCHORS) for v in local_drs
    ]
    dist = distribution_stats(local_scores)
    bad_ratio = None if not local_scores else float(np.mean([x < 55.0 for x in local_scores]))
    temporal = {**dist, "bad_segment_ratio": None if bad_ratio is None else round(bad_ratio, 3)}

    local_var = None if not local_drs else float(np.mean(local_scores))
    mean_abrupt = None if not abrupt_ratios else float(np.mean(abrupt_ratios))
    smoothness = (
        None
        if mean_abrupt is None
        else score_piecewise(mean_abrupt, cfg.SMOOTHNESS_ABRUPT_ANCHORS, lower_is_better=True)
    )
    phrase = None
    if len(local_scores) >= 2:
        phrase = score_piecewise(
            float(np.std(local_scores)),
            cfg.STABILITY_CONSISTENCY_STD_ANCHORS,
            lower_is_better=True,
        )
    abrupt_score = smoothness  # same mapping
    worst = dist.get("worst")

    coverage = 0.35 * (1.0 if gdr is not None else 0.0) + 0.65 * min(1.0, len(dyn_segs) / 4.0)

    # Soft dynamics note: small global range lowers confidence slightly (not raw score hack)
    conf = 0.82 * min(1.0, 0.4 + 0.6 * (len(dyn_segs) / 4.0))
    if gdr is not None and float(gdr) < 6.0:
        conf *= 0.85
    conf = _apply_quality_penalties("dynamic_control", conf, list(quality.get("codes") or []))

    subs = [
        _sub("global_dynamic_range", global_score, confidence=0.75 if global_score else 0.2, coverage=coverage, raw_value=gdr, unit="dB"),
        _sub("local_dynamic_variation", local_var, confidence=0.75 if local_var else 0.2, coverage=min(1.0, len(dyn_segs) / 4.0), raw_value=None if not local_drs else round(float(np.median(local_drs)), 2)),
        _sub("smoothness", smoothness, confidence=0.75 if smoothness else 0.2, coverage=coverage, raw_value=mean_abrupt),
        _sub("phrase_consistency", phrase, confidence=0.7 if phrase else 0.2, coverage=min(1.0, len(dyn_segs) / 4.0)),
        _sub("abrupt_change_ratio", abrupt_score, confidence=0.7 if abrupt_score else 0.2, coverage=coverage, raw_value=mean_abrupt),
        _sub("dynamic_worst_segment", worst, confidence=0.65 if worst else 0.2, coverage=coverage),
    ]
    base = weighted_mean_skip_none(
        [(subs[i]["score"], list(cfg.DYNAMIC_WEIGHTS.values())[i]) for i in range(len(subs))]
    )
    segment_scores = [
        {
            "start_sec": s.get("start_sec"),
            "end_sec": s.get("end_sec"),
            "score": round(local_scores[i], 1) if i < len(local_scores) else None,
            "confidence": 0.7,
        }
        for i, s in enumerate(dyn_segs)
    ]
    return _finalize_axis(
        "dynamic_control",
        base_score=base,
        submetrics=subs,
        coverage=coverage,
        confidence=conf,
        temporal=temporal,
        segment_scores=segment_scores,
        evidence={"global_dynamic_range_db": gdr, "n_dynamic_segments": len(dyn_segs)},
    )


def _aggregate_overall(areas: list[dict[str, Any]]) -> dict[str, Any]:
    reliable = [
        a
        for a in areas
        if a.get("score") is not None and a.get("confidence", 0) >= cfg.MIN_AREA_CONFIDENCE
    ]
    if len(reliable) < cfg.MIN_AREAS_FOR_OVERALL:
        return {
            "available": False,
            "overall": None,
            "label": None,
            "overall_confidence": round(
                float(np.mean([a.get("confidence") or 0 for a in areas]) if areas else 0), 3
            ),
            "overall_coverage": round(
                float(np.mean([a.get("coverage") or 0 for a in areas]) if areas else 0), 3
            ),
            "provisional": True,
            "reason": "신뢰할 수 있는 측정 영역이 부족함",
        }

    scores = [float(a["score"]) for a in reliable]
    weights = [float(a.get("weight") or 0.25) for a in reliable]
    coverages = [float(a.get("coverage") or 0) for a in reliable]
    confidences = [float(a.get("confidence") or 0) for a in reliable]

    # Confidence × coverage weighted arithmetic
    cw = [w * c * cov for w, c, cov in zip(weights, confidences, coverages)]
    arith = float(np.average(scores, weights=np.asarray(cw) + 1e-9))
    geo = geometric_mean_positive(scores, weights)
    if geo is None:
        blend = arith
    else:
        blend = (
            cfg.OVERALL_ARITHMETIC_WEIGHT * arith
            + cfg.OVERALL_GEOMETRIC_WEIGHT * float(geo)
        )

    weakest = min(scores)
    overall = (1.0 - cfg.WEAKEST_AXIS_BLEND) * blend + cfg.WEAKEST_AXIS_BLEND * weakest

    overall_coverage = float(np.mean([a.get("coverage") or 0 for a in areas]))
    # Missing axes reduce overall coverage
    missing = sum(1 for a in areas if a.get("score") is None)
    overall_coverage *= (len(areas) - 0.5 * missing) / max(len(areas), 1)
    overall_confidence = float(np.mean(confidences))

    # Soft ceiling from overall coverage/confidence (not arbitrary score cut)
    from .helpers_v3 import coverage_ceiling, confidence_ceiling

    ceil = min(coverage_ceiling(overall_coverage), confidence_ceiling(overall_confidence))
    if ceil < 100:
        overall = min(overall, ceil)

    return {
        "available": True,
        "overall": round(float(overall), 1),
        "label": overall_label(overall),
        "overall_confidence": round(overall_confidence, 3),
        "overall_coverage": round(overall_coverage, 3),
        "provisional": True,
        "reason": None,
        "aggregation": {
            "arithmetic": round(arith, 2),
            "geometric": None if geo is None else round(float(geo), 2),
            "weakest_reliable": round(weakest, 2),
            "formula": (
                f"{cfg.OVERALL_ARITHMETIC_WEIGHT}*arith + "
                f"{cfg.OVERALL_GEOMETRIC_WEIGHT}*geo, then "
                f"(1-{cfg.WEAKEST_AXIS_BLEND})*blend + {cfg.WEAKEST_AXIS_BLEND}*weakest"
            ),
        },
    }


def compute_score_v3(
    *,
    phonation: dict[str, Any],
    acoustic: dict[str, Any],
    waveform: dict[str, Any],
    quality: dict[str, Any],
    source_mode: str = "raw",
    artifact_flags: Optional[dict[str, Any]] = None,
    y: Any = None,
    sr: Optional[int] = None,
) -> dict[str, Any]:
    artifact_flags = artifact_flags or {}
    spectral_segs: list[dict[str, Any]] = []
    if y is not None and sr:
        try:
            spectral_segs = compute_spectral_segments(np.asarray(y, dtype=np.float32), int(sr))
        except Exception:
            spectral_segs = []
    dyn_segs = compute_dynamic_segments(waveform, y=y, sr=sr)

    stability = _score_stability(phonation, quality)
    projection = _score_projection(
        acoustic, spectral_segs, quality, source_mode, artifact_flags
    )
    resonance = _score_resonance(
        acoustic, spectral_segs, quality, source_mode, artifact_flags
    )
    dynamic = _score_dynamic(waveform, dyn_segs, quality)
    areas = [stability, projection, resonance, dynamic]

    agg = _aggregate_overall(areas)

    strengths = []
    priority = []
    for a in areas:
        if (
            a["status"] in ("excellent", "good")
            and a["confidence"] >= cfg.STRENGTH_MIN_CONFIDENCE
            and a["score"] is not None
            and float(a["score"]) >= cfg.STRENGTH_MIN_SCORE
        ):
            strengths.append(
                {
                    "area_id": a["area_id"],
                    "display_name": a["display_name"],
                    "score": a["score"],
                    "status": a["status"],
                }
            )
        if a["status"] == "needs_work" and a["score"] is not None:
            priority.append(
                {
                    "area_id": a["area_id"],
                    "display_name": a["display_name"],
                    "score": a["score"],
                    "status": a["status"],
                }
            )
    strengths.sort(key=lambda x: x["score"], reverse=True)
    priority.sort(key=lambda x: x["score"])

    return {
        "available": bool(agg.get("available")),
        "version": cfg.SCORE_VERSION,
        "calibration_status": cfg.CALIBRATION_STATUS,
        "overall": agg.get("overall"),
        "label": agg.get("label"),
        "overall_confidence": agg.get("overall_confidence"),
        "overall_coverage": agg.get("overall_coverage"),
        "provisional": agg.get("provisional", True),
        "areas": areas,
        "strengths": strengths[:3],
        "priority_issues": priority[:3],
        "reason": agg.get("reason"),
        "aggregation": agg.get("aggregation"),
    }
