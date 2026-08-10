"""Resonance / timbre descriptive profile (not skill score)."""

from __future__ import annotations

from typing import Any, Optional

import numpy as np


def spectral_bands(y: np.ndarray, sr: int) -> dict[str, float]:
    spec = np.abs(np.fft.rfft(y * np.hanning(len(y)))) ** 2
    freqs = np.fft.rfftfreq(len(y), 1.0 / sr)
    total = float(np.sum(spec)) + 1e-12

    def band(lo: float, hi: float) -> float:
        m = (freqs >= lo) & (freqs < hi)
        return float(np.sum(spec[m]) / total)

    return {
        "energy_1_2k": band(1000, 2000),
        "energy_2_4k": band(2000, 4000),
        "energy_4_8k": band(4000, 8000),
        "alpha_ratio_db": float(
            10
            * np.log10(
                (band(1000, 5000) + 1e-12) / (band(50, 1000) + 1e-12)
            )
        ),
        "spectral_centroid_hz": float(np.sum(freqs * spec) / total),
    }


def build_timbre_profile(
    bands: dict[str, float],
    formant_conf: Optional[float] = None,
) -> dict[str, Any]:
    c = bands.get("spectral_centroid_hz") or 1500.0
    mid = bands.get("energy_1_2k") or 0.0
    upper = bands.get("energy_2_4k") or 0.0
    if c < 1400:
        brightness = "어두운 편"
    elif c > 2200:
        brightness = "밝은 편"
    else:
        brightness = "중간"
    mid_lab = "낮은 편" if mid < 0.12 else ("높은 편" if mid > 0.25 else "보통")
    up_lab = "낮은 편" if upper < 0.08 else ("높은 편" if upper > 0.2 else "보통")
    restricted = formant_conf is not None and formant_conf < 0.28
    return {
        "brightness": brightness,
        "weight_or_warmth": "무게감 있는 편" if c < 1600 else "가벼운 편",
        "mid_presence": mid_lab,
        "upper_harmonic_presence": up_lab,
        "resonance_focus": "보통",
        "flexibility": "UNKNOWN",
        "descriptive_only": True,
        "restricted": restricted,
        "what_it_is_not": "음색 좋고 나쁨 / 실력 점수가 아닙니다.",
    }
