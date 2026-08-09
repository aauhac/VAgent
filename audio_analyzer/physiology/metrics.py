"""
physiology/metrics.py
---------------------
Acoustic metrics with honest proxy naming (physiology-metrics-v1.1).

Hostile audit findings:
- Our cepstral measure is a simplified Hillenbrand-style prominence, NOT
  Praat/ADSV CPPS → metric_id: cepstral_prominence_proxy_db
- Our AC HNR lacks Boersma (1993) window-AC normalization → hnr_ac_proxy_db
- H1-H2 is raw output spectrum, NOT formant-corrected H1*-H2*
  → raw_h1_h2_proxy_db
- Frame-F0 period diffs are NOT clinical cycle jitter
  → f0_frame_period_perturbation_proxy_percent
- Fixed-window amplitude peaks are NOT clinical shimmer
  → amplitude_window_shimmer_proxy_percent
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
from scipy.signal import find_peaks

from .config import METRIC_VERSION


def _metric(
    metric_id: str,
    value: Optional[float],
    *,
    unit: str,
    valid: bool,
    confidence: float,
    source_task: str,
    notes: Optional[list[str]] = None,
    measurement_condition: str = "",
    attempts_used: Optional[list[int]] = None,
) -> dict[str, Any]:
    return {
        "metric_id": metric_id,
        "value": None if value is None else round(float(value), 4),
        "unit": unit,
        "valid": bool(valid),
        "confidence": round(float(confidence), 3),
        "source_task": source_task,
        "attempts_used": attempts_used or [],
        "measurement_condition": measurement_condition,
        "metric_version": METRIC_VERSION,
        "notes": notes or [],
    }


def compute_cepstral_prominence_proxy_db(
    y: np.ndarray,
    sr: int,
    *,
    f0_hz: Optional[float] = None,
    pitch_floor: float = 60.0,
    pitch_ceiling: float = 300.0,
) -> Optional[float]:
    """
    Simplified cepstral peak prominence proxy (dB).

    Inspired by Hillenbrand et al. (1994) CPP idea, but NOT identical to
    validated CPPS/Praat implementations (no frame smoothing; OLS trend).
    """
    if y is None or len(y) < int(0.05 * sr):
        return None
    # Hamming windowed FFT magnitude spectrum → log → IFFT → real cepstrum
    n = int(2 ** np.ceil(np.log2(len(y))))
    win = np.hamming(len(y))
    spec = np.fft.rfft(y * win, n=n)
    log_mag = np.log(np.abs(spec) + 1e-12)
    cepstrum = np.fft.irfft(log_mag)
    # quefrency axis (seconds)
    quef = np.arange(len(cepstrum)) / float(sr)
    q_lo = 1.0 / pitch_ceiling
    q_hi = 1.0 / pitch_floor
    mask = (quef >= q_lo) & (quef <= q_hi)
    if not np.any(mask):
        return None
    # Power cepstrum in dB-like scale
    power_db = 20.0 * np.log10(np.abs(cepstrum) + 1e-12)
    # Prefer peak near expected period if F0 known
    search = power_db.copy()
    search[~mask] = -np.inf
    if f0_hz and f0_hz > 0:
        target_q = 1.0 / f0_hz
        # weight near expected quefrency
        weight = np.exp(-0.5 * ((quef - target_q) / (0.15 * target_q + 1e-6)) ** 2)
        search = search + 3.0 * weight
        search[~mask] = -np.inf
    peak_idx = int(np.argmax(search))
    if not np.isfinite(search[peak_idx]):
        return None
    # Trend line on background (exclude very low quefrency < 0.001s like Hillenbrand)
    trend_mask = (quef >= 0.001) & (quef <= q_hi)
    if int(np.sum(trend_mask)) < 10:
        return None
    x = quef[trend_mask]
    yy = power_db[trend_mask]
    # Least squares linear fit (documented deviation from Praat robust default)
    coef = np.polyfit(x, yy, 1)
    trend_at_peak = float(np.polyval(coef, quef[peak_idx]))
    cpp = float(power_db[peak_idx] - trend_at_peak)
    return cpp


# Back-compat alias (do not use in new observations)
compute_cpp_db = compute_cepstral_prominence_proxy_db


def compute_hnr_ac_proxy_db(
    y: np.ndarray,
    sr: int,
    *,
    f0_hz: Optional[float] = None,
    pitch_floor: float = 60.0,
    pitch_ceiling: float = 400.0,
) -> Optional[float]:
    """
    Simplified autocorrelation HNR proxy (dB).

    Formula family matches Boersma lag-domain HNR idea, but WITHOUT Praat's
    window-AC normalization / sinx/x lag interpolation → not Praat-identical.
    """
    if y is None or len(y) < int(0.05 * sr):
        return None
    y = y.astype(np.float64)
    y = y - np.mean(y)
    # Normalize energy
    energy = float(np.dot(y, y)) + 1e-12
    # Autocorrelation via FFT
    n = int(2 ** np.ceil(np.log2(2 * len(y) - 1)))
    fy = np.fft.rfft(y, n=n)
    ac = np.fft.irfft(fy * np.conj(fy), n=n)[: len(y)]
    ac = ac / (ac[0] + 1e-12)
    lag_lo = max(1, int(sr / pitch_ceiling))
    lag_hi = min(len(ac) - 1, int(sr / pitch_floor))
    if lag_hi <= lag_lo:
        return None
    segment = ac[lag_lo : lag_hi + 1]
    if f0_hz and f0_hz > 0:
        expected = int(sr / f0_hz)
        if lag_lo <= expected <= lag_hi:
            # local max near expected lag
            w = 3
            i0 = expected - lag_lo
            sl = segment[max(0, i0 - w) : i0 + w + 1]
            r_max = float(np.max(sl)) if len(sl) else float(np.max(segment))
        else:
            r_max = float(np.max(segment))
    else:
        r_max = float(np.max(segment))
    r_max = min(0.999, max(1e-6, r_max))
    hnr = 10.0 * np.log10(r_max / (1.0 - r_max))
    return float(hnr)


compute_hnr_ac_db = compute_hnr_ac_proxy_db


def compute_raw_h1_h2_proxy_db(
    y: np.ndarray, sr: int, f0_hz: Optional[float]
) -> Optional[float]:
    """
    Raw radiated-spectrum H1−H2 (dB). NOT formant-corrected H1*-H2*.

    Must not be interpreted as open quotient without Hanson/Iseli correction.
    """
    if y is None or f0_hz is None or f0_hz <= 0 or len(y) < sr // 10:
        return None
    n_fft = int(2 ** np.ceil(np.log2(max(len(y), 2048))))
    win = np.hamming(len(y))
    mag = np.abs(np.fft.rfft(y * win, n=n_fft))
    freqs = np.fft.rfftfreq(n_fft, d=1.0 / sr)

    def harm_db(k: int) -> Optional[float]:
        target = k * f0_hz
        if target >= sr / 2:
            return None
        bw = max(f0_hz * 0.1, sr / n_fft * 2)
        mask = (freqs >= target - bw) & (freqs <= target + bw)
        if not np.any(mask):
            return None
        return float(20.0 * np.log10(np.max(mag[mask]) + 1e-12))

    h1 = harm_db(1)
    h2 = harm_db(2)
    if h1 is None or h2 is None:
        return None
    return float(h1 - h2)


compute_h1_h2_db = compute_raw_h1_h2_proxy_db


def compute_spectral_tilt_db_per_oct(y: np.ndarray, sr: int) -> Optional[float]:
    if len(y) < 512:
        return None
    n_fft = 2048
    hop = 512
    # STFT mean power
    frames = []
    for i in range(0, len(y) - n_fft, hop):
        frame = y[i : i + n_fft] * np.hanning(n_fft)
        frames.append(np.abs(np.fft.rfft(frame)) ** 2)
    if not frames:
        return None
    mean_p = np.mean(np.stack(frames, axis=0), axis=0)
    freqs = np.fft.rfftfreq(n_fft, d=1.0 / sr)
    mask = (freqs >= 100) & (freqs <= 5000)
    if int(np.sum(mask)) < 10:
        return None
    x = np.log2(freqs[mask] + 1e-12)
    yy = 10.0 * np.log10(mean_p[mask] + 1e-12)
    slope, _ = np.polyfit(x, yy, 1)
    return float(slope)


def compute_f0_frame_period_perturbation_proxy_percent(
    times: np.ndarray,
    f0: np.ndarray,
) -> Optional[float]:
    """
    Frame-F0 derived period-to-period perturbation proxy (%).

    NOT clinical cycle-detected jitter. Invalid under vibrato / unstable F0.
    """
    valid = np.isfinite(f0) & (f0 > 0)
    f0v = f0[valid]
    if len(f0v) < 20:
        return None
    periods = 1.0 / f0v
    d = np.abs(np.diff(periods))
    mean_p = float(np.mean(periods))
    if mean_p <= 0:
        return None
    return float(100.0 * np.mean(d) / mean_p)


compute_local_jitter_percent = compute_f0_frame_period_perturbation_proxy_percent


def compute_amplitude_window_shimmer_proxy_percent(
    y: np.ndarray, sr: int, f0_hz: float
) -> Optional[float]:
    """Fixed mean-F0 window peak amplitude variation proxy (%). Not clinical shimmer."""
    if f0_hz <= 0 or len(y) < int(sr / f0_hz) * 10:
        return None
    period = int(sr / f0_hz)
    if period < 4:
        return None
    peaks = []
    for i in range(0, len(y) - period, period):
        peaks.append(float(np.max(np.abs(y[i : i + period]))))
    if len(peaks) < 10:
        return None
    peaks_a = np.asarray(peaks)
    d = np.abs(np.diff(peaks_a))
    return float(100.0 * np.mean(d) / (np.mean(peaks_a) + 1e-12))


compute_local_shimmer_percent = compute_amplitude_window_shimmer_proxy_percent


def compute_onset_slope_db_per_sec(y: np.ndarray, sr: int) -> Optional[float]:
    """Rise of RMS envelope over first ~150ms of voiced energy (dB/s). Not glottal attack."""
    hop = max(1, sr // 200)
    rms = []
    for i in range(0, len(y) - hop, hop):
        rms.append(float(np.sqrt(np.mean(y[i : i + hop] ** 2) + 1e-12)))
    if len(rms) < 5:
        return None
    arr = np.asarray(rms)
    thr = 0.15 * float(np.max(arr))
    idx = np.where(arr >= thr)[0]
    if len(idx) == 0:
        return None
    start = int(idx[0])
    end = min(len(arr) - 1, start + max(3, int(0.15 * sr / hop)))
    t0 = start * hop / sr
    t1 = end * hop / sr
    if t1 <= t0:
        return None
    db0 = 20.0 * np.log10(arr[start] + 1e-12)
    db1 = 20.0 * np.log10(arr[end] + 1e-12)
    return float((db1 - db0) / (t1 - t0))


def compute_release_drop_db(y: np.ndarray, sr: int) -> Optional[float]:
    """Drop in RMS from peak region to last 100ms (dB)."""
    if len(y) < sr // 5:
        return None
    hop = max(1, sr // 100)
    rms = np.array(
        [
            np.sqrt(np.mean(y[i : i + hop] ** 2) + 1e-12)
            for i in range(0, len(y) - hop, hop)
        ]
    )
    if len(rms) < 5:
        return None
    peak = float(np.percentile(rms, 90))
    tail = float(np.mean(rms[-max(2, int(0.1 * sr / hop)) :]))
    return float(20.0 * np.log10((peak + 1e-12) / (tail + 1e-12)))


def compute_envelope_smoothness(y: np.ndarray, sr: int) -> Optional[float]:
    """
    Smoothness proxy: 1 / (1 + mean abs 2nd derivative of log-RMS).
    Higher = smoother swell. Custom heuristic → metric_id envelope_smoothness_index.
    """
    hop = max(1, sr // 50)
    rms = np.array(
        [
            np.sqrt(np.mean(y[i : i + hop] ** 2) + 1e-12)
            for i in range(0, len(y) - hop, hop)
        ]
    )
    if len(rms) < 8:
        return None
    log_r = np.log(rms + 1e-12)
    d2 = np.diff(log_r, n=2)
    rough = float(np.mean(np.abs(d2)))
    return float(1.0 / (1.0 + 50.0 * rough))
