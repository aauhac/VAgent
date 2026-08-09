"""
Synthetic audio unit tests for VAgent v2.

CASE 1: sustained 220Hz sine → high local stability
CASE 2: C4→E4→G4 stable notes → no phonation_instability from melody
CASE 3: vibrato ~5.5Hz
CASE 4: silence → quality fail, score unavailable
CASE 5: clipped → warn/fail
CASE 6: low level → warn/fail
CASE 7: unknown status never becomes strength
CASE 8: no LLM → deterministic analysis still works
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from audio_analyzer.features.phonation import (
    analyze_vibrato_on_regions,
    detect_sustained_regions,
    extract_phonation_features,
    phonation_instability_events,
)
from audio_analyzer.features.pitch import extract_pitch_features
from audio_analyzer.pipeline import analyze_audio
from audio_analyzer.quality import evaluate_quality
from audio_analyzer.scoring.score_v2 import compute_score_v2, status_from_score


SR = 22050


def _write_wav(path: Path, y: np.ndarray, sr: int = SR) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), y.astype(np.float32), sr)
    return path


def _sine(freq: float, duration: float, sr: int = SR, amp: float = 0.3) -> np.ndarray:
    t = np.arange(int(sr * duration)) / sr
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def _note_hz(name: str) -> float:
    # approximate equal temperament from A4=440
    semis = {
        "C4": -9,
        "E4": -5,
        "G4": -2,
        "C5": 3,
    }[name]
    return 440.0 * (2.0 ** (semis / 12.0))


@pytest.fixture()
def tmp_runtime(tmp_path: Path) -> Path:
    return tmp_path / "runtime"


def test_case1_sustained_tone_high_stability(tmp_runtime: Path):
    y = _sine(220.0, 3.5)
    wav = _write_wav(tmp_runtime / "sine220.wav", y)
    result = analyze_audio(
        str(wav),
        output_dir=str(tmp_runtime),
        recording_id="case1",
        sample_rate=SR,
        build_preview=False,
        include_feedback=False,
    )
    phon = result["features"]["phonation"]
    assert phon["sustained_count"] >= 1
    assert phon["median_residual_std_cents"] is not None
    assert phon["median_residual_std_cents"] < 25.0
    assert result["score"]["available"] is True
    stab = next(a for a in result["score"]["areas"] if a["area_id"] == "stability")
    assert stab["score"] is not None
    assert stab["score"] >= 70.0


def test_case2_melody_movement_not_instability(tmp_runtime: Path):
    parts = [
        _sine(_note_hz("C4"), 0.9),
        _sine(_note_hz("E4"), 0.9),
        _sine(_note_hz("G4"), 0.9),
    ]
    y = np.concatenate(parts)
    wav = _write_wav(tmp_runtime / "melody.wav", y)
    result = analyze_audio(
        str(wav),
        output_dir=str(tmp_runtime),
        recording_id="case2",
        sample_rate=SR,
        build_preview=False,
    )
    # Melody moves globally, but must NOT create pitch-accuracy-style events
    timeline = result.get("timeline") or []
    assert all(e.get("type") != "unstable_pitch" for e in timeline)
    assert all(e.get("type") != "pitch_unstable" for e in timeline)
    # Local residual instability should not fire on clean stepped tones
    assert not any(e.get("type") == "phonation_instability" for e in timeline)


def test_case3_vibrato_rate(tmp_runtime: Path):
    sr = SR
    duration = 2.5
    t = np.arange(int(sr * duration)) / sr
    # 220Hz carrier with 5.5Hz vibrato, ~80 cent depth
    depth = 80.0 / 1200.0
    phase = 2 * np.pi * 220 * t + (depth * 220 / 5.5) * np.sin(2 * np.pi * 5.5 * t)
    y = (0.3 * np.sin(phase)).astype(np.float32)
    wav = _write_wav(tmp_runtime / "vibrato.wav", y)
    result = analyze_audio(
        str(wav),
        output_dir=str(tmp_runtime),
        recording_id="case3",
        sample_rate=sr,
        build_preview=False,
    )
    vib = result["optional_analysis"]["vibrato"]
    assert vib.get("available") is True
    assert 4.0 <= float(vib["rate_hz"]) <= 7.0
    # Vibrato must not be an overall score area
    area_ids = [a["area_id"] for a in result["score"]["areas"]]
    assert "vibrato" not in area_ids


def test_case4_silence_quality_fail(tmp_runtime: Path):
    y = np.zeros(int(SR * 4.0), dtype=np.float32)
    wav = _write_wav(tmp_runtime / "silence.wav", y)
    result = analyze_audio(
        str(wav),
        output_dir=str(tmp_runtime),
        recording_id="case4",
        sample_rate=SR,
        build_preview=False,
    )
    assert result["quality"]["status"] == "fail"
    assert result["score"]["available"] is False
    assert result["score"].get("overall") is None


def test_case5_clipped_audio(tmp_runtime: Path):
    y = _sine(220.0, 3.0, amp=1.2)
    y = np.clip(y, -1.0, 1.0)
    wav = _write_wav(tmp_runtime / "clipped.wav", y)
    q = evaluate_quality(y, SR, voiced_ratio=0.8, voiced_duration_sec=2.5)
    assert q["status"] in ("warn", "fail")
    assert q["metrics"]["clipping_ratio"] > 0


def test_case6_low_level(tmp_runtime: Path):
    y = _sine(220.0, 3.0, amp=0.0005)
    q = evaluate_quality(y, SR, voiced_ratio=0.5, voiced_duration_sec=1.5)
    assert q["status"] in ("warn", "fail")
    assert q["metrics"]["rms_dbfs"] < -30


def test_case7_unknown_not_strength():
    score = compute_score_v2(
        phonation={
            "median_residual_std_cents": 10.0,
            "sustained_count": 3,
            "median_rms_variation_db": 1.0,
        },
        acoustic={
            "spr_db": 20.0,
            "singer_formant_prominence_db": 5.0,
            "weight_gap_db": 0.0,
            "mouth_gap_db": 4.0,
            "spectral_slope_db_per_oct": -12.0,
        },
        waveform={"dynamic_range_db": 15.0},
        quality={"status": "pass"},
        source_mode="separated",
        artifact_flags={"high_band_loss_likely": True, "relative_low_mid_inflation_likely": True},
    )
    for a in score["areas"]:
        if a["status"] == "unknown":
            assert a["area_id"] not in [s["area_id"] for s in score.get("strengths") or []]
    # Direct status helper
    assert status_from_score(90.0, 0.2) == "unknown"


def test_case8_no_llm_still_returns_score(tmp_runtime: Path):
    y = _sine(220.0, 3.5, amp=0.25)
    wav = _write_wav(tmp_runtime / "nollm.wav", y)
    result = analyze_audio(
        str(wav),
        output_dir=str(tmp_runtime),
        recording_id="case8",
        sample_rate=SR,
        build_preview=False,
        include_feedback=True,
        feedback_kwargs={"use_llm": False, "api_key": None},
    )
    assert result["analysis_status"] == "completed"
    assert result["score"]["available"] is True
    assert result["feedback_status"] in ("completed", "failed")
    assert result.get("feedback") is not None


def test_sustained_region_detection_unit():
    hop = 0.01
    times = np.arange(0, 2.0, hop)
    # 1s at 220, then jump to 330 for 1s
    f0 = np.where(times < 1.0, 220.0, 330.0)
    voiced = np.ones_like(f0, dtype=bool)
    regions = detect_sustained_regions(times, f0, voiced, hop_sec=hop)
    assert len(regions) >= 2
    events = phonation_instability_events(regions)
    assert events == []
