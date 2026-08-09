"""Quality gate unit tests."""

import numpy as np

from audio_analyzer.quality.gate import evaluate_quality


def test_pass_on_reasonable_tone():
    sr = 22050
    t = np.arange(int(sr * 4)) / sr
    y = (0.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    q = evaluate_quality(y, sr, voiced_ratio=0.7, voiced_duration_sec=2.8)
    assert q["status"] in ("pass", "warn")
    assert "metrics" in q


def test_fail_short_audio():
    sr = 22050
    y = (0.2 * np.sin(2 * np.pi * 220 * np.arange(sr) / sr)).astype(np.float32)
    q = evaluate_quality(y, sr, voiced_ratio=0.8, voiced_duration_sec=0.8)
    assert q["status"] == "fail"
