"""
vocal_quality/metrics.py
------------------------
Segment-level acoustic observations for Vocal Quality Engine.
Reuses physiology proxy metric functions with honest naming.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from audio_analyzer.physiology.metrics import (
    compute_cepstral_prominence_proxy_db,
    compute_f0_frame_period_perturbation_proxy_percent,
    compute_hnr_ac_proxy_db,
    compute_onset_slope_db_per_sec,
    compute_raw_h1_h2_proxy_db,
    compute_spectral_tilt_db_per_oct,
)

from . import config as cfg


def _median_f0_in_window(
    pitch: dict[str, Any], start: float, end: float
) -> Optional[float]:
    vals = []
    for fr in pitch.get("frame_f0") or []:
        t = fr.get("time_sec")
        hz = fr.get("f0_hz")
        if t is None or hz is None:
            continue
        if float(start) <= float(t) < float(end):
            vals.append(float(hz))
    if not vals:
        return None
    return float(np.median(vals))


def _voiced_ratio_in_window(
    pitch: dict[str, Any], start: float, end: float, hop: float = 0.25
) -> float:
    frames = pitch.get("frame_f0") or []
    if not frames:
        return 0.0
    total = voiced = 0
    for fr in frames:
        t = fr.get("time_sec")
        if t is None:
            continue
        if float(start) <= float(t) < float(end):
            total += 1
            if fr.get("f0_hz") is not None:
                voiced += 1
    return float(voiced / total) if total else 0.0


def _spectral_centroid_hz(y: np.ndarray, sr: int) -> Optional[float]:
    if len(y) < 512:
        return None
    n_fft = min(2048, int(2 ** np.ceil(np.log2(len(y)))))
    mag = np.abs(np.fft.rfft(y * np.hanning(len(y)), n=n_fft))
    freqs = np.fft.rfftfreq(n_fft, d=1.0 / sr)
    w = mag + 1e-12
    return float(np.sum(freqs * w) / np.sum(w))


def _periodicity_establishment_ratio(y: np.ndarray, sr: int, f0: Optional[float]) -> Optional[float]:
    """Fraction of early window where AC peak is strong. Experimental."""
    if y is None or len(y) < int(0.08 * sr):
        return None
    win = y[: int(0.12 * sr)]
    # compare first half vs second half HNR proxy
    mid = len(win) // 2
    a = compute_hnr_ac_proxy_db(win[:mid], sr, f0_hz=f0)
    b = compute_hnr_ac_proxy_db(win[mid:], sr, f0_hz=f0)
    if a is None or b is None:
        return None
    # higher second half relative to first → slower establishment
    return float(np.clip((b - a) / 20.0 + 0.5, 0.0, 1.0))


def segment_observations(
    y: np.ndarray,
    sr: int,
    start: float,
    end: float,
    pitch: dict[str, Any],
) -> dict[str, Any]:
    a = int(start * sr)
    b = max(a + 1, int(end * sr))
    chunk = np.asarray(y[a:b], dtype=np.float32)
    rms = float(np.sqrt(np.mean(chunk**2))) if len(chunk) else 0.0
    f0 = _median_f0_in_window(pitch, start, end)
    vratio = _voiced_ratio_in_window(pitch, start, end)

    # Periodicity family: pick PRIMARY metric (cepstral). HNR stored but same family.
    cpp = compute_cepstral_prominence_proxy_db(chunk, sr, f0_hz=f0)
    hnr = compute_hnr_ac_proxy_db(chunk, sr, f0_hz=f0)
    # Prefer cepstral when both valid; family value = cpp if present else hnr
    periodicity_primary = cpp if cpp is not None else hnr
    periodicity_source = (
        "cepstral_prominence_proxy_db" if cpp is not None else "hnr_ac_proxy_db"
    )

    h1h2 = compute_raw_h1_h2_proxy_db(chunk, sr, f0)
    tilt = compute_spectral_tilt_db_per_oct(chunk, sr)
    centroid = _spectral_centroid_hz(chunk, sr)
    onset = compute_onset_slope_db_per_sec(chunk, sr)
    est = _periodicity_establishment_ratio(chunk, sr, f0)

    # F0 frames in window for perturbation
    times, f0s = [], []
    for fr in pitch.get("frame_f0") or []:
        t = fr.get("time_sec")
        hz = fr.get("f0_hz")
        if t is None:
            continue
        if float(start) <= float(t) < float(end):
            times.append(float(t))
            f0s.append(float(hz) if hz is not None else np.nan)
    perturb = None
    if times:
        perturb = compute_f0_frame_period_perturbation_proxy_percent(
            np.asarray(times), np.asarray(f0s, dtype=float)
        )

    valid = bool(vratio >= cfg.MIN_VOICED_RATIO and len(chunk) >= sr // 4 and rms > 1e-5)
    return {
        "start_sec": round(float(start), 3),
        "end_sec": round(float(end), 3),
        "valid": valid,
        "voiced_ratio": round(vratio, 4),
        "rms": round(rms, 6),
        "median_f0_hz": None if f0 is None else round(f0, 2),
        "observations": {
            "periodicity_primary_db": periodicity_primary,
            "periodicity_source": periodicity_source,
            "cepstral_prominence_proxy_db": cpp,
            "hnr_ac_proxy_db": hnr,  # same family — not counted separately
            "raw_h1_h2_proxy_db": h1h2,
            "spectral_tilt_db_per_oct": tilt,
            "spectral_centroid_hz": centroid,
            "f0_frame_period_perturbation_proxy_percent": perturb,
            "onset_slope_db_per_sec": onset,
            "periodicity_establishment_ratio": est,
        },
    }
