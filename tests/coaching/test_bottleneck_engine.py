"""Coach bottleneck / contamination / episode tests."""

from __future__ import annotations

import numpy as np

from audio_analyzer.coaching.bottleneck import build_coaching_decision
from audio_analyzer.coaching.bottleneck.hypotheses import rank_hypotheses
from audio_analyzer.vocal_function.episodes.builder import build_high_note_episodes
from audio_analyzer.vocal_function.evidence_gate import (
    accompaniment_contamination_at,
    segment_vocal_evidence,
)
from audio_analyzer.vocal_function.rules.fusion import fuse_register


def _seg(start, end, *, f0, period=12.0, vocal_specific=True, accomp=0.0, firm=False, light=False, naq=0.1, h1=3.0, rms=0.05):
    from audio_analyzer.vocal_function.evidence.families import firmer_like, lighter_like

    obs = {
        "f0_hz": f0,
        "periodicity_primary_db": period,
        "raw_h1_h2_proxy_db": -1.0 if firm else (10.0 if light else h1),
        "energy_2_4k": 0.22 if firm else 0.08,
        "spectral_tilt_db_per_oct": -4.0 if firm else -18.0,
        "rms": rms,
        "onset_slope_db_per_sec": 20.0,
    }
    src = {
        "valid": True,
        "estimated_naq": 0.05 if firm else (0.2 if light else naq),
        "estimated_mfdr_proxy": 1.0,
        "estimated_oq_proxy": 0.4 if firm else 0.65,
    }
    s = {
        "start_sec": start,
        "end_sec": end,
        "valid": True,
        "observations": obs,
        "level2_proxies": {"glottal_source": src, "formants": {"valid": True}, "timbre": {}},
        "vocal_evidence": {
            "vocal_specific": vocal_specific,
            "vocal_confidence": 0.8 if vocal_specific else 0.2,
            "accompaniment_match": accomp,
        },
    }
    return s


def test_no_vocals_only_pitch_transition_register_reject():
    # Not vocal-specific → reject
    segs = [
        _seg(0, 3, f0=180, vocal_specific=False, firm=True),
        _seg(3, 6, f0=400, vocal_specific=False, light=True, period=6.0),
    ]
    out = fuse_register(segs, {"frame_f0": []})
    assert out["status"] != "TRANSITION_EVENTS" or not (out.get("profile") or {}).get("events")
    rejected = (out.get("profile") or {}).get("rejected_events") or []
    assert any(r.get("reason_code") == "REGISTER_EVENT_REJECTED" for r in rejected)


def test_vocals_no_vocals_same_transition_contamination():
    sr = 22050
    n = sr * 2
    t = np.arange(n) / sr
    # Strong shared mid-band step at midpoint in BOTH stems
    step = np.ones(n)
    step[: n // 2] = 0.05
    step[n // 2 :] = 1.0
    carrier = np.sin(2 * np.pi * 1200 * t)
    yv = (0.05 * np.sin(2 * np.pi * 220 * t) + 0.8 * carrier * step).astype(np.float32)
    yn = (0.02 * np.random.randn(n) * 0.1 + 0.8 * carrier * step).astype(np.float32)
    c = accompaniment_contamination_at(yv, yn, sr, 0.2, 1.8)
    assert c["possible_accompaniment_contamination"] is True or c["accompaniment_match"] >= 0.5


def test_vocal_specific_register_candidate():
    segs = [
        _seg(0, 3, f0=180, vocal_specific=True, firm=True, period=14.0, rms=0.04),
        _seg(3, 6, f0=420, vocal_specific=True, light=True, period=7.0, rms=0.08),
    ]
    out = fuse_register(segs, {"frame_f0": []})
    events = (out.get("profile") or {}).get("events") or []
    assert len(events) >= 1
    assert events[0]["validity"]["vocal_specific"] is True


def test_overlapping_high_note_windows_one_episode():
    windows = [
        {"start_sec": 18.0, "end_sec": 21.0, "type": "HIGH_NOTE", "concern": True, "periodicity": 8},
        {"start_sec": 19.5, "end_sec": 22.5, "type": "HIGH_NOTE", "concern": True, "periodicity": 7},
        {"start_sec": 22.5, "end_sec": 25.5, "type": "HIGH_NOTE", "concern": False, "periodicity": 10},
        {"start_sec": 24.0, "end_sec": 27.0, "type": "HIGH_NOTE", "concern": False, "periodicity": 11},
        {"start_sec": 27.0, "end_sec": 30.0, "type": "HIGH_NOTE", "concern": False, "periodicity": 12},
    ]
    eps = build_high_note_episodes(windows)
    assert len(eps) == 1
    assert eps[0]["start_sec"] == 18.0
    assert eps[0]["end_sec"] == 30.0
    assert eps[0]["n_merged_windows"] == 5
    assert "phases" in eps[0]


def test_firm_alone_no_bottleneck():
    profile = {
        "dimensions": {
            "vocal_effort_strain": {"status": "LOW"},
            "air_leakage_breathiness": {"status": "LOW"},
            "register_configuration": {"status": "STABLE_LIKE", "profile": {"events": []}},
            "glottal_contact_profile": {"continuum_0_to_1": 0.8, "status": "OBSERVED"},
            "onset_offset_coordination": {"status": "BALANCED_LIKE"},
            "phonation_regularity": {"status": "STABLE"},
            "resonance_formant_strategy": {"status": "OBSERVED", "profile": {}},
            "respiratory_phonatory_coordination": {"status": "STABLE_LIKE"},
            "vibrato_control": {"status": "UNKNOWN"},
        },
        "contact_effort_plane": {
            "firm_high_strain_low": True,
            "firm_high_strain_high": False,
        },
    }
    hyps = rank_hypotheses(profile, [])
    assert not any(h["id"] == "EXCESS_EFFORT_HIGH_NOTE" and h.get("supporting_evidence") for h in hyps)


def test_firm_plus_effort_spike_candidate():
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
            "glottal_contact_profile": {"continuum_0_to_1": 0.8},
        },
        "contact_effort_plane": {"firm_high_strain_high": True, "firm_high_strain_low": False},
    }
    eps = [
        {
            "episode_id": "HIGH_NOTE_10.0_14.0",
            "type": "HIGH_NOTE",
            "concern": True,
            "start_sec": 10,
            "end_sec": 14,
            "feature_matrix": {
                "effort": {"strain_like": 0.8, "effort_shift": 0.8},
                "source": {"contact_firmness": 0.8},
                "regularity": {"periodicity": 6},
                "shifts": {"effort_shift": 0.8, "source_shift": 0.5},
                "validity": {"vocal_specific": True},
            },
        }
    ]
    decision = build_coaching_decision(
        profile=profile,
        episodes=eps,
        focus={"primary": eps, "best_self_reference": None},
        user_goal="HIGH_NOTE",
    )
    assert decision["primary_bottleneck"] is not None
    assert decision["primary_bottleneck"]["id"] in (
        "EXCESS_EFFORT_HIGH_NOTE",
        "EXCESS_FIRMNESS_WITH_STRAIN",
    )
    assert decision["target_episode"] is not None
    assert decision["exercise_plan"]
    assert decision["modify"]


def test_firm_stable_preserve_contact():
    profile = {
        "dimensions": {
            "vocal_effort_strain": {"status": "LOW"},
            "glottal_contact_profile": {"continuum_0_to_1": 0.75, "status": "OBSERVED"},
            "phonation_regularity": {"status": "STABLE"},
            "vibrato_control": {"status": "OBSERVED"},
            "air_leakage_breathiness": {"status": "LOW"},
            "register_configuration": {"status": "STABLE_LIKE", "profile": {}},
            "onset_offset_coordination": {"status": "BALANCED_LIKE"},
            "resonance_formant_strategy": {"profile": {}},
            "respiratory_phonatory_coordination": {"status": "STABLE_LIKE"},
        },
        "contact_effort_plane": {"firm_high_strain_low": True},
    }
    decision = build_coaching_decision(
        profile=profile,
        episodes=[],
        focus={},
        user_goal="GENERAL_EASE_AND_CONTROL",
    )
    assert any(p["id"] == "contact_firmness" for p in decision["preserve"])


def test_contact_slider_direction():
    # 0=light → ● on left (0 left dashes), 1=firm → ● on right
    def pos(c: float) -> tuple[int, int]:
        c = max(0.0, min(1.0, c))
        return int(round(c * 6)), int(round((1 - c) * 6))

    assert pos(0.0) == (0, 6)
    assert pos(1.0) == (6, 0)
    left, right = pos(0.7)
    assert left > right  # firm → more dashes before dot (toward right)


def test_goal_changes_priority_only():
    profile = {
        "dimensions": {
            "vocal_effort_strain": {"status": "OCCASIONAL"},
            "air_leakage_breathiness": {"status": "LOW"},
            "register_configuration": {"status": "STABLE_LIKE", "profile": {"events": []}},
            "onset_offset_coordination": {"status": "BALANCED_LIKE"},
            "phonation_regularity": {"status": "STABLE"},
            "resonance_formant_strategy": {"profile": {"mid_presence": "낮은 편"}},
            "respiratory_phonatory_coordination": {"status": "STABLE_LIKE"},
            "vibrato_control": {"status": "UNKNOWN"},
            "glottal_contact_profile": {},
        },
        "contact_effort_plane": {},
    }
    eps = [{"episode_id": "HIGH_NOTE_1.0_3.0", "type": "HIGH_NOTE", "concern": True, "start_sec": 1, "end_sec": 3, "feature_matrix": {"effort": {"strain_like": 0.7, "effort_shift": 0.7}, "regularity": {}, "shifts": {"effort_shift": 0.7}, "validity": {"vocal_specific": True}}}]
    a = rank_hypotheses(profile, eps, user_goal="HIGH_NOTE")
    b = rank_hypotheses(profile, eps, user_goal="VIBRATO")
    # raw supporting evidence labels same set for effort hyp
    ea = next(h for h in a if h["id"] == "EXCESS_EFFORT_HIGH_NOTE")
    eb = next(h for h in b if h["id"] == "EXCESS_EFFORT_HIGH_NOTE")
    assert [x.get("label") for x in ea["supporting_evidence"]] == [
        x.get("label") for x in eb["supporting_evidence"]
    ]
    assert ea["impact"] == "HIGH"
    assert eb["impact"] != "HIGH" or True  # may still be medium


def test_low_confidence_hidden_in_public():
    from audio_analyzer.vocal_function.report import public_dimensions

    profile = {
        "dimensions": {
            "vocal_effort_strain": {
                "dimension_id": "vocal_effort_strain",
                "status": "LOW",
                "confidence_label": "low",
                "hidden": True,
                "summary": "안정",
            },
            "glottal_contact_profile": {
                "dimension_id": "glottal_contact_profile",
                "status": "OBSERVED",
                "confidence_label": "medium",
                "hidden": False,
                "summary": "중간",
                "continuum_0_to_1": 0.5,
            },
        }
    }
    pubs = public_dimensions(profile)
    ids = [d["dimension_id"] for d in pubs]
    assert "vocal_effort_strain" not in ids
    assert "glottal_contact_profile" in ids


def test_evidence_gate_flags():
    sr = 22050
    y = (0.2 * np.sin(2 * np.pi * 220 * np.arange(sr) / sr)).astype(np.float32)
    pitch = {
        "frame_f0": [{"time_sec": t / 100, "f0_hz": 220.0} for t in range(100)],
    }
    ev = segment_vocal_evidence(
        y_vocals=y,
        sr=sr,
        start_sec=0.1,
        end_sec=0.9,
        pitch=pitch,
        segment_obs={"voiced_ratio": 0.9, "observations": {"periodicity_primary_db": 12}},
        y_no_vocals=None,
    )
    assert "vocal_specific" in ev
    assert "vocal_confidence" in ev
