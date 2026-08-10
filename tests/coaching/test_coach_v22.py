"""Coaching Decision Engine v2.2 — localization & cause harden tests."""

from __future__ import annotations

import math

import numpy as np

from audio_analyzer.coaching.bottleneck import build_coaching_decision
from audio_analyzer.coaching.bottleneck.hypotheses import rank_hypotheses
from audio_analyzer.coaching.bottleneck.ranker import select_primary
from audio_analyzer.pipeline import _functional_quality_policy
from audio_analyzer.vocal_function.episodes.builder import (
    build_feature_matrix,
    build_generic_episodes_from_segments,
    build_high_note_episodes,
    classify_cause_hint,
    find_best_self_reference,
    select_post_context,
    select_pre_context,
)


def _seg(start, end, **kw):
    obs = {
        "f0_hz": kw.get("f0", 220),
        "rms": kw.get("rms", 0.05),
        "periodicity_primary_db": kw.get("period", 12),
        "raw_h1_h2_proxy_db": kw.get("h1", 3),
        "energy_2_4k": kw.get("e24", 0.15),
        "spectral_centroid_hz": kw.get("cent", 1800),
        "onset_slope_db_per_sec": kw.get("onset", 20),
        "f0_frame_period_perturbation_proxy_percent": kw.get("pert", 1.0),
        "spectral_tilt_db_per_oct": kw.get("tilt", -12),
    }
    src = {
        "valid": True,
        "estimated_naq": kw.get("naq", 0.12),
        "estimated_oq_proxy": kw.get("oq", 0.5),
        "estimated_mfdr_norm_proxy": kw.get("mfdr", 1.0),
    }
    form = {
        "valid": kw.get("form_ok", True),
        "confidence": kw.get("form_conf", 0.7),
        "f1_hz": kw.get("f1", 500),
        "f2_hz": kw.get("f2", 1500),
    }
    return {
        "start_sec": start,
        "end_sec": end,
        "valid": True,
        "observations": obs,
        "level2_proxies": {"glottal_source": src, "formants": form},
        "vocal_evidence": {
            "vocal_specific": kw.get("vocal", True),
            "vocal_confidence": 0.8,
            "accompaniment_match": 0.0,
        },
    }


def test_functional_vocal_only_not_quick_and_not_limited():
    q = _functional_quality_policy(
        analysis_mode="FUNCTIONAL",
        input_mode="VOCAL_ONLY",
        source_mode="raw",
        separation_status="skipped",
        has_no_vocals=False,
        separation_required=False,
    )
    assert q[0] == "FULL_VOCAL_ONLY"


def test_functional_mixed_requires_separation():
    q = _functional_quality_policy(
        analysis_mode="FUNCTIONAL",
        input_mode="MIXED",
        source_mode="raw",
        separation_status="failed",
        has_no_vocals=False,
        separation_required=True,
    )
    assert q[0] == "UNAVAILABLE"
    full = _functional_quality_policy(
        analysis_mode="FUNCTIONAL",
        input_mode="AUTO",
        source_mode="separated",
        separation_status="success",
        has_no_vocals=True,
        separation_required=True,
    )
    assert full[0] == "FULL_MIXED"


def test_pre_context_before_episode_not_first_half():
    segs = [_seg(i, i + 1, f0=200 + i) for i in range(10)]
    # episode 5–7
    pre = select_pre_context(segs, episode_start=5.0, max_sec=4.0, n=3)
    assert pre
    assert all(float(s["end_sec"]) <= 5.0 + 1e-6 for s in pre)
    assert all(float(s["start_sec"]) >= 1.0 for s in pre)  # within max_sec window
    post = select_post_context(segs, episode_end=7.0, max_sec=4.0, n=3)
    assert post
    assert all(float(s["start_sec"]) >= 7.0 - 1e-6 for s in post)


def test_no_post_recovery_unknown():
    members = [_seg(5, 6, rms=0.1), _seg(6, 7, rms=0.12)]
    fm = build_feature_matrix(members, pre_segs=[_seg(3, 4)], post_segs=[], episode_type="HIGH_NOTE")
    assert fm["recovery"]["status"] == "UNKNOWN"
    assert fm["recovery"]["returned_to_baseline"] is None


def test_intensity_delta_not_effort_boolean():
    pre = [_seg(0, 1, rms=0.05)]
    during = [_seg(2, 3, rms=0.1)]  # +6 dB
    fm = build_feature_matrix(during, pre, [], episode_type="HIGH_NOTE")
    d = fm["effort"]["intensity_delta_db"]
    assert d is not None and d > 5.0
    # not a 0/1 effort mean
    assert fm["effort"]["intensity_overshoot"] != fm["effort"]["strain_like"]


def test_same_rms_intensity_delta_near_zero():
    pre = [_seg(0, 1, rms=0.08)]
    during = [_seg(2, 3, rms=0.08)]
    fm = build_feature_matrix(during, pre, [], episode_type="HIGH_NOTE")
    assert fm["effort"]["intensity_delta_db"] is not None
    assert abs(float(fm["effort"]["intensity_delta_db"])) < 0.2


def test_air_leakage_primary_needs_episode():
    profile = {
        "dimensions": {
            "air_leakage_breathiness": {"status": "HIGH"},
            "vocal_effort_strain": {"status": "LOW"},
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
    # no episodes → cannot be primary
    decision = build_coaching_decision(profile=profile, episodes=[], focus={})
    assert decision["primary_bottleneck"] is None
    assert decision["measurement_candidates"] or decision["prefer_additional_measurement"]

    leak_eps = build_generic_episodes_from_segments(
        [
            _seg(1, 2, period=5, h1=10, tilt=-18, oq=0.7),
            _seg(2, 3, period=5, h1=9, tilt=-17, oq=0.65),
        ],
        episode_type="AIR_LEAKAGE",
        predicate=lambda s: True,
    )
    decision2 = build_coaching_decision(profile=profile, episodes=leak_eps, focus={})
    assert decision2["primary_bottleneck"]["id"] == "AIR_LEAKAGE"
    assert decision2["target_episode"] is not None


def test_low_confidence_goal_high_not_primary():
    hyps = [
        {
            "id": "EXCESS_EFFORT_HIGH_NOTE",
            "confidence_label": "low",
            "impact": "HIGH",
            "supporting_evidence": [{"label": "x"}],
            "supporting_episode_ids": ["HIGH_NOTE_1.0_2.0"],
            "support_level": "low",
            "eligibility": "NEEDS_MEASUREMENT",
        }
    ]
    primary, _ = select_primary(hyps, user_goal="HIGH_NOTE")
    assert primary is None


def test_cause_classification_independent_shifts():
    assert classify_cause_hint({"source_shift": 0.8, "effort_shift": 0.1, "resonance_shift": 0.1, "register_shift": 0}) == "SOURCE"
    assert classify_cause_hint({"source_shift": 0.1, "effort_shift": 0.8, "resonance_shift": 0.1, "register_shift": 0}) == "EFFORT"
    assert (
        classify_cause_hint(
            {"source_shift": 0.1, "effort_shift": 0.1, "resonance_shift": 0.8, "register_shift": 0},
            e24_delta=-0.08,
        )
        == "RESONANCE_PRESENCE_LOSS"
    )
    assert (
        classify_cause_hint(
            {"source_shift": 0.1, "effort_shift": 0.1, "resonance_shift": 0.8, "register_shift": 0},
            e24_delta=0.08,
        )
        == "RESONANCE_EXCESS_SHARPNESS"
    )
    assert classify_cause_hint({"source_shift": 0.7, "effort_shift": 0.7, "resonance_shift": 0.1, "register_shift": 0}) == "MIXED"
    assert classify_cause_hint({"source_shift": 0.1, "effort_shift": 0.1, "resonance_shift": 0.1, "register_shift": 0}) == "UNCLEAR"


def test_resonance_increase_not_collapse():
    # 2–4k increase must not be presence-loss / collapse path
    hint = classify_cause_hint(
        {"source_shift": 0, "effort_shift": 0, "resonance_shift": 0.9, "register_shift": 0},
        e24_delta=0.1,
    )
    assert hint != "RESONANCE_PRESENCE_LOSS"
    assert "COLLAPSE" not in hint


def test_register_matrix_fields_filled():
    segs = [
        _seg(0, 1, f0=180, naq=0.05, h1=-1),
        _seg(1, 2, f0=420, naq=0.18, h1=8),
        _seg(2, 3, f0=400, naq=0.16, h1=7),
    ]
    eps = build_high_note_episodes(
        [{"start_sec": 1, "end_sec": 3, "concern": True, "observations": segs[1]["observations"], "level2_proxies": segs[1]["level2_proxies"]}],
        all_segments=segs,
    )
    # force register type finalize via generic
    from audio_analyzer.vocal_function.episodes.builder import build_typed_episodes

    reg = build_typed_episodes(
        [{"start_sec": 1, "end_sec": 2, "observations": segs[1]["observations"], "level2_proxies": segs[1]["level2_proxies"]}],
        episode_type="REGISTER_TRANSITION",
        all_segments=segs,
    )
    fm = reg[0]["feature_matrix"]["register"]
    assert fm.get("transition_strength") is not None or fm.get("f0_delta_cents") is not None
    assert fm.get("f0_continuity") is not None
    assert fm.get("register_shift") is not None


def test_best_self_rejects_negligible_and_far_pitch():
    high = {
        "episode_id": "HIGH_NOTE_10.0_12.0",
        "type": "HIGH_NOTE",
        "concern": True,
        "start_sec": 10,
        "end_sec": 12,
        "members": [{"observations": {"f0_hz": 450}}],
        "feature_matrix": {
            "effort": {"strain_like": 0.9},
            "regularity": {"periodicity": 10, "roughness": False},
            "validity": {"vocal_specific": True},
        },
        "during_context": {"f0_hz": 450},
    }
    mid = {
        "episode_id": "HIGH_NOTE_1.0_3.0",
        "type": "HIGH_NOTE",
        "concern": False,
        "start_sec": 1,
        "end_sec": 3,
        "members": [{"observations": {"f0_hz": 220}}],
        "feature_matrix": {
            "effort": {"strain_like": 0.2},
            "regularity": {"periodicity": 12, "roughness": False},
            "validity": {"vocal_specific": True},
        },
        "during_context": {"f0_hz": 220},
    }
    assert find_best_self_reference([high, mid], target=high) is None

    near = dict(mid)
    near["episode_id"] = "HIGH_NOTE_4.0_6.0"
    near["during_context"] = {"f0_hz": 430}
    near["members"] = [{"observations": {"f0_hz": 430}}]
    near["feature_matrix"] = {
        "effort": {"strain_like": 0.2},
        "regularity": {"periodicity": 12, "roughness": False},
        "validity": {"vocal_specific": True},
    }
    assert find_best_self_reference([high, near], target=high) is not None


def test_pre_during_post_on_merged_episode():
    segs = [_seg(i, i + 1, f0=200, e24=0.2 if i < 4 else 0.05, rms=0.05 if i < 4 else 0.1) for i in range(8)]
    windows = [
        {**segs[4], "start_sec": 4, "end_sec": 5, "concern": True},
        {**segs[5], "start_sec": 5, "end_sec": 6, "concern": True},
    ]
    eps = build_high_note_episodes(windows, all_segments=segs)
    assert eps[0]["context_quality"]["pre_available"] is True
    assert eps[0]["pre_context_segments"]
    assert float(eps[0]["pre_context_segments"][-1]["end_sec"]) <= 4.0 + 1e-6
    if eps[0]["post_context_segments"]:
        assert float(eps[0]["post_context_segments"][0]["start_sec"]) >= 6.0 - 1e-6
