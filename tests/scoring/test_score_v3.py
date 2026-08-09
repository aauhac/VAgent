"""Song performance scoring v3 — hierarchical precision tests."""

from __future__ import annotations

import numpy as np

from audio_analyzer.scoring.config_v3 import SCORE_VERSION
from audio_analyzer.scoring.helpers_v3 import (
    apply_bad_ratio_penalty,
    apply_score_ceilings,
    apply_worst_segment_penalty,
    score_abs_deviation,
    score_piecewise,
)
from audio_analyzer.scoring import config_v3 as cfg
from audio_analyzer.scoring.score_v3 import compute_score_v3


def _base_kwargs(**over):
    kw = dict(
        phonation={
            "median_residual_std_cents": 16.0,
            "median_rms_variation_db": 2.5,
            "sustained_count": 4,
            "sustained_regions": [
                {
                    "start_sec": i * 2.0,
                    "end_sec": i * 2.0 + 1.2,
                    "duration_sec": 1.2,
                    "residual_std_cents": 16.0 + i,
                    "rms_variation_db": 2.5,
                }
                for i in range(4)
            ],
        },
        acoustic={
            "spr_db": 21.0,
            "singer_formant_prominence_db": 6.0,
            "weight_gap_db": 2.0,
            "mouth_gap_db": 3.0,
            "spectral_slope_db_per_oct": -12.0,
        },
        waveform={
            "dynamic_range_db": 16.0,
            "per_second_summary": [
                {"second": i, "rms_mean": 0.05 + 0.02 * (i % 3), "peak": 0.2}
                for i in range(12)
            ],
        },
        quality={"status": "pass", "codes": []},
        source_mode="raw",
        artifact_flags={},
    )
    kw.update(over)
    return kw


def test_version_v3():
    s = compute_score_v3(**_base_kwargs())
    assert s["version"] == SCORE_VERSION == "vocal-score-v3.0"
    assert s["calibration_status"] == "uncalibrated"
    assert len(s["areas"]) == 4


def test_case_a_average_metrics_not_100():
    s = compute_score_v3(**_base_kwargs())
    for a in s["areas"]:
        if a["score"] is not None:
            assert a["score"] < 100.0


def test_case_b_one_elite_metric_not_95_plus_axis():
    # Only pitch elite; levels/consistency middling
    ph = {
        "sustained_count": 3,
        "sustained_regions": [
            {
                "start_sec": 0,
                "end_sec": 1.5,
                "duration_sec": 1.5,
                "residual_std_cents": 7.0,
                "rms_variation_db": 5.5,
            },
            {
                "start_sec": 2,
                "end_sec": 3.5,
                "duration_sec": 1.5,
                "residual_std_cents": 8.0,
                "rms_variation_db": 6.0,
            },
            {
                "start_sec": 4,
                "end_sec": 5.5,
                "duration_sec": 1.5,
                "residual_std_cents": 28.0,
                "rms_variation_db": 7.0,
            },
        ],
    }
    s = compute_score_v3(**_base_kwargs(phonation=ph))
    stab = next(a for a in s["areas"] if a["area_id"] == "stability")
    assert stab["score"] is None or stab["score"] < 95.0


def test_case_c_elite_but_low_coverage_no_100():
    ph = {
        "sustained_count": 1,
        "sustained_regions": [
            {
                "start_sec": 0,
                "end_sec": 0.8,
                "duration_sec": 0.8,
                "residual_std_cents": 7.0,
                "rms_variation_db": 1.0,
            }
        ],
    }
    s = compute_score_v3(**_base_kwargs(phonation=ph))
    stab = next(a for a in s["areas"] if a["area_id"] == "stability")
    if stab["score"] is not None:
        assert stab["score"] < 100.0
        assert stab["coverage"] < 0.9 or "coverage" in " ".join(stab.get("ceiling_reasons") or [])


def test_case_d_worst_segment_blocks_100():
    base = 94.0
    penalized = apply_worst_segment_penalty(base, 50.0)
    assert penalized < base
    final, ceil, reasons = apply_score_ceilings(
        penalized,
        coverage=0.95,
        confidence=0.9,
        submetric_scores=[95, 95, 95, 95, 50],
        required_count=4,
        worst_segment=50.0,
        bad_ratio=0.05,
    )
    assert final < 100
    assert ceil <= 99


def test_case_e_high_bad_ratio_reduces():
    scored = apply_bad_ratio_penalty(95.0, 0.4)
    assert scored < 95.0


def test_case_f_elite_path_can_reach_100():
    # Construct after ceilings with all elite conditions
    final, ceil, reasons = apply_score_ceilings(
        98.0,
        coverage=0.95,
        confidence=0.9,
        submetric_scores=[92, 93, 91, 94, 95],
        required_count=4,
        worst_segment=92.0,
        bad_ratio=0.02,
        contradiction=False,
    )
    assert ceil == 100.0
    assert final >= 98.0


def test_case_g_partial_unknown_submetrics():
    s = compute_score_v3(
        **_base_kwargs(
            acoustic={
                "spr_db": 22.0,
                "singer_formant_prominence_db": None,
                "weight_gap_db": None,
                "mouth_gap_db": None,
                "spectral_slope_db_per_oct": None,
            }
        )
    )
    proj = next(a for a in s["areas"] if a["area_id"] == "projection")
    # partial submetric may still exist
    assert any(sm.get("score") is not None for sm in proj["submetrics"]) or proj["status"] == "unknown"


def test_case_h_weak_projection_limits_overall():
    s = compute_score_v3(
        **_base_kwargs(
            acoustic={
                "spr_db": 34.0,
                "singer_formant_prominence_db": 0.2,
                "weight_gap_db": 2.0,
                "mouth_gap_db": 3.0,
                "spectral_slope_db_per_oct": -12.0,
            }
        )
    )
    if s["available"] and s["overall"] is not None:
        proj = next(a for a in s["areas"] if a["area_id"] == "projection")
        if proj["score"] is not None and proj["score"] < 55:
            assert s["overall"] < 90.0


def test_case_i_missing_axis_reduces_overall_coverage():
    s = compute_score_v3(
        **_base_kwargs(
            phonation={"sustained_count": 0, "sustained_regions": []},
        )
    )
    assert s.get("overall_coverage") is not None
    stab = next(a for a in s["areas"] if a["area_id"] == "stability")
    assert stab["status"] == "unknown" or stab["coverage"] < 0.5


def test_case_j_quality_warn_affects_confidence_not_arbitrary_raw_cut():
    a = compute_score_v3(**_base_kwargs(quality={"status": "pass", "codes": []}))
    b = compute_score_v3(**_base_kwargs(quality={"status": "warn", "codes": ["CLIPPING"]}))
    dyn_a = next(x for x in a["areas"] if x["area_id"] == "dynamic_control")
    dyn_b = next(x for x in b["areas"] if x["area_id"] == "dynamic_control")
    assert dyn_b["confidence"] < dyn_a["confidence"]


def test_piecewise_no_flat_100_band():
    # Center of dynamic range should not be automatic 100
    sc = score_abs_deviation(16.0, cfg.DYNAMIC_RANGE_CENTER, cfg.DYNAMIC_RANGE_DEV_ANCHORS)
    assert sc < 100.0
    # Edge of old "good" band also not auto-100
    sc2 = score_abs_deviation(8.0, cfg.DYNAMIC_RANGE_CENTER, cfg.DYNAMIC_RANGE_DEV_ANCHORS)
    assert sc2 < 100.0


def test_no_v3_helper_returns_100_for_entire_target_range():
    # Search: score_piecewise at "good" SPR 22.6 should not be 100
    sc = score_piecewise(22.6, cfg.PROJECTION_SPR_ANCHORS, lower_is_better=True)
    assert sc < 100.0


def test_submetrics_present_on_axes():
    s = compute_score_v3(**_base_kwargs())
    for a in s["areas"]:
        assert "submetrics" in a
        assert "coverage" in a
        assert "temporal" in a
