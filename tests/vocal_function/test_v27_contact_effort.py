"""v2.7 — contact/effort dimension validity, GIF fallback, effort decoupling."""

from __future__ import annotations

from audio_analyzer.vocal_function.evidence.effort_contact import (
    effort_like,
    effort_score,
    firmer_like,
    lighter_like,
)
from audio_analyzer.vocal_function.rules.fusion import fuse_contact, fuse_effort
from audio_analyzer.vocal_function.validity import build_validity_by_dimension, dim_valid


def _seg(
    start,
    end,
    *,
    obs=None,
    src=None,
    valid=True,
    rms=0.05,
    ve=None,
):
    observations = dict(obs or {})
    if rms is not None and "rms" not in observations:
        observations["rms"] = rms
    seg = {
        "start_sec": start,
        "end_sec": end,
        "valid": valid,
        "voiced_ratio": 0.7,
        "observations": observations,
        "vocal_evidence": ve
        or {
            "vocal_specific": True,
            "vocal_dominance": 0.8,
            "vocal_confidence": 0.7,
        },
        "level2_proxies": {
            "glottal_source": src if src is not None else {"valid": False},
            "gif_gate": {"valid": bool((src or {}).get("valid"))},
            "formants": {"valid": True, "confidence": 0.5},
        },
        "rms": rms,
    }
    seg["validity_by_dimension"] = build_validity_by_dimension(seg)
    return seg


def _batch(maker, n=6):
    return [maker(i) for i in range(0, n * 2, 2)]


# --- contact ---


def test_firm_flow_harmonic_contact():
    s = _seg(
        0,
        2,
        obs={"raw_h1_h2_proxy_db": -1.0, "energy_2_4k": 0.2, "periodicity_primary_db": 12},
        src={"valid": True, "estimated_naq": 0.05, "estimated_oq_proxy": 0.4},
    )
    assert firmer_like(s)
    assert dim_valid(s, "glottal_contact")


def test_light_flow_harmonic_contact():
    s = _seg(
        0,
        2,
        obs={"raw_h1_h2_proxy_db": 8.0, "spectral_tilt_db_per_oct": -16.0},
        src={"valid": True, "estimated_naq": 0.18, "estimated_oq_proxy": 0.6},
    )
    assert lighter_like(s)


def test_gif_invalid_multi_family_contact_available_capped():
    segs = _batch(
        lambda i: _seg(
            i,
            i + 2,
            valid=False,
            obs={
                "raw_h1_h2_proxy_db": -1.0,
                "energy_2_4k": 0.22,
                "spectral_tilt_db_per_oct": -8.0,
                "onset_slope_db_per_sec": 40.0,
                "periodicity_primary_db": 8.0,
            },
            src={"valid": False},
        )
    )
    assert all(dim_valid(s, "glottal_contact") for s in segs)
    out = fuse_contact(segs)
    assert out["status"] == "OBSERVED"
    assert out["confidence_label"] == "low"
    assert out["profile"].get("fallback_supported") is True
    assert out["continuum_0_to_1"] is not None


def test_gif_invalid_one_family_contact_unresolved():
    s = _seg(0, 2, obs={"raw_h1_h2_proxy_db": -1.0, "periodicity_primary_db": 10}, src={"valid": False})
    assert dim_valid(s, "glottal_contact") is False
    segs = _batch(lambda i: _seg(i, i + 2, obs={"periodicity_primary_db": 10}, src={"valid": False}))
    out = fuse_contact(segs)
    assert out["status"] in ("UNKNOWN", "AMBIGUOUS")
    assert out["continuum_0_to_1"] is None


def test_contact_firm_alone_effort_low():
    segs = _batch(
        lambda i: _seg(
            i,
            i + 2,
            obs={
                "raw_h1_h2_proxy_db": -1.0,
                "energy_2_4k": 0.2,
                "periodicity_primary_db": 14.0,
                "onset_slope_db_per_sec": 20.0,
                "f0_frame_period_perturbation_proxy_percent": 0.4,
                "rms": 0.05,
            },
            src={"valid": True, "estimated_naq": 0.05, "estimated_oq_proxy": 0.4},
        )
    )
    assert any(firmer_like(s) for s in segs)
    assert not any(effort_like(s) for s in segs)
    effort = fuse_effort(segs, baseline_obs={"rms": 0.05, "energy_24k": 0.12})
    assert effort["status"] == "LOW"


def test_effort_without_firm_contact_intensity_onset():
    baseline = {"rms": 0.04, "energy_24k": 0.1, "n_baseline_segments": 8}
    # Rising intensity + hard onset without firm contact
    seq = [
        (0.04, 25),
        (0.06, 40),
        (0.09, 70),
        (0.13, 100),
        (0.14, 95),
        (0.12, 50),
    ]
    segs = [
        _seg(
            i * 2,
            i * 2 + 2,
            obs={
                "raw_h1_h2_proxy_db": 4.0,
                "energy_2_4k": 0.08,
                "periodicity_primary_db": 12.0,
                "onset_slope_db_per_sec": onset,
                "f0_frame_period_perturbation_proxy_percent": 0.5,
                "rms": rms,
            },
            src={"valid": False},
            rms=rms,
        )
        for i, (rms, onset) in enumerate(seq)
    ]
    assert any(effort_like(s, baseline, pre=segs[i - 1] if i else None, post=segs[i + 1] if i + 1 < len(segs) else None) for i, s in enumerate(segs))
    assert not any(firmer_like(s, baseline) for s in segs)
    out = fuse_effort(segs, baseline_obs=baseline)
    assert out["status"] in ("OCCASIONAL", "MODERATE", "REPEATED")
    assert out["profile"]["effort_hit_segments"] >= 1


def test_roughness_alone_not_high_effort():
    segs = _batch(
        lambda i: _seg(
            i,
            i + 2,
            obs={
                "periodicity_primary_db": 12.0,
                "f0_frame_period_perturbation_proxy_percent": 3.5,
                "onset_slope_db_per_sec": 20.0,
                "rms": 0.05,
                "raw_h1_h2_proxy_db": 3.0,
            },
            src={"valid": False},
        )
    )
    baseline = {"rms": 0.05}
    assert not any(effort_like(s, baseline) for s in segs)
    out = fuse_effort(segs, baseline_obs=baseline)
    assert out["status"] == "LOW"


def test_loud_alone_not_high_effort():
    baseline = {"rms": 0.04}
    segs = _batch(
        lambda i: _seg(
            i,
            i + 2,
            obs={
                "rms": 0.15,
                "periodicity_primary_db": 14.0,
                "onset_slope_db_per_sec": 25.0,
                "raw_h1_h2_proxy_db": 3.0,
                "f0_frame_period_perturbation_proxy_percent": 0.4,
            },
        )
    )
    assert not any(effort_like(s, baseline) for s in segs)


def test_high_f0_alone_not_high_effort():
    segs = _batch(
        lambda i: _seg(
            i,
            i + 2,
            obs={
                "f0_hz": 520.0,
                "periodicity_primary_db": 13.0,
                "onset_slope_db_per_sec": 30.0,
                "rms": 0.05,
                "raw_h1_h2_proxy_db": 3.0,
            },
        )
    )
    assert not any(effort_like(s, {"rms": 0.05}) for s in segs)


def test_firm_plus_rough_onset_effort():
    # Segment-local fallback still allows temporal+regularity core/support path
    segs = _batch(
        lambda i: _seg(
            i,
            i + 2,
            obs={
                "raw_h1_h2_proxy_db": -1.0,
                "energy_2_4k": 0.22,
                "periodicity_primary_db": 5.0,
                "onset_slope_db_per_sec": 90.0,
                "f0_frame_period_perturbation_proxy_percent": 3.0,
                "rms": 0.06,
            },
            src={"valid": True, "estimated_naq": 0.05},
        )
    )
    assert any(effort_like(s) for s in segs)


def test_light_contact_intensity_onset_effort():
    baseline = {"rms": 0.04, "energy_24k": 0.08, "n_baseline_segments": 8}
    seq = [(0.04, 30, 8.0), (0.07, 50, 8.0), (0.10, 80, 8.0), (0.14, 105, 8.0), (0.13, 90, 8.0), (0.08, 40, 8.0)]
    segs = [
        _seg(
            i * 2,
            i * 2 + 2,
            obs={
                "raw_h1_h2_proxy_db": h1,
                "spectral_tilt_db_per_oct": -16.0,
                "energy_2_4k": 0.06,
                "periodicity_primary_db": 11.0,
                "onset_slope_db_per_sec": onset,
                "rms": rms,
            },
            src={"valid": True, "estimated_naq": 0.18, "estimated_oq_proxy": 0.6},
            rms=rms,
        )
        for i, (rms, onset, h1) in enumerate(seq)
    ]
    assert any(lighter_like(s) for s in segs)
    out = fuse_effort(segs, baseline_obs=baseline)
    assert out["status"] in ("OCCASIONAL", "MODERATE", "REPEATED")


def test_global_invalid_but_effort_valid_used_in_fusion():
    baseline = {"rms": 0.04, "n_baseline_segments": 8}
    seq = [(0.04, 30), (0.07, 55), (0.11, 85), (0.15, 100), (0.14, 90), (0.09, 40)]
    segs = [
        _seg(
            i * 2,
            i * 2 + 2,
            valid=False,
            obs={
                "rms": rms,
                "onset_slope_db_per_sec": onset,
                "periodicity_primary_db": 5.0,
                "f0_frame_period_perturbation_proxy_percent": 3.0,
                "energy_2_4k": 0.1,
                "raw_h1_h2_proxy_db": 3.0,
            },
            src={"valid": False},
            ve={"vocal_specific": False, "vocal_dominance": 0.4},
            rms=rms,
        )
        for i, (rms, onset) in enumerate(seq)
    ]
    assert all(not s["valid"] for s in segs)
    assert all(dim_valid(s, "effort") for s in segs)
    out = fuse_effort(segs, baseline_obs=baseline)
    assert out["valid_segment_count"] >= 3
    assert out["status"] in ("OCCASIONAL", "MODERATE", "REPEATED")


def test_global_invalid_contact_fallback_used():
    segs = _batch(
        lambda i: _seg(
            i,
            i + 2,
            valid=False,
            obs={
                "raw_h1_h2_proxy_db": -1.0,
                "energy_2_4k": 0.2,
                "spectral_tilt_db_per_oct": -7.0,
                "onset_slope_db_per_sec": 50.0,
            },
            src={"valid": False},
        )
    )
    assert all(dim_valid(s, "glottal_contact") for s in segs)
    out = fuse_contact(segs)
    assert out["valid_segment_count"] >= 3
    assert out["status"] == "OBSERVED"


def test_versions_bumped():
    from audio_analyzer.vocal_function import config as cfg
    from audio_analyzer.song_detail.report import SONG_DETAIL_REPORT_VERSION

    assert cfg.FUNCTION_ENGINE_VERSION == "vocal-function-v2.9"
    assert cfg.REPORT_VERSION == "vocal-coach-report-v2.9"
    assert SONG_DETAIL_REPORT_VERSION == "vocal-coach-report-v2.9"


def test_effort_score_monotonic_with_families():
    baseline = {"rms": 0.04, "energy_24k": 0.08}
    soft = _seg(0, 2, obs={"rms": 0.04, "onset_slope_db_per_sec": 20, "periodicity_primary_db": 14})
    hard = _seg(
        0,
        2,
        obs={
            "rms": 0.12,
            "onset_slope_db_per_sec": 95,
            "periodicity_primary_db": 5,
            "f0_frame_period_perturbation_proxy_percent": 3.0,
            "energy_2_4k": 0.2,
        },
    )
    assert effort_score(hard, baseline) > effort_score(soft, baseline)
