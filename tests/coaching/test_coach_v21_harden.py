"""Coaching Decision Engine v2.1 — P0/P1 harden regression tests."""

from __future__ import annotations

import numpy as np

from audio_analyzer.coaching.bottleneck import build_coaching_decision
from audio_analyzer.coaching.bottleneck.hypotheses import rank_hypotheses
from audio_analyzer.pipeline import _functional_quality_policy
from audio_analyzer.vocal_function.alignment import (
    attach_time_fields,
    build_time_context,
    slice_aligned_stems,
)
from audio_analyzer.vocal_function.engine import compute_contact_effort_plane
from audio_analyzer.vocal_function.episodes.builder import (
    build_high_note_episodes,
    find_best_self_reference,
)
from audio_analyzer.vocal_function.evidence.families import firmer_like


def test_functional_mode_forces_separation_policy():
    q = _functional_quality_policy(
        analysis_mode="FUNCTIONAL",
        input_mode="AUTO",
        source_mode="raw",
        separation_status="failed",
        has_no_vocals=False,
        separation_required=True,
    )
    assert q[0] == "UNAVAILABLE"
    full = _functional_quality_policy(
        analysis_mode="FUNCTIONAL",
        input_mode="MIXED",
        source_mode="separated",
        separation_status="success",
        has_no_vocals=True,
        separation_required=True,
    )
    assert full[0] == "FULL_MIXED"
    quick = _functional_quality_policy(
        analysis_mode="QUICK",
        input_mode="AUTO",
        source_mode="raw",
        separation_status="skipped",
        has_no_vocals=False,
        separation_required=False,
    )
    assert quick[0] == "LIMITED"
    vocal_only = _functional_quality_policy(
        analysis_mode="FUNCTIONAL",
        input_mode="VOCAL_ONLY",
        source_mode="raw",
        separation_status="skipped",
        has_no_vocals=False,
        separation_required=False,
    )
    assert vocal_only[0] == "FULL_VOCAL_ONLY"


def test_long_clip_vocals_no_vocals_aligned():
    sr = 1000
    # 180 sec original; clip 90–135
    yv = np.arange(180 * sr, dtype=np.float32)
    yn = np.arange(180 * sr, dtype=np.float32) + 1000
    aligned = slice_aligned_stems(
        y_vocals_full=yv,
        y_no_vocals_full=yn,
        sr=sr,
        start_sec=90.0,
        end_sec=135.0,
    )
    assert aligned["clip_start_sec"] == 90.0
    # local 5–8 sec → original 95–98
    local_s, local_e = 5.0, 8.0
    origin = aligned["clip_start_sec"]
    assert origin + local_s == 95.0
    assert origin + local_e == 98.0
    i0 = int(local_s * sr)
    i1 = int(local_e * sr)
    # Same relative indices map to same original absolute samples
    assert float(aligned["vocals_clip"][i0]) == float(yv[int(95 * sr)])
    assert float(aligned["no_vocals_clip"][i0]) == float(yn[int(95 * sr)])


def test_local_to_original_conversion():
    ev = attach_time_fields({"start_sec": 5.0, "end_sec": 8.0}, time_origin_sec=90.0)
    assert ev["local_start_sec"] == 5.0
    assert ev["original_start_sec"] == 95.0
    assert ev["original_end_sec"] == 98.0
    ctx = build_time_context(
        duration_policy={"start_sec": 90, "end_sec": 135, "truncated": True},
        original_duration_sec=180,
    )
    assert ctx["analysis_time_origin_sec"] == 90


def test_firm_effort_different_segments_no_cooccurrence():
    # A: firm only (stable period, no secondary effort signs)
    # B: effort secondary signs only (not firm contact)
    segs = [
        {
            "start_sec": 0,
            "end_sec": 1,
            "valid": True,
            "observations": {
                "raw_h1_h2_proxy_db": -2.0,
                "energy_2_4k": 0.25,
                "periodicity_primary_db": 12,
                "rms": 0.05,
                "onset_slope_db_per_sec": 10,
            },
            "level2_proxies": {
                "glottal_source": {
                    "valid": True,
                    "estimated_naq": 0.04,
                    "estimated_mfdr_norm_proxy": 1.0,
                    "estimated_oq_proxy": 0.35,
                }
            },
        },
        {
            "start_sec": 2,
            "end_sec": 3,
            "valid": True,
            "observations": {
                "raw_h1_h2_proxy_db": 8.0,
                "energy_2_4k": 0.05,
                "periodicity_primary_db": 4.0,
                "f0_frame_period_perturbation_proxy_percent": 3.0,
                "rms": 0.2,
                "onset_slope_db_per_sec": 100,
            },
            "level2_proxies": {
                "glottal_source": {
                    "valid": True,
                    "estimated_naq": 0.2,
                    "estimated_mfdr_norm_proxy": 0.5,
                    "estimated_oq_proxy": 0.65,
                }
            },
        },
    ]
    baseline = {"rms": 0.05, "mfdr_norm": 1.0}
    plane = compute_contact_effort_plane(segs, baseline, episodes=[])
    assert plane["firm_segments"] >= 1
    assert plane["effort_segments"] >= 1
    assert plane["firm_effort_overlap_segments"] == 0
    assert plane["firm_high_strain_high"] is False


def test_firm_effort_same_segment_overlap():
    segs = [
        {
            "start_sec": 0,
            "end_sec": 1,
            "valid": True,
            "observations": {
                "raw_h1_h2_proxy_db": -2.0,
                "energy_2_4k": 0.25,
                "periodicity_primary_db": 4.0,
                "f0_frame_period_perturbation_proxy_percent": 3.0,
                "rms": 0.2,
                "onset_slope_db_per_sec": 100,
            },
            "level2_proxies": {
                "glottal_source": {
                    "valid": True,
                    "estimated_naq": 0.04,
                    "estimated_mfdr_norm_proxy": 2.0,
                    "estimated_oq_proxy": 0.35,
                }
            },
        }
    ]
    plane = compute_contact_effort_plane(segs, {"rms": 0.05, "mfdr_norm": 1.0}, [])
    assert plane["firm_effort_overlap_segments"] >= 1
    assert plane["firm_high_strain_high"] is True
    assert plane["firm_effort_overlap_ratio"] > 0


def test_mfdr_gt_zero_alone_not_firm():
    seg = {
        "observations": {"raw_h1_h2_proxy_db": 5.0, "energy_2_4k": 0.05},
        "level2_proxies": {
            "glottal_source": {
                "valid": True,
                "estimated_naq": 0.2,
                "estimated_mfdr_proxy": 999.0,
                "estimated_mfdr_norm_proxy": 0.5,
                "estimated_oq_proxy": 0.6,
            }
        },
    }
    assert firmer_like(seg, {"mfdr_norm": 0.5}) is False


def test_mfdr_relative_rise_with_other_family_eligible():
    seg = {
        "observations": {"raw_h1_h2_proxy_db": -1.0, "energy_2_4k": 0.2},
        "level2_proxies": {
            "glottal_source": {
                "valid": True,
                "estimated_naq": 0.2,
                "estimated_mfdr_norm_proxy": 2.0,
                "estimated_oq_proxy": 0.5,
            }
        },
    }
    # MFDR relative rise + harmonic → firm
    assert firmer_like(seg, {"mfdr_norm": 1.0}) is True


def test_invalid_gif_mfdr_ignored():
    seg = {
        "observations": {"raw_h1_h2_proxy_db": 5.0},
        "level2_proxies": {
            "glottal_source": {
                "valid": False,
                "estimated_mfdr_norm_proxy": 99.0,
                "estimated_naq": 0.01,
            }
        },
    }
    assert firmer_like(seg, {"mfdr_norm": 1.0}) is False


def test_global_effort_no_high_note_no_excess_effort_high_note():
    profile = {
        "dimensions": {
            "vocal_effort_strain": {"status": "REPEATED"},
            "air_leakage_breathiness": {"status": "LOW"},
            "register_configuration": {"status": "STABLE_LIKE", "profile": {"events": []}},
            "onset_offset_coordination": {"status": "BALANCED_LIKE"},
            "phonation_regularity": {"status": "STABLE"},
            "resonance_formant_strategy": {"profile": {}},
            "respiratory_phonatory_coordination": {"status": "STABLE_LIKE"},
            "vibrato_control": {"status": "UNKNOWN"},
            "glottal_contact_profile": {},
        },
        "contact_effort_plane": {},
    }
    hyps = rank_hypotheses(profile, [])
    assert not any(h["id"] == "EXCESS_EFFORT_HIGH_NOTE" for h in hyps)
    # without GENERAL_EFFORT episodes → measurement candidate, not coachable primary
    decision = build_coaching_decision(profile=profile, episodes=[], focus={})
    assert decision["primary_bottleneck"] is None
    assert any(
        (m.get("issue") == "effort") for m in (decision.get("measurement_candidates") or [])
    ) or decision.get("prefer_additional_measurement")


def test_high_note_effort_same_episode_creates_excess_effort_high_note():
    profile = {
        "dimensions": {
            "vocal_effort_strain": {"status": "LOW"},
            "air_leakage_breathiness": {"status": "LOW"},
            "register_configuration": {"status": "STABLE_LIKE", "profile": {"events": []}},
            "onset_offset_coordination": {"status": "BALANCED_LIKE"},
            "phonation_regularity": {"status": "STABLE"},
            "resonance_formant_strategy": {"profile": {}},
            "respiratory_phonatory_coordination": {"status": "STABLE_LIKE"},
            "vibrato_control": {"status": "UNKNOWN"},
            "glottal_contact_profile": {},
        },
        "contact_effort_plane": {},
    }
    eps = [
        {
            "episode_id": "HIGH_NOTE_10.0_14.0",
            "type": "HIGH_NOTE",
            "concern": True,
            "start_sec": 10,
            "end_sec": 14,
            "feature_matrix": {"effort": {"strain_like": 0.8}, "source": {}, "regularity": {}},
        }
    ]
    hyps = rank_hypotheses(profile, eps)
    h = next(x for x in hyps if x["id"] == "EXCESS_EFFORT_HIGH_NOTE")
    assert "HIGH_NOTE_10.0_14.0" in h["supporting_episode_ids"]


def test_register_primary_targets_register_episode():
    profile = {
        "dimensions": {
            "vocal_effort_strain": {"status": "LOW"},
            "air_leakage_breathiness": {"status": "LOW"},
            "register_configuration": {
                "status": "TRANSITION_EVENTS",
                "profile": {
                    "events": [
                        {
                            "start_sec": 5,
                            "end_sec": 7,
                            "validity": {"vocal_specific": True},
                        }
                    ]
                },
            },
            "onset_offset_coordination": {"status": "BALANCED_LIKE"},
            "phonation_regularity": {"status": "STABLE"},
            "resonance_formant_strategy": {"profile": {}},
            "respiratory_phonatory_coordination": {"status": "STABLE_LIKE"},
            "vibrato_control": {"status": "UNKNOWN"},
            "glottal_contact_profile": {},
        },
        "contact_effort_plane": {},
    }
    eps = [
        {
            "episode_id": "HIGH_NOTE_20.0_26.0",
            "type": "HIGH_NOTE",
            "concern": True,
            "start_sec": 20,
            "end_sec": 26,
            "feature_matrix": {"effort": {"strain_like": 0.2}},
        },
        {
            "episode_id": "REGISTER_TRANSITION_5.0_7.0",
            "type": "REGISTER_TRANSITION",
            "start_sec": 5,
            "end_sec": 7,
            "feature_matrix": {},
        },
    ]
    decision = build_coaching_decision(
        profile=profile,
        episodes=eps,
        focus={"primary": [eps[0]]},  # misleading focus — must NOT win
        user_goal="MIX",
    )
    assert decision["primary_bottleneck"]["id"] == "REGISTER_TRANSITION_DISRUPTION"
    assert decision["target_episode"]["type"] == "REGISTER_TRANSITION"
    assert decision["target_episode"]["episode_id"] == "REGISTER_TRANSITION_5.0_7.0"


def test_phase_method_populated():
    windows = [
        {
            "start_sec": 0,
            "end_sec": 1,
            "concern": True,
            "observations": {"f0_hz": 200, "rms": 0.05},
        },
        {
            "start_sec": 1,
            "end_sec": 2,
            "concern": True,
            "observations": {"f0_hz": 400, "rms": 0.08},
        },
        {
            "start_sec": 2,
            "end_sec": 3,
            "concern": False,
            "observations": {"f0_hz": 390, "rms": 0.07},
        },
    ]
    eps = build_high_note_episodes(windows)
    assert eps[0]["phase_method"] in ("ACOUSTIC", "PROVISIONAL")
    assert "phases" in eps[0]


def test_source_vs_resonance_cause_hint():
    # resonance drop without effort → RESONANCE
    windows = [
        {
            "start_sec": i,
            "end_sec": i + 1,
            "concern": False,
            "observations": {
                "f0_hz": 300 + i * 10,
                "energy_2_4k": 0.25 if i < 2 else 0.05,
                "spectral_centroid_hz": 2000 if i < 2 else 1200,
                "periodicity_primary_db": 12,
            },
            "level2_proxies": {"glottal_source": {"valid": True, "estimated_naq": 0.12}},
            "effort_during": "not_elevated",
        }
        for i in range(5)
    ]
    eps = build_high_note_episodes(windows)
    assert eps[0]["cause_hint"] in ("RESONANCE", "MIXED", "UNCLEAR", "SOURCE_EFFORT")


def test_best_self_rejects_mid_as_high_ref():
    high_bad = {
        "episode_id": "HIGH_NOTE_10.0_12.0",
        "type": "HIGH_NOTE",
        "concern": True,
        "start_sec": 10,
        "end_sec": 12,
        "members": [{"observations": {"f0_hz": 450}}],
        "feature_matrix": {
            "effort": {"strain_like": 0.9},
            "regularity": {"periodicity": 6, "roughness": False},
        },
    }
    mid_better = {
        "episode_id": "HIGH_NOTE_1.0_3.0",
        "type": "HIGH_NOTE",
        "concern": False,
        "start_sec": 1,
        "end_sec": 3,
        "members": [{"observations": {"f0_hz": 220}}],
        "feature_matrix": {
            "effort": {"strain_like": 0.1},
            "regularity": {"periodicity": 14, "roughness": False},
        },
    }
    assert find_best_self_reference([high_bad, mid_better]) is None
