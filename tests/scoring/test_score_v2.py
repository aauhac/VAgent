"""Scoring v2 unit tests."""

from audio_analyzer.scoring.score_v2 import (
    compute_score_v2,
    score_target_range,
    status_from_score,
)


def test_four_axes_present():
    score = compute_score_v2(
        phonation={
            "median_residual_std_cents": 15.0,
            "sustained_count": 4,
            "median_rms_variation_db": 2.0,
        },
        acoustic={
            "spr_db": 21.0,
            "singer_formant_prominence_db": 7.0,
            "weight_gap_db": 2.0,
            "mouth_gap_db": 3.0,
            "spectral_slope_db_per_oct": -12.0,
        },
        waveform={"dynamic_range_db": 16.0},
        quality={"status": "pass"},
        source_mode="raw",
    )
    assert score["available"] is True
    assert score["version"] == "vocal-score-v2.0"
    assert score["calibration_status"] == "uncalibrated"
    ids = [a["area_id"] for a in score["areas"]]
    assert ids == ["stability", "projection", "resonance", "dynamic_control"]
    assert "vibrato" not in ids


def test_dynamic_control_is_target_range():
    # Mid range good
    assert score_target_range(15.0, 8.0, 28.0, 3.0, 40.0) == 100.0
    # Too small not automatically 100
    assert score_target_range(2.0, 8.0, 28.0, 3.0, 40.0) < 50.0


def test_unknown_status():
    assert status_from_score(95.0, 0.1) == "unknown"
    assert status_from_score(95.0, 0.9) == "excellent"
