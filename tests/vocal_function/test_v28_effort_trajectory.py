"""v2.8 — effort trajectory, support-only cap, roughness FP, f0 dropout."""

from __future__ import annotations

import numpy as np

from audio_analyzer.vocal_evidence.phonation_quality import classify_rough_segment
from audio_analyzer.vocal_function.evidence.effort_contact import effort_like, firmer_like
from audio_analyzer.vocal_function.evidence.effort_trajectory import (
    compute_effort_event_context,
    extract_micro_intensity_db,
    rms_to_db,
)
from audio_analyzer.vocal_function.observations.segment import _f0_stats
from audio_analyzer.vocal_function.rules.fusion import fuse_effort
from audio_analyzer.vocal_function.validity import build_validity_by_dimension


def _seg(start, end, *, obs=None, src=None, valid=True, rms=0.05):
    observations = dict(obs or {})
    if rms is not None and "rms" not in observations:
        observations["rms"] = rms
    if "intensity_db" not in observations and rms is not None:
        observations["intensity_db"] = rms_to_db(rms)
    seg = {
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
        "level2_proxies": {
            "glottal_source": src if src is not None else {"valid": False},
            "gif_gate": {"valid": bool((src or {}).get("valid"))},
        },
        "rms": rms,
    }
    seg["validity_by_dimension"] = build_validity_by_dimension(seg)
    return seg


def test_constant_loud_low_trajectory():
    # Static loud pre/during/post — no rising trajectory
    pre = _seg(0, 1, rms=0.2, obs={"onset_slope_db_per_sec": 30, "periodicity_primary_db": 14})
    dur = _seg(1, 2, rms=0.21, obs={"onset_slope_db_per_sec": 32, "periodicity_primary_db": 14})
    post = _seg(2, 3, rms=0.2, obs={"onset_slope_db_per_sec": 30, "periodicity_primary_db": 14})
    ctx = compute_effort_event_context(dur, pre=pre, post=post)
    assert ctx["intensity"]["status"] == "STATIC_LOUD"
    assert ctx["elevated"] is False


def test_rising_intensity_trajectory_positive():
    pre = _seg(0, 1, rms=0.03, obs={"onset_slope_db_per_sec": 20, "periodicity_primary_db": 14})
    dur = _seg(1, 2, rms=0.12, obs={"onset_slope_db_per_sec": 25, "periodicity_primary_db": 14})
    ctx = compute_effort_event_context(dur, pre=pre, post=None)
    assert ctx["intensity"]["positive"] is True


def test_rising_plus_fast_recovery_not_elevated_without_other_cost():
    pre = _seg(0, 1, rms=0.03, obs={"onset_slope_db_per_sec": 20, "periodicity_primary_db": 14})
    dur = _seg(1, 2, rms=0.12, obs={"onset_slope_db_per_sec": 25, "periodicity_primary_db": 14})
    post = _seg(2, 3, rms=0.035, obs={"onset_slope_db_per_sec": 20, "periodicity_primary_db": 14})
    ctx = compute_effort_event_context(dur, pre=pre, post=post)
    assert ctx["controlled_crescendo"] is True
    assert ctx["elevated"] is False


def test_rising_plus_attack_elevated():
    pre = _seg(0, 1, rms=0.04, obs={"onset_slope_db_per_sec": 25, "periodicity_primary_db": 14})
    dur = _seg(1, 2, rms=0.14, obs={"onset_slope_db_per_sec": 100, "periodicity_primary_db": 12})
    post = _seg(2, 3, rms=0.12, obs={"onset_slope_db_per_sec": 40, "periodicity_primary_db": 10})
    ctx = compute_effort_event_context(dur, pre=pre, post=post)
    assert ctx["elevated"] is True
    assert ctx["core_family_count"] >= 1


def test_loud_firm_stable_low_effort():
    segs = []
    for i in range(0, 12, 2):
        segs.append(
            _seg(
                i,
                i + 2,
                rms=0.15,
                obs={
                    "raw_h1_h2_proxy_db": -1.0,
                    "energy_2_4k": 0.2,
                    "periodicity_primary_db": 14.0,
                    "onset_slope_db_per_sec": 30.0,
                    "f0_frame_period_perturbation_proxy_percent": 0.5,
                },
                src={"valid": True, "estimated_naq": 0.05, "estimated_oq_proxy": 0.4},
            )
        )
    assert any(firmer_like(s) for s in segs)
    out = fuse_effort(segs, baseline_obs={"rms": 0.14, "energy_24k": 0.18})
    assert out["status"] == "LOW"
    assert (out["profile"].get("effort_score") or 0) < 0.35


def test_regularity_spectral_support_only_not_moderate():
    segs = [
        _seg(
            i,
            i + 2,
            rms=0.06,
            obs={
                "periodicity_primary_db": 5.0,
                "f0_frame_period_perturbation_proxy_percent": 3.5,
                "energy_2_4k": 0.25,
                "onset_slope_db_per_sec": 25.0,
                "raw_h1_h2_proxy_db": 3.0,
            },
        )
        for i in range(0, 12, 2)
    ]
    # Absolute regularity+spectral without trajectory neighbors escalating → not elevated
    assert not any(effort_like(s) for s in segs)
    out = fuse_effort(segs, baseline_obs={"rms": 0.06, "energy_24k": 0.1})
    assert out["status"] == "LOW"


def test_firm_contact_only_not_elevated():
    s = _seg(
        0,
        2,
        obs={
            "raw_h1_h2_proxy_db": -1.0,
            "energy_2_4k": 0.2,
            "periodicity_primary_db": 14,
            "onset_slope_db_per_sec": 20,
        },
        src={"valid": True, "estimated_naq": 0.05},
    )
    assert firmer_like(s)
    assert not effort_like(s)


def test_roughness_only_not_effort():
    s = _seg(
        0,
        2,
        obs={
            "periodicity_primary_db": 12,
            "f0_frame_period_perturbation_proxy_percent": 3.5,
            "onset_slope_db_per_sec": 20,
            "rms": 0.05,
        },
    )
    assert not effort_like(s)


def test_irregularity_alone_not_rough_positive():
    s = _seg(
        0,
        2,
        obs={
            "periodicity_primary_db": 12.0,
            "f0_frame_period_perturbation_proxy_percent": 3.5,
        },
    )
    assert classify_rough_segment(s)["verdict"] != "POSITIVE"


def test_tracker_artifact_rejects_rough():
    s = _seg(
        0,
        2,
        obs={
            "periodicity_primary_db": 12.0,
            "f0_frame_period_perturbation_proxy_percent": 3.5,
            "f0_octave_jump_ratio": 0.25,
            "f0_tracker_artifact": {"suspect": True},
        },
    )
    c = classify_rough_segment(s)
    assert c["verdict"] == "REJECTED"
    assert "artifact" in c["reason"]


def test_f0_dropout_uses_all_frames():
    pitch = {
        "frame_f0": [
            {"time_sec": 0.0, "f0_hz": 100.0},
            {"time_sec": 0.1, "f0_hz": 100.0},
            {"time_sec": 0.2, "f0_hz": None},
            {"time_sec": 0.3, "f0_hz": None},
            {"time_sec": 0.4, "f0_hz": 100.0},
            {"time_sec": 0.5, "f0_hz": 100.0},
            {"time_sec": 0.6, "f0_hz": 100.0},
        ]
    }
    stats = _f0_stats(pitch, 0.0, 0.6)
    assert stats["f0_dropout_ratio"] > 0.0
    assert abs(stats["f0_dropout_ratio"] - (2 / 7)) < 1e-6


def test_micro_intensity_slope_on_ramp():
    sr = 16000
    t = np.linspace(0, 1.0, sr, endpoint=False)
    # Rising amplitude envelope
    env = 0.05 + 0.4 * t
    y = env * np.sin(2 * np.pi * 220 * t)
    out = extract_micro_intensity_db(y, sr)
    assert out["slope_db_per_sec"] is not None
    assert out["slope_db_per_sec"] > 0


def test_escalating_chain_higher_than_static_loud_chain():
    static = [
        _seg(
            i,
            i + 2,
            rms=0.18,
            obs={
                "onset_slope_db_per_sec": 30,
                "periodicity_primary_db": 14,
                "raw_h1_h2_proxy_db": -1.0,
                "energy_2_4k": 0.2,
                "f0_frame_period_perturbation_proxy_percent": 0.5,
            },
            src={"valid": True, "estimated_naq": 0.05},
        )
        for i in range(0, 12, 2)
    ]
    # Escalating intensity + hardening attack + slow recovery mid-chain
    rms_seq = [0.03, 0.06, 0.10, 0.16, 0.18, 0.17]
    onset_seq = [20, 40, 70, 100, 90, 50]
    pert_seq = [0.5, 0.8, 1.5, 3.0, 2.8, 2.5]
    escalate = []
    for i, (rms, onset, pert) in enumerate(zip(rms_seq, onset_seq, pert_seq)):
        escalate.append(
            _seg(
                i * 2,
                i * 2 + 2,
                rms=rms,
                obs={
                    "onset_slope_db_per_sec": onset,
                    "periodicity_primary_db": 12 - i,
                    "f0_frame_period_perturbation_proxy_percent": pert,
                    "energy_2_4k": 0.1 + 0.02 * i,
                    "raw_h1_h2_proxy_db": 2.0,
                },
            )
        )
    a = fuse_effort(static, baseline_obs={"rms": 0.16, "energy_24k": 0.18})
    b = fuse_effort(escalate, baseline_obs={"rms": 0.05, "energy_24k": 0.1})
    assert (b["profile"].get("effort_score") or 0) > (a["profile"].get("effort_score") or 0)
    assert a["status"] == "LOW"
    assert b["status"] in ("OCCASIONAL", "MODERATE", "REPEATED")
