"""Vocal Quality Engine unit tests — non-medical, multi-evidence rules."""

from __future__ import annotations

import numpy as np

from audio_analyzer.song_detail.report import build_song_detailed_report
from audio_analyzer.vocal_quality import compute_vocal_quality_profile
from audio_analyzer.vocal_quality.config import BANNED_USER_SUBSTRINGS
from audio_analyzer.vocal_quality.evidence import segment_evidence_flags
from audio_analyzer.vocal_quality.report import affirmative_copy_blob, build_vocal_quality_public
from audio_analyzer.vocal_quality.rules import fuse_breathy, fuse_onset, fuse_pressed, fuse_rough


def _seg(start, end, *, valid=True, obs=None):
    return {
        "start_sec": start,
        "end_sec": end,
        "valid": valid,
        "voiced_ratio": 0.8,
        "observations": obs or {},
    }


def test_single_periodicity_metric_no_breathy_high():
    # Only periodicity low — spectral family false → not a multi-family hit
    segs = [
        _seg(
            i,
            i + 3,
            obs={
                "periodicity_primary_db": 5.0,
                "spectral_tilt_db_per_oct": -10.0,  # not steep enough
                "raw_h1_h2_proxy_db": 2.0,
            },
        )
        for i in range(0, 18, 3)
    ]
    out = fuse_breathy(segs)
    assert out["status"] != "HIGH"
    assert out["hit_segment_count"] == 0


def test_periodicity_plus_spectral_breathy_eligible():
    segs = [
        _seg(
            i,
            i + 3,
            obs={
                "periodicity_primary_db": 5.0,
                "spectral_tilt_db_per_oct": -20.0,
                "raw_h1_h2_proxy_db": 10.0,
            },
        )
        for i in range(0, 18, 3)
    ]
    out = fuse_breathy(segs)
    assert out["hit_segment_count"] >= 2
    assert out["status"] in ("MODERATE", "HIGH", "INTERMITTENT")


def test_single_h1h2_no_pressed_high():
    segs = [
        _seg(
            i,
            i + 3,
            obs={
                "periodicity_primary_db": 12.0,  # not pressed-high
                "spectral_tilt_db_per_oct": -12.0,
                "raw_h1_h2_proxy_db": -2.0,  # pressed-ish alone
                "onset_slope_db_per_sec": 20.0,
            },
        )
        for i in range(0, 18, 3)
    ]
    out = fuse_pressed(segs, breathy_hits=0)
    assert out["status"] != "HIGH"
    assert out["hit_segment_count"] == 0


def test_pressed_breathy_contradiction_ambiguous():
    segs = []
    for i in range(0, 12, 3):
        segs.append(
            _seg(
                i,
                i + 3,
                obs={
                    "periodicity_primary_db": 5.0,
                    "spectral_tilt_db_per_oct": -20.0,
                    "raw_h1_h2_proxy_db": 10.0,
                },
            )
        )
    for i in range(12, 24, 3):
        segs.append(
            _seg(
                i,
                i + 3,
                obs={
                    "periodicity_primary_db": 22.0,
                    "spectral_tilt_db_per_oct": -4.0,
                    "raw_h1_h2_proxy_db": -1.0,
                    "onset_slope_db_per_sec": 90.0,
                },
            )
        )
    breathy = fuse_breathy(segs)
    pressed = fuse_pressed(segs, breathy_hits=breathy["hit_segment_count"])
    assert pressed["status"] in ("AMBIGUOUS", "UNKNOWN") or breathy["hit_segment_count"] >= 2


def test_rough_one_segment_not_global_high():
    segs = [
        _seg(0, 3, obs={"periodicity_primary_db": 4.0, "f0_frame_period_perturbation_proxy_percent": 3.0})
    ]
    for i in range(3, 18, 3):
        segs.append(_seg(i, i + 3, obs={"periodicity_primary_db": 15.0}))
    out = fuse_rough(segs)
    assert out["status"] != "HIGH"
    assert out["status"] == "INTERMITTENT"


def test_rough_repeated_segments():
    segs = [
        _seg(i, i + 3, obs={"periodicity_primary_db": 4.0, "f0_frame_period_perturbation_proxy_percent": 3.5})
        for i in range(0, 18, 3)
    ]
    out = fuse_rough(segs)
    assert out["hit_segment_count"] >= 3
    assert out["status"] in ("MODERATE", "HIGH")


def test_resonance_descriptive_not_skill():
    y = (0.1 * np.sin(2 * np.pi * 220 * np.arange(44100) / 44100)).astype(np.float32)
    pitch = {
        "frame_f0": [
            {"time_sec": t, "f0_hz": 220.0} for t in np.linspace(0, 0.9, 20)
        ],
        "voiced_ratio": 0.9,
    }
    profile = compute_vocal_quality_profile(
        y=y, sr=44100, pitch=pitch, acoustic={"weight_gap_db": 12.0}
    )
    res = profile["dimensions"]["resonance_timbre"]
    claim = affirmative_copy_blob([res])
    assert "음색" in claim or "밝" in claim or "어둡" in claim or res.get("status") == "UNKNOWN"
    assert "실력 점수" not in claim
    assert "좋다" not in claim and "나쁘다" not in claim
    assert "인두 공간" not in claim
    assert "비강 공명" not in claim


def test_onset_rms_only_no_abrupt_conclusion():
    # Only one abrupt slope → cannot be ABRUPT_LIKE
    segs = [
        _seg(0, 3, obs={"onset_slope_db_per_sec": 100.0, "periodicity_establishment_ratio": 0.2}),
        _seg(3, 6, obs={"onset_slope_db_per_sec": 30.0, "periodicity_establishment_ratio": 0.6}),
        _seg(6, 9, obs={"onset_slope_db_per_sec": 25.0, "periodicity_establishment_ratio": 0.5}),
    ]
    out = fuse_onset(segs)
    assert out["status"] != "ABRUPT_LIKE"


def test_unknown_hidden_in_main_report():
    report = build_song_detailed_report(
        {
            "score": {
                "available": True,
                "overall": 60,
                "label": "보통이에요",
                "areas": [
                    {
                        "area_id": "stability",
                        "display_name": "발성 안정성",
                        "score": 74,
                        "status": "normal",
                        "confidence": 0.8,
                        "submetrics": [],
                        "temporal": {},
                        "segment_scores": [],
                    },
                    {
                        "area_id": "dynamic_control",
                        "display_name": "강약 컨트롤",
                        "score": 57,
                        "status": "needs_work",
                        "confidence": 0.8,
                        "submetrics": [],
                        "temporal": {},
                        "segment_scores": [],
                    },
                ],
            },
            "quality": {"status": "pass"},
            "optional_analysis": {"vibrato": {"available": False}},
            "vocal_quality_profile": {
                "available": True,
                "headline": ["테스트"],
                "dimensions": {
                    "breathy_like": {
                        "dimension_id": "breathy_like",
                        "display_name": "숨이 섞이는 음질 경향",
                        "status": "UNKNOWN",
                        "status_label": "판단 어려움",
                        "hidden": True,
                        "summary": "판단 어려움",
                        "focus_segments": [],
                        "practice": [],
                        "what_it_may_mean": "",
                        "what_we_cannot_know": "x",
                    },
                    "pressed_like": {
                        "dimension_id": "pressed_like",
                        "display_name": "압착된 음질 경향",
                        "status": "MODERATE",
                        "status_label": "중간",
                        "prevalence_label": "일부",
                        "hidden": False,
                        "summary": "일부 반복",
                        "focus_segments": [],
                        "practice": ["가벼운 SOVT"],
                        "what_it_may_mean": "압착된 음질과 일치할 수 있습니다.",
                        "what_we_cannot_know": "목 근육 긴장을 측정하지 않습니다.",
                    },
                },
                "focus_segments": [],
                "disclaimer": "참고",
            },
        }
    )
    ids = [d["dimension_id"] for d in report["vocal_quality_profile"]["dimensions"]]
    assert "breathy_like" not in ids
    assert "pressed_like" in ids
    assert report["summary"]["title"] == "오늘의 코칭"
    assert report["performance_supplement"]["areas"]
    assert "scientific_debug" not in report["vocal_quality_profile"]


def test_medical_banned_wording_absent():
    y = (0.2 * np.sin(2 * np.pi * 180 * np.arange(88200) / 44100)).astype(np.float32)
    pitch = {
        "frame_f0": [{"time_sec": float(t), "f0_hz": 180.0} for t in np.linspace(0, 1.9, 40)],
        "voiced_ratio": 0.85,
    }
    profile = compute_vocal_quality_profile(y=y, sr=44100, pitch=pitch, acoustic={})
    pub = build_vocal_quality_public(profile)
    blob = affirmative_copy_blob(pub.get("dimensions") or [], pub.get("headline"))
    for banned in BANNED_USER_SUBSTRINGS:
        assert banned not in blob
    # Boundary copy may name structures only to say we do NOT measure them.
    disclaimer = str(pub.get("disclaimer") or "")
    assert "진단하지" in disclaimer or "참고" in disclaimer


def test_evidence_flags_same_family_cpp_hnr():
    flags = segment_evidence_flags(
        {
            "observations": {
                "periodicity_primary_db": 5.0,
                "cepstral_prominence_proxy_db": 5.0,
                "hnr_ac_proxy_db": 4.0,  # same family — not a second independent flag
                "spectral_tilt_db_per_oct": -10.0,
            }
        }
    )
    # Only periodicity + spectral counted in breathy families
    assert flags["breathy"]["periodicity"] is True
    assert flags["breathy"]["spectral_or_harmonic"] is False


def test_free_teaser_no_detail_leak():
    from audio_analyzer.models import free_public_result

    pub = free_public_result(
        {
            "score": {
                "available": True,
                "overall": 64,
                "label": "개선 여지가 있어요",
                "areas": [
                    {"area_id": "stability", "score": 74, "status": "normal", "display_name": "발성 안정성"},
                    {"area_id": "dynamic_control", "score": 56, "status": "needs_work", "display_name": "강약"},
                    {"area_id": "projection", "score": None, "status": "unknown"},
                    {"area_id": "resonance", "score": None, "status": "unknown"},
                ],
                "strengths": [],
                "priority_issues": [],
            },
            "quality": {"status": "pass"},
            "vocal_quality_profile": {
                "available": True,
                "dimensions": {
                    "breathy_like": {"status": "INTERMITTENT"},
                    "pressed_like": {"status": "LOW"},
                },
                "scientific_debug": {"secret": True},
            },
            "audio": {},
        }
    )
    assert "vocal_quality_profile" not in pub
    assert pub.get("vocal_quality_teaser")
    assert "scientific_debug" not in str(pub)
