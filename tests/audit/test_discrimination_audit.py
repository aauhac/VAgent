"""Discrimination / fingerprint / UX policy tests."""

from __future__ import annotations

import numpy as np
import soundfile as sf

from audio_analyzer.audit.fingerprints import (
    cached_artifact_matches_source,
    file_fingerprint,
    sha256_file,
    write_source_sidecar,
)
from audio_analyzer.scoring.duration_policy_v3 import select_score_clip
from audio_analyzer.scoring.segments_v3 import compute_spectral_segments
from audio_analyzer.song_detail.explain_v3 import (
    build_overall_assessment,
    collect_detail_strengths,
)
from audio_analyzer.song_detail.report import build_song_detailed_report


def test_two_different_audio_different_fingerprint(tmp_path):
    a = tmp_path / "a.wav"
    b = tmp_path / "b.wav"
    sr = 16000
    t = np.linspace(0, 1, sr, endpoint=False)
    sf.write(a, (0.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32), sr)
    sf.write(b, (0.2 * np.sin(2 * np.pi * 440 * t)).astype(np.float32), sr)
    fa, fb = file_fingerprint(a), file_fingerprint(b)
    assert fa["sha256"] != fb["sha256"]
    assert fa["size_bytes"] == fb["size_bytes"]  # same length, different content


def test_cache_sidecar_rejects_wrong_source(tmp_path):
    src1 = tmp_path / "src1.bin"
    src2 = tmp_path / "src2.bin"
    src1.write_bytes(b"aaa")
    src2.write_bytes(b"bbb")
    art = tmp_path / "input_converted.wav"
    art.write_bytes(b"cached")
    write_source_sidecar(art, sha256_file(src1))
    assert cached_artifact_matches_source(art, sha256_file(src1))
    assert not cached_artifact_matches_source(art, sha256_file(src2))


def test_unknown_axis_cannot_create_strength():
    areas = [
        {
            "area_id": "projection",
            "display_name": "목소리 전달력",
            "status": "unknown",
            "score": None,
            "submetrics": [
                {
                    "submetric_id": "spectral_projection",
                    "display_name": "스펙트럼 전달",
                    "score": 100,
                    "confidence": 0.8,
                }
            ],
        }
    ]
    assert collect_detail_strengths(areas) == []


def test_unknown_axis_hidden_from_song_detail_main():
    report = build_song_detailed_report(
        {
            "score": {
                "available": True,
                "overall": 64.6,
                "label": "개선 여지가 있어요",
                "overall_coverage": 0.5,
                "areas": [
                    {
                        "area_id": "stability",
                        "display_name": "발성 안정성",
                        "score": 74,
                        "status": "normal",
                        "confidence": 0.8,
                        "coverage": 0.9,
                        "submetrics": [
                            {
                                "submetric_id": "sustain_pitch_stability",
                                "display_name": "지속음 안정성",
                                "score": 96,
                                "confidence": 0.85,
                            }
                        ],
                        "temporal": {},
                        "segment_scores": [],
                    },
                    {
                        "area_id": "projection",
                        "display_name": "목소리 전달력",
                        "score": None,
                        "status": "unknown",
                        "confidence": 0.2,
                        "coverage": 0.9,
                        "ceiling_reasons": ["confidence_below_unknown"],
                        "submetrics": [
                            {
                                "submetric_id": "spectral_projection",
                                "display_name": "스펙트럼 전달",
                                "score": 100,
                                "confidence": 0.15,
                            }
                        ],
                        "temporal": {},
                        "segment_scores": [],
                    },
                    {
                        "area_id": "resonance",
                        "display_name": "공명 균형",
                        "score": None,
                        "status": "unknown",
                        "confidence": 0.2,
                        "submetrics": [],
                        "temporal": {},
                        "segment_scores": [],
                    },
                    {
                        "area_id": "dynamic_control",
                        "display_name": "강약 컨트롤",
                        "score": 56,
                        "status": "needs_work",
                        "confidence": 0.8,
                        "submetrics": [],
                        "temporal": {"worst": 40},
                        "segment_scores": [
                            {"start_sec": 1, "end_sec": 3, "score": 40, "confidence": 0.8}
                        ],
                    },
                ],
            },
            "quality": {"status": "pass"},
            "optional_analysis": {"vibrato": {"available": False}},
        }
    )
    ids = [a["area_id"] for a in report["areas"]]
    assert "projection" not in ids
    assert "resonance" not in ids
    assert "stability" in ids
    assert report["excluded_unknown_areas"]
    assert all(s.get("area_id") != "projection" for s in report["strengths"])


def test_two_reliable_axes_hide_public_overall():
    score = {
        "available": True,
        "overall": 64.6,
        "label": "개선 여지가 있어요",
        "overall_coverage": 0.55,
        "areas": [
            {"area_id": "stability", "score": 74, "status": "normal"},
            {"area_id": "dynamic_control", "score": 56, "status": "needs_work"},
            {"area_id": "projection", "score": None, "status": "unknown"},
            {"area_id": "resonance", "score": None, "status": "unknown"},
        ],
    }
    oa = build_overall_assessment(score)
    assert oa["overall_display_state"] == "PARTIAL"
    assert oa["display_overall"] is None
    assert oa["internal_overall"] == 64.6


def test_three_reliable_axes_allow_overall():
    score = {
        "available": True,
        "overall": 70.0,
        "label": "좋은 편",
        "overall_coverage": 0.8,
        "areas": [
            {"area_id": "stability", "score": 72, "status": "good"},
            {"area_id": "dynamic_control", "score": 68, "status": "normal"},
            {"area_id": "projection", "score": 66, "status": "normal"},
            {"area_id": "resonance", "score": None, "status": "unknown"},
        ],
    }
    oa = build_overall_assessment(score)
    assert oa["overall_display_state"] == "FULL"
    assert oa["display_overall"] == 70.0


def test_duration_policy_truncates_long_song():
    # Fake pitch frames: voiced only in middle
    frames = []
    for t in np.linspace(0, 120, 240):
        frames.append({"time_sec": float(t), "f0_hz": 220.0 if 40 <= t <= 80 else None})
    policy = select_score_clip(120.0, {"frame_f0": frames}, clip_sec=45.0, max_full_sec=60.0)
    assert policy["truncated"] is True
    assert 35 <= policy["start_sec"] <= 45
    assert policy["clip_sec"] <= 45.1


def test_voiced_mask_excludes_silent_proxy_windows():
    sr = 8000
    y = np.zeros(sr * 6, dtype=np.float32)
    # energy in first 3s but unvoiced; voiced frames only marked later with no energy
    y[: sr * 3] = 0.2 * np.sin(2 * np.pi * 100 * np.arange(sr * 3) / sr).astype(np.float32)
    pitch = {
        "frame_f0": [
            {"time_sec": t, "f0_hz": None if t < 3 else 200.0}
            for t in np.linspace(0, 5.9, 60)
        ]
    }
    # Without voiced frames in energetic region, segments should be empty or few
    segs = compute_spectral_segments(y, sr, pitch=pitch)
    for s in segs:
        assert (s.get("voiced_ratio") or 0) >= 0.25 or s.get("vocal_present")


def test_collision_classifier_raw_vs_mapping():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "scripts" / "discrimination_audit.py"
    spec = importlib.util.spec_from_file_location("discrimination_audit", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    assert mod._classify(10.0, 10.01, 96.0, 96.0, "normal", "normal") == "RAW_COLLISION"
    assert mod._classify(10.0, 20.0, 100.0, 100.0, "normal", "normal") == "MAPPING_COLLISION"
