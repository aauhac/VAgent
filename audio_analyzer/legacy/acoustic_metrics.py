"""
acoustic_metrics.py
-------------------
vocal_score 계산에 필요한 음향 지표를 추출한다.
"""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np
import librosa

EPS = 1e-10


def compute_ltas(
    y: np.ndarray,
    sr: int,
    n_fft: int = 4096,
    hop_length: int = 512,
) -> tuple[np.ndarray, np.ndarray]:
    if y is None or len(y) == 0:
        raise ValueError("Empty audio input")

    S = np.abs(librosa.stft(y, n_fft=n_fft, hop_length=hop_length)) + EPS
    power = S ** 2
    mean_power = np.mean(power, axis=1)
    ltas_db = librosa.power_to_db(mean_power, ref=np.max)
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    return freqs, ltas_db


def band_values(freqs: np.ndarray, values_db: np.ndarray, low_hz: float, high_hz: float) -> np.ndarray:
    mask = (freqs >= low_hz) & (freqs <= high_hz)
    return values_db[mask]


def band_mean_db(freqs: np.ndarray, values_db: np.ndarray, low_hz: float, high_hz: float) -> Optional[float]:
    vals = band_values(freqs, values_db, low_hz, high_hz)
    if vals.size == 0:
        return None
    return float(np.mean(vals))


def band_peak_db(freqs: np.ndarray, values_db: np.ndarray, low_hz: float, high_hz: float) -> Optional[float]:
    vals = band_values(freqs, values_db, low_hz, high_hz)
    if vals.size == 0:
        return None
    return float(np.max(vals))


def band_peak_freq(freqs: np.ndarray, values_db: np.ndarray, low_hz: float, high_hz: float) -> Optional[float]:
    mask = (freqs >= low_hz) & (freqs <= high_hz)
    if not np.any(mask):
        return None
    sub_freqs = freqs[mask]
    sub_vals = values_db[mask]
    idx = int(np.argmax(sub_vals))
    return float(sub_freqs[idx])


def compute_spr_db(freqs: np.ndarray, ltas_db: np.ndarray) -> Optional[float]:
    low_peak = band_peak_db(freqs, ltas_db, 0, 2000)
    high_peak = band_peak_db(freqs, ltas_db, 2000, 4000)
    if low_peak is None or high_peak is None:
        return None
    return float(low_peak - high_peak)


def compute_singer_formant_features(freqs: np.ndarray, ltas_db: np.ndarray) -> Dict[str, Optional[float]]:
    center_hz = band_peak_freq(freqs, ltas_db, 2500, 3500)
    peak_db = band_peak_db(freqs, ltas_db, 2500, 3500)
    base_db = band_mean_db(freqs, ltas_db, 1000, 2000)
    prominence_db = None if peak_db is None or base_db is None else float(peak_db - base_db)
    return {
        "singer_formant_center_hz": center_hz,
        "singer_formant_prominence_db": prominence_db,
    }


def compute_spectral_slope_db_per_oct(
    freqs: np.ndarray,
    ltas_db: np.ndarray,
    low_hz: float = 100.0,
    high_hz: float = 8000.0,
) -> Optional[float]:
    mask = (freqs >= low_hz) & (freqs <= high_hz)
    if int(np.sum(mask)) < 10:
        return None
    x = np.log2(freqs[mask] + EPS)
    y = ltas_db[mask]
    slope, _intercept = np.polyfit(x, y, 1)
    return float(slope)


def compute_core_acoustic_metrics(y: np.ndarray, sr: int) -> Dict[str, Optional[float]]:
    freqs, ltas_db = compute_ltas(y, sr)

    rumble = band_mean_db(freqs, ltas_db, 60, 95)
    main_body = band_mean_db(freqs, ltas_db, 95, 4000)

    low_weight = band_mean_db(freqs, ltas_db, 95, 250)
    projection = band_mean_db(freqs, ltas_db, 2000, 4000)

    mouth = band_mean_db(freqs, ltas_db, 500, 800)
    presence = band_mean_db(freqs, ltas_db, 2500, 4000)

    air = band_mean_db(freqs, ltas_db, 6000, 10000)
    mid_ref = band_mean_db(freqs, ltas_db, 1000, 4000)

    spr_db = compute_spr_db(freqs, ltas_db)
    sf = compute_singer_formant_features(freqs, ltas_db)
    slope = compute_spectral_slope_db_per_oct(freqs, ltas_db)

    return {
        "rumble_ratio_db": None if rumble is None or main_body is None else float(rumble - main_body),
        "weight_gap_db": None if low_weight is None or projection is None else float(low_weight - projection),
        "mouth_gap_db": None if mouth is None or presence is None else float(mouth - presence),
        "air_ratio_db": None if air is None or mid_ref is None else float(air - mid_ref),
        "spr_db": spr_db,
        "spectral_slope_db_per_oct": slope,
        **sf,
    }
