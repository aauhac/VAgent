"""Hardening tests: artifacts, completeness, quality codes, vibrato, glissando."""

from __future__ import annotations

import numpy as np
import pytest
import soundfile as sf
from pathlib import Path

from audio_analyzer.features.phonation import (
    analyze_vibrato_on_regions,
    detect_sustained_regions,
    extract_phonation_features,
    phonation_instability_events,
)
from audio_analyzer.features.pitch import extract_pitch_features
from audio_analyzer.pipeline import _artifact_flags, analyze_audio
from audio_analyzer.models import public_result
from audio_analyzer.quality import evaluate_quality
from audio_analyzer.scoring.score_v2 import compute_score_v2


SR = 22050


def _sine(freq: float, duration: float, sr: int = SR, amp: float = 0.3) -> np.ndarray:
    t = np.arange(int(sr * duration)) / sr
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def _vibrato(freq: float, duration: float, rate_hz: float = 5.5, depth_cents: float = 70.0, sr: int = SR):
    t = np.arange(int(sr * duration)) / sr
    depth = depth_cents / 1200.0
    phase = 2 * np.pi * freq * t + (depth * freq / rate_hz) * np.sin(2 * np.pi * rate_hz * t)
    return (0.3 * np.sin(phase)).astype(np.float32)


def test_raw_dark_spectrum_not_demucs_artifact():
    freq = {
        "band_energy_db": {
            "80_250": -10.0,
            "2500_4000": -18.0,
            "6000_10000": -30.0,  # dark / low HF
        }
    }
    flags = _artifact_flags(freq, "raw")
    assert flags["demucs_high_band_loss_likely"] is False
    assert flags["relative_low_mid_inflation_likely"] is False


def test_separated_same_spectrum_is_demucs_artifact():
    freq = {
        "band_energy_db": {
            "80_250": -10.0,
            "2500_4000": -18.0,
            "6000_10000": -30.0,
        }
    }
    flags = _artifact_flags(freq, "separated")
    assert flags["demucs_high_band_loss_likely"] is True


def test_projection_missing_metric_lowers_confidence():
    full = compute_score_v2(
        phonation={"median_residual_std_cents": 12.0, "sustained_count": 3, "median_rms_variation_db": 1.0},
        acoustic={
            "spr_db": 20.0,
            "singer_formant_prominence_db": 6.0,
            "weight_gap_db": 1.0,
            "mouth_gap_db": 3.0,
            "spectral_slope_db_per_oct": -12.0,
        },
        waveform={"dynamic_range_db": 14.0},
        quality={"status": "pass", "codes": []},
        source_mode="raw",
    )
    partial = compute_score_v2(
        phonation={"median_residual_std_cents": 12.0, "sustained_count": 3, "median_rms_variation_db": 1.0},
        acoustic={
            "spr_db": 20.0,
            "singer_formant_prominence_db": None,
            "weight_gap_db": 1.0,
            "mouth_gap_db": 3.0,
            "spectral_slope_db_per_oct": -12.0,
        },
        waveform={"dynamic_range_db": 14.0},
        quality={"status": "pass", "codes": []},
        source_mode="raw",
    )
    full_p = next(a for a in full["areas"] if a["area_id"] == "projection")
    part_p = next(a for a in partial["areas"] if a["area_id"] == "projection")
    assert part_p["score"] is not None
    assert part_p["confidence"] < full_p["confidence"]


def test_resonance_two_metrics_missing_unknown_or_excluded():
    score = compute_score_v2(
        phonation={"median_residual_std_cents": 12.0, "sustained_count": 3, "median_rms_variation_db": 1.0},
        acoustic={
            "spr_db": 20.0,
            "singer_formant_prominence_db": 6.0,
            "weight_gap_db": 1.0,
            "mouth_gap_db": None,
            "spectral_slope_db_per_oct": None,
        },
        waveform={"dynamic_range_db": 14.0},
        quality={"status": "pass", "codes": []},
        source_mode="raw",
    )
    res = next(a for a in score["areas"] if a["area_id"] == "resonance")
    assert res["status"] == "unknown" or res["confidence"] < 0.35


def test_quality_codes_clipping_penalizes_dynamic_more():
    base_q = {"status": "warn", "codes": []}
    clip_q = {"status": "warn", "codes": ["CLIPPING"]}
    kwargs = dict(
        phonation={"median_residual_std_cents": 12.0, "sustained_count": 3, "median_rms_variation_db": 1.0},
        acoustic={
            "spr_db": 20.0,
            "singer_formant_prominence_db": 6.0,
            "weight_gap_db": 1.0,
            "mouth_gap_db": 3.0,
            "spectral_slope_db_per_oct": -12.0,
        },
        waveform={"dynamic_range_db": 14.0},
        source_mode="raw",
    )
    a = compute_score_v2(quality=base_q, **kwargs)
    b = compute_score_v2(quality=clip_q, **kwargs)
    dyn_a = next(x for x in a["areas"] if x["area_id"] == "dynamic_control")
    dyn_b = next(x for x in b["areas"] if x["area_id"] == "dynamic_control")
    assert dyn_b["confidence"] < dyn_a["confidence"]


def test_quality_gate_emits_codes():
    y = np.zeros(int(SR * 4), dtype=np.float32)
    q = evaluate_quality(y, SR, voiced_ratio=0.01, voiced_duration_sec=0.1)
    assert q["status"] == "fail"
    assert "codes" in q
    assert len(q["codes"]) >= 1


def test_public_result_has_no_filesystem_paths():
    fake = {
        "analysis_version": "2.0",
        "recording_id": "abc",
        "analysis_status": "completed",
        "feedback_status": "skipped",
        "audio": {
            "duration_sec": 3.0,
            "sample_rate": 44100,
            "source_mode": "raw",
            "original_path": r"C:\\VocalAgent\\foo.m4a",
            "analysis_wav_path": r"C:\\VocalAgent\\runtime\\x\\analysis.wav",
            "preview_path": "/runtime/x/preview.wav",
            "separation": {"used": False, "vocals_path": "/runtime/x/demucs/vocals.wav"},
        },
        "quality": {"status": "pass", "confidence": 0.9, "reasons": [], "codes": [], "metrics": {}},
        "score": {"available": True, "areas": [], "overall": 80},
        "optional_analysis": {},
        "issues": [],
        "timeline": [],
        "strengths": [],
        "analysis_notes": [],
        "preview_path": r"C:\\runtime\\x\\preview.wav",
    }
    pub = public_result(fake)
    blob = str(pub)
    assert "C:\\" not in blob
    assert "/runtime/" not in blob
    assert "analysis.wav" not in blob
    assert "preview.wav" not in blob
    assert pub["audio"]["duration_sec"] == 3.0
    assert set(pub["audio"].keys()) <= {"duration_sec", "sample_rate", "source_mode", "separation"}


def test_vibrato_available_mandatory(tmp_path: Path):
    y = _vibrato(220.0, 2.5, rate_hz=5.5, depth_cents=80.0)
    wav = tmp_path / "vib.wav"
    sf.write(str(wav), y, SR)
    result = analyze_audio(
        str(wav),
        output_dir=str(tmp_path / "rt"),
        recording_id="vib",
        sample_rate=SR,
        build_preview=False,
    )
    vib = result["optional_analysis"]["vibrato"]
    assert vib["available"] is True
    assert 4.0 <= float(vib["rate_hz"]) <= 7.0


def test_straight_tone_no_vibrato(tmp_path: Path):
    y = _sine(220.0, 2.5)
    wav = tmp_path / "straight.wav"
    sf.write(str(wav), y, SR)
    result = analyze_audio(
        str(wav),
        output_dir=str(tmp_path / "rt"),
        recording_id="straight",
        sample_rate=SR,
        build_preview=False,
    )
    vib = result["optional_analysis"]["vibrato"]
    assert vib.get("available") is False or float(vib.get("regularity") or 0) < 0.35


def test_glissando_not_phonation_instability():
    # continuous glide C4→G4 over 2s
    sr = SR
    t = np.arange(int(sr * 2.2)) / sr
    f0_start, f0_end = 261.63, 392.0
    freq = f0_start * (f0_end / f0_start) ** (t / t[-1])
    phase = 2 * np.pi * np.cumsum(freq) / sr
    y = (0.25 * np.sin(phase)).astype(np.float32)
    pitch = extract_pitch_features(y, sr)
    phon = extract_phonation_features(y, sr, pitch)
    events = phon.get("instability_events") or []
    assert events == []


def test_fast_melisma_not_instability():
    notes = [261.63, 293.66, 329.63, 349.23, 392.0, 440.0]
    parts = [_sine(f, 0.28) for f in notes]
    y = np.concatenate(parts)
    pitch = extract_pitch_features(y, sr=SR)
    phon = extract_phonation_features(y, SR, pitch)
    assert (phon.get("instability_events") or []) == []


def test_deep_vibrato_not_over_segmented():
    y = _vibrato(220.0, 2.0, rate_hz=5.5, depth_cents=120.0)
    pitch = extract_pitch_features(y, SR)
    phon = extract_phonation_features(y, SR, pitch)
    # Should form at least one reasonably long sustained region
    regions = phon.get("sustained_regions") or []
    assert any(r["duration_sec"] >= 0.8 for r in regions) or phon.get("vibrato", {}).get("available")


def test_slow_portamento_no_false_instability():
    sr = SR
    t = np.arange(int(sr * 1.8)) / sr
    freq = 220.0 + 30.0 * (t / t[-1])  # slow gentle drift
    phase = 2 * np.pi * np.cumsum(freq) / sr
    y = (0.25 * np.sin(phase)).astype(np.float32)
    pitch = extract_pitch_features(y, sr)
    phon = extract_phonation_features(y, sr, pitch)
    assert (phon.get("instability_events") or []) == []
