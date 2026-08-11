"""v2.9 — roughness persistence / tracker artifact / breathy contamination."""

from __future__ import annotations

from audio_analyzer.vocal_evidence.phonation_quality import (
    classify_rough_segment,
    disambiguate_breathy_vs_rough,
)
from audio_analyzer.vocal_function.rules.fusion import fuse_regularity
from audio_analyzer.vocal_function.validity import build_validity_by_dimension


def _seg(start, end, *, obs=None, valid=True, rms=0.05):
    observations = dict(obs or {})
    if "rms" not in observations:
        observations["rms"] = rms
    seg = {
        "start": start,
        "end": end,
        "start_sec": start,
        "end_sec": end,
        "valid": valid,
        "voiced_ratio": 0.7,
        "observations": observations,
        "vocal_evidence": {
            "vocal_specific": True,
            "vocal_dominance": 0.8,
            "vocal_confidence": 0.7,
        },
        "level2_proxies": {"glottal_source": {"valid": False}, "gif_gate": {"valid": False}},
        "rms": rms,
    }
    seg["validity_by_dimension"] = build_validity_by_dimension(seg)
    return seg


def _true_rough_obs(**extra):
    base = {
        "periodicity_primary_db": 4.0,
        "f0_frame_period_perturbation_proxy_percent": 3.5,
        "f0_octave_jump_ratio": 0.02,
        "f0_tracker_artifact": {
            "suspect": False,
            "octave_jumps": 0,
            "n_voiced": 12,
            "n_frames": 20,
        },
    }
    base.update(extra)
    return base


def test_periodicity_loss_alone_not_rough():
    s = _seg(0, 1, obs={"periodicity_primary_db": 4.0, "f0_frame_period_perturbation_proxy_percent": 0.4})
    c = classify_rough_segment(s)
    assert c["verdict"] == "REJECTED"
    assert c["reason"] == "periodicity_loss_without_irregularity"


def test_isolated_perturbation_not_strong_rough():
    s = _seg(0, 1, obs={"periodicity_primary_db": 12.0, "f0_frame_period_perturbation_proxy_percent": 4.0})
    c = classify_rough_segment(s)
    assert c["verdict"] != "POSITIVE"


def test_low_confidence_octave_artifact_suppressed():
    s = _seg(
        0,
        1,
        obs={
            "periodicity_primary_db": 4.0,
            "f0_frame_period_perturbation_proxy_percent": 3.5,
            "f0_octave_jump_ratio": 0.25,
            "f0_tracker_artifact": {"suspect": True, "octave_jumps": 3, "n_voiced": 8, "n_frames": 20},
        },
    )
    c = classify_rough_segment(s)
    assert c["verdict"] == "REJECTED"
    assert c["reason"] == "tracker_artifact"


def test_persistent_irregularity_and_periodicity_positive():
    s = _seg(0, 1, obs=_true_rough_obs())
    assert classify_rough_segment(s)["verdict"] == "POSITIVE"


def test_breathy_weak_periodicity_not_rough():
    s = _seg(
        0,
        1,
        obs={
            "periodicity_primary_db": 5.0,
            "raw_h1_h2_proxy_db": 10.0,
            "spectral_tilt_db_per_oct": -18.0,
            "f0_dropout_ratio": 0.25,
            "f0_frame_period_perturbation_proxy_percent": 0.5,
        },
    )
    d = disambiguate_breathy_vs_rough(s)
    assert d["rough"]["verdict"] != "POSITIVE"


def test_fuse_regularity_persistence_events():
    segs = [_seg(i, i + 1, obs=_true_rough_obs()) for i in range(0, 4)]
    out = fuse_regularity(segs)
    assert out["status"] == "REPEATED_IRREGULAR"
    assert out["roughness_persistence"]["n_events"] >= 1
    assert out["roughness_persistence"]["adjacent_run_length"] >= 2


def test_fuse_isolated_singles_intermittent():
    segs = [
        _seg(0, 1, obs=_true_rough_obs()),
        _seg(1, 2, obs={"periodicity_primary_db": 14.0, "f0_frame_period_perturbation_proxy_percent": 0.3}),
        _seg(2, 3, obs={"periodicity_primary_db": 14.0, "f0_frame_period_perturbation_proxy_percent": 0.3}),
        _seg(3, 4, obs={"periodicity_primary_db": 14.0, "f0_frame_period_perturbation_proxy_percent": 0.3}),
        _seg(4, 5, obs={"periodicity_primary_db": 14.0, "f0_frame_period_perturbation_proxy_percent": 0.3}),
        _seg(5, 6, obs={"periodicity_primary_db": 14.0, "f0_frame_period_perturbation_proxy_percent": 0.3}),
        _seg(6, 7, obs={"periodicity_primary_db": 14.0, "f0_frame_period_perturbation_proxy_percent": 0.3}),
        _seg(7, 8, obs={"periodicity_primary_db": 14.0, "f0_frame_period_perturbation_proxy_percent": 0.3}),
        _seg(20, 21, obs=_true_rough_obs()),
    ]
    out = fuse_regularity(segs)
    assert out["status"] in ("INTERMITTENT", "STABLE")
    assert out["roughness_persistence"]["n_events"] <= 2


def test_clean_phonation_dropout_not_rough():
    s = _seg(
        0,
        1,
        obs={
            "periodicity_primary_db": 15.0,
            "f0_frame_period_perturbation_proxy_percent": 3.5,
            "f0_dropout_ratio": 0.25,
            "f0_tracker_artifact": {"suspect": False, "n_voiced": 20, "n_frames": 24, "octave_jumps": 0},
            "f0_octave_jump_ratio": 0.02,
        },
    )
    c = classify_rough_segment(s)
    assert c["verdict"] == "REJECTED"
    assert c["reason"] == "clean_phonation_tracker_noise"


def test_full_frame_dropout_denominator_retained():
    s = _seg(
        0,
        1,
        obs={
            "periodicity_primary_db": 4.0,
            "f0_frame_period_perturbation_proxy_percent": 4.0,
            "f0_dropout_ratio": 0.5,
            "f0_tracker_artifact": {"suspect": False, "n_voiced": 3, "n_frames": 20, "octave_jumps": 0},
        },
    )
    assert classify_rough_segment(s)["verdict"] != "POSITIVE"
