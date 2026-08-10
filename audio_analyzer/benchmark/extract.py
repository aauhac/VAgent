"""
audio_analyzer/benchmark/extract.py
-----------------------------------
Extract raw / mapped / axis tables from an analysis result dict.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

SUBMETRICS = [
    "sustain_pitch_stability",
    "sustain_level_stability",
    "region_consistency",
    "unstable_region_ratio",
    "stability_worst_region",
    "spectral_projection",
    "presence_prominence",
    "projection_consistency",
    "weak_projection_segment_ratio",
    "projection_worst_segment",
    "weight_balance",
    "mid_resonance_balance",
    "spectral_slope_balance",
    "resonance_consistency",
    "extreme_resonance_ratio",
    "resonance_worst_segment",
    "global_dynamic_range",
    "local_dynamic_variation",
    "smoothness",
    "phrase_consistency",
    "abrupt_change_ratio",
    "dynamic_worst_segment",
]

AXES = ["stability", "projection", "resonance", "dynamic_control"]


def _area_map(analysis: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        a.get("area_id"): a
        for a in ((analysis.get("score") or {}).get("areas") or [])
        if a.get("area_id")
    }


def _sub_map(analysis: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out = {}
    for a in ((analysis.get("score") or {}).get("areas") or []):
        for sm in a.get("submetrics") or []:
            sid = sm.get("submetric_id")
            if sid:
                out[sid] = sm
    return out


def _percentile(vals: list[float], q: float) -> Optional[float]:
    if not vals:
        return None
    return float(np.quantile(np.asarray(vals, dtype=float), q))


def extract_raw_features(analysis: dict[str, Any], *, mode: str) -> dict[str, Any]:
    """mode: raw | vocal (label only; analysis already computed in that mode)."""
    quality = analysis.get("quality") or {}
    phon = (analysis.get("features") or {}).get("phonation") or {}
    acoustic = ((analysis.get("features") or {}).get("spectral") or {}).get(
        "acoustic_metrics"
    ) or {}
    waveform = (analysis.get("features") or {}).get("waveform") or {}
    areas = _area_map(analysis)
    subs = _sub_map(analysis)
    audio = analysis.get("audio") or {}

    regions = list(phon.get("sustained_regions") or [])
    residuals = [
        float(r["residual_std_cents"])
        for r in regions
        if r.get("residual_std_cents") is not None
    ]
    region_scores = []
    for a_id in ("stability",):
        for seg in (areas.get(a_id) or {}).get("segment_scores") or []:
            if seg.get("score") is not None:
                region_scores.append(float(seg["score"]))

    stab_temp = (areas.get("stability") or {}).get("temporal") or {}
    proj_temp = (areas.get("projection") or {}).get("temporal") or {}
    res_temp = (areas.get("resonance") or {}).get("temporal") or {}
    dyn_temp = (areas.get("dynamic_control") or {}).get("temporal") or {}

    # Segment spectral metrics if present on analysis score debug — else None
    proj_segs = (areas.get("projection") or {}).get("segment_scores") or []
    # acoustic global
    row = {
        "mode": mode,
        "voiced_ratio": phon.get("voiced_ratio")
        or ((analysis.get("features") or {}).get("phonation") or {}).get("voiced_ratio"),
        "quality_status": quality.get("status"),
        "quality_confidence": quality.get("confidence"),
        "source_mode": audio.get("source_mode"),
        "separation_used": bool((audio.get("separation") or {}).get("used")),
        "duration_sec": audio.get("duration_sec"),
        "score_duration_sec": audio.get("score_duration_sec"),
        "duration_policy": (audio.get("duration_policy") or {}).get("policy"),
        # stability raw
        "residual_median": phon.get("median_residual_std_cents"),
        "residual_p75": _percentile(residuals, 0.75),
        "residual_p90": _percentile(residuals, 0.90),
        "region_score_median": _percentile(region_scores, 0.5),
        "stability_worst": stab_temp.get("worst"),
        "stability_bad_ratio": stab_temp.get("bad_segment_ratio"),
        "sustained_count": phon.get("sustained_count"),
        "sustained_duration_proxy": sum(
            float(r.get("duration_sec") or 0) for r in regions
        ),
        "median_rms_variation_db": phon.get("median_rms_variation_db"),
        # projection / resonance acoustic
        "spr_db": acoustic.get("spr_db"),
        "singer_formant_prominence_db": acoustic.get("singer_formant_prominence_db"),
        "weight_gap_db": acoustic.get("weight_gap_db"),
        "mouth_gap_db": acoustic.get("mouth_gap_db"),
        "spectral_slope_db_per_oct": acoustic.get("spectral_slope_db_per_oct"),
        "projection_worst": proj_temp.get("worst"),
        "projection_bad_ratio": proj_temp.get("bad_segment_ratio"),
        "resonance_worst": res_temp.get("worst"),
        "resonance_bad_ratio": res_temp.get("bad_segment_ratio"),
        # dynamic
        "global_dynamic_range_db": waveform.get("dynamic_range_db"),
        "dynamic_worst": dyn_temp.get("worst"),
        "dynamic_bad_ratio": dyn_temp.get("bad_segment_ratio"),
        "smoothness_raw": (subs.get("smoothness") or {}).get("raw_value"),
        "abrupt_ratio": (subs.get("abrupt_change_ratio") or {}).get("raw_value"),
        "local_dyn_raw": (subs.get("local_dynamic_variation") or {}).get("raw_value"),
        "n_proj_segments": len(proj_segs),
    }
    # vocal dominance proxy from separation energy if available in fingerprints
    fp = analysis.get("fingerprints") or {}
    # leave None unless computed elsewhere
    row["vocal_dominance_proxy"] = fp.get("vocal_dominance_proxy")
    return row


def extract_mapped_features(analysis: dict[str, Any], *, mode: str) -> dict[str, Any]:
    subs = _sub_map(analysis)
    row: dict[str, Any] = {"mode": mode}
    for sid in SUBMETRICS:
        sm = subs.get(sid) or {}
        row[f"{sid}_score"] = sm.get("score")
        row[f"{sid}_raw"] = sm.get("raw_value")
        row[f"{sid}_confidence"] = sm.get("confidence")
    return row


def extract_axis_scores(analysis: dict[str, Any], *, mode: str) -> dict[str, Any]:
    areas = _area_map(analysis)
    score = analysis.get("score") or {}
    row: dict[str, Any] = {
        "mode": mode,
        "overall_internal": score.get("overall"),
        "overall_coverage": score.get("overall_coverage"),
        "overall_confidence": score.get("overall_confidence"),
        "score_available": score.get("available"),
    }
    reliable = 0
    for aid in AXES:
        a = areas.get(aid) or {}
        row[f"{aid}_score"] = a.get("score")
        row[f"{aid}_status"] = a.get("status")
        row[f"{aid}_confidence"] = a.get("confidence")
        row[f"{aid}_coverage"] = a.get("coverage")
        if a.get("score") is not None and a.get("status") != "unknown":
            reliable += 1
    row["reliable_axis_count"] = reliable
    row["overall_primary"] = score.get("overall") if reliable >= 3 else None
    return row


def unknown_flags(analysis: dict[str, Any]) -> dict[str, bool]:
    areas = _area_map(analysis)
    return {
        aid: (
            (areas.get(aid) or {}).get("status") == "unknown"
            or (areas.get(aid) or {}).get("score") is None
        )
        for aid in AXES
    }


def run_analysis(
    file_path: str,
    *,
    output_dir: str,
    recording_id: str,
    separate: bool,
) -> dict[str, Any]:
    from audio_analyzer.pipeline import analyze_audio

    return analyze_audio(
        file_path,
        output_dir=output_dir,
        recording_id=recording_id,
        separate=separate,
        build_preview=False,
        include_feedback=False,
    )
