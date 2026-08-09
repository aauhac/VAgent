"""
features/phonation.py
---------------------
Local sustained-note phonation analysis.

melody variation != vocal instability

We only measure residual fluctuation *inside* sustained regions
after removing each region's local F0 trend.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
from scipy.signal import medfilt, savgol_filter

# --- config (phonation heuristics; uncalibrated) ---
MIN_SUSTAIN_SEC = 0.5
MAX_FRAME_JUMP_CENTS = 45.0  # larger jumps → note transition
MERGE_GAP_SEC = 0.12
VIBRATO_MIN_SUSTAIN_SEC = 0.85
VIBRATO_BAND_HZ = (3.0, 8.0)
INSTABILITY_RESIDUAL_STD_CENTS = 35.0
INSTABILITY_MIN_REGION_SEC = 0.6


def _hz_to_cents(hz: np.ndarray, ref_hz: float) -> np.ndarray:
    return 1200.0 * np.log2((hz + 1e-10) / (ref_hz + 1e-10))


def _local_trend(cents: np.ndarray) -> np.ndarray:
    n = len(cents)
    if n < 5:
        return np.full(n, float(np.median(cents)))
    window = min(n if n % 2 == 1 else n - 1, 15)
    if window < 5:
        return np.full(n, float(np.median(cents)))
    try:
        return savgol_filter(cents, window_length=window, polyorder=2)
    except Exception:
        return medfilt(cents, kernel_size=min(5, n if n % 2 == 1 else n - 1) or 1)


def _rms_variation_db(y: np.ndarray, sr: int, start_sec: float, end_sec: float) -> float:
    start = int(start_sec * sr)
    end = int(end_sec * sr)
    chunk = y[max(0, start) : min(len(y), end)]
    if len(chunk) < sr // 20:
        return 0.0
    hop = 256
    vals = []
    for i in range(0, len(chunk) - hop, hop):
        frame = chunk[i : i + hop]
        vals.append(float(np.sqrt(np.mean(np.square(frame)) + 1e-20)))
    if not vals:
        return 0.0
    arr = np.asarray(vals)
    return float(20.0 * np.log10((np.max(arr) + 1e-12) / (np.min(arr) + 1e-12)))


def detect_sustained_regions(
    times: np.ndarray,
    f0_hz: np.ndarray,
    voiced_mask: np.ndarray,
    *,
    hop_sec: float,
    min_sustain_sec: float = MIN_SUSTAIN_SEC,
    max_jump_cents: float = MAX_FRAME_JUMP_CENTS,
    merge_gap_sec: float = MERGE_GAP_SEC,
) -> list[dict[str, Any]]:
    """
    Group consecutive voiced frames with small frame-to-frame F0 jumps
    into sustained note candidates.
    """
    idx = np.where(voiced_mask & np.isfinite(f0_hz) & (f0_hz > 0))[0]
    if len(idx) < 2:
        return []

    segments: list[list[int]] = []
    current = [int(idx[0])]
    for i in range(1, len(idx)):
        prev_i = int(idx[i - 1])
        cur_i = int(idx[i])
        gap_sec = float(times[cur_i] - times[prev_i])
        cents_jump = abs(1200.0 * np.log2((f0_hz[cur_i] + 1e-10) / (f0_hz[prev_i] + 1e-10)))
        if gap_sec <= merge_gap_sec and cents_jump <= max_jump_cents:
            current.append(cur_i)
        else:
            segments.append(current)
            current = [cur_i]
    segments.append(current)

    # Merge nearby segments with similar median F0
    merged: list[list[int]] = []
    for seg in segments:
        if not merged:
            merged.append(seg)
            continue
        prev = merged[-1]
        gap = float(times[seg[0]] - times[prev[-1]])
        med_prev = float(np.median(f0_hz[prev]))
        med_cur = float(np.median(f0_hz[seg]))
        cents_gap = abs(1200.0 * np.log2((med_cur + 1e-10) / (med_prev + 1e-10)))
        if gap <= merge_gap_sec and cents_gap <= max_jump_cents:
            merged[-1] = prev + seg
        else:
            merged.append(seg)

    regions: list[dict[str, Any]] = []
    for seg in merged:
        start_sec = float(times[seg[0]])
        end_sec = float(times[seg[-1]]) + hop_sec
        duration = end_sec - start_sec
        if duration < min_sustain_sec:
            continue
        hz = f0_hz[seg]
        median_hz = float(np.median(hz))
        cents = _hz_to_cents(hz, median_hz)
        trend = _local_trend(cents)
        residual = cents - trend
        regions.append(
            {
                "start_sec": round(start_sec, 3),
                "end_sec": round(end_sec, 3),
                "duration_sec": round(duration, 3),
                "median_f0_hz": round(median_hz, 2),
                "residual_std_cents": round(float(np.std(residual)), 2),
                "frame_indices": seg,
                "residual_cents": residual,
                "times": times[seg],
            }
        )
    return regions


def analyze_vibrato_on_regions(
    regions: list[dict[str, Any]],
    *,
    min_duration_sec: float = VIBRATO_MIN_SUSTAIN_SEC,
) -> dict[str, Any]:
    """
    Vibrato only on sufficiently long sustained regions.
    Absence of vibrato is NOT a negative skill signal.
    """
    rates: list[float] = []
    depths: list[float] = []
    regs: list[float] = []
    used = 0

    for region in regions:
        if float(region["duration_sec"]) < min_duration_sec:
            continue
        residual = np.asarray(region["residual_cents"], dtype=float)
        times = np.asarray(region["times"], dtype=float)
        if len(residual) < 16:
            continue
        dt = float(np.median(np.diff(times)))
        if dt <= 0:
            continue
        depth = float(np.percentile(residual, 95) - np.percentile(residual, 5)) / 2.0
        spectrum = np.abs(np.fft.rfft(residual - np.mean(residual)))
        freqs = np.fft.rfftfreq(len(residual), d=dt)
        mask = (freqs >= VIBRATO_BAND_HZ[0]) & (freqs <= VIBRATO_BAND_HZ[1])
        if not np.any(mask):
            continue
        sub_f = freqs[mask]
        sub_s = spectrum[mask]
        peak_i = int(np.argmax(sub_s))
        rate = float(sub_f[peak_i])
        regularity = float(np.max(sub_s) / (np.mean(sub_s) + 1e-10))
        regularity = min(1.0, regularity / 5.0)
        # Require some depth to count as vibrato-like
        if depth < 20.0 or regularity < 0.25:
            continue
        rates.append(rate)
        depths.append(depth)
        regs.append(regularity)
        used += 1

    if used == 0:
        return {
            "available": False,
            "rate_hz": None,
            "depth_cents": None,
            "regularity": None,
            "regions_used": 0,
            "note": "충분히 긴 지속음에서 규칙적인 비브라토가 측정되지 않았어요. 없어도 문제 없어요.",
        }

    return {
        "available": True,
        "rate_hz": round(float(np.median(rates)), 2),
        "depth_cents": round(float(np.median(depths)), 1),
        "regularity": round(float(np.median(regs)), 3),
        "regions_used": used,
        "note": "길게 유지한 음에서 측정된 참고 분석입니다.",
    }


def phonation_instability_events(
    regions: list[dict[str, Any]],
    *,
    residual_std_threshold: float = INSTABILITY_RESIDUAL_STD_CENTS,
    min_duration_sec: float = INSTABILITY_MIN_REGION_SEC,
) -> list[dict[str, Any]]:
    """
    Detect local phonation instability inside sustained regions only.
    Never uses global melody deviation from mean F0.
    """
    events: list[dict[str, Any]] = []
    for region in regions:
        if float(region["duration_sec"]) < min_duration_sec:
            continue
        std = float(region["residual_std_cents"])
        if std < residual_std_threshold:
            continue
        severity = "high" if std >= residual_std_threshold * 1.6 else "medium"
        conf = min(0.95, 0.55 + (std - residual_std_threshold) / 80.0)
        events.append(
            {
                "type": "phonation_instability",
                "start_sec": region["start_sec"],
                "end_sec": region["end_sec"],
                "severity": severity,
                "confidence": round(conf, 3),
                "user_message": (
                    "길게 유지한 일부 음에서 소리가 일정하게 유지되지 않는 구간이 측정됐어요."
                ),
                "detail": {
                    "residual_std_cents": region["residual_std_cents"],
                    "median_f0_hz": region["median_f0_hz"],
                    "duration_sec": region["duration_sec"],
                },
            }
        )
    return events


def extract_phonation_features(
    y: np.ndarray,
    sr: int,
    pitch_features: dict[str, Any],
) -> dict[str, Any]:
    """
    Build sustained-region phonation summary from pitch frame_f0.
    """
    frame_f0 = pitch_features.get("frame_f0") or []
    if not frame_f0:
        return {
            "sustained_regions": [],
            "median_residual_std_cents": None,
            "median_rms_variation_db": None,
            "sustained_count": 0,
            "vibrato": {"available": False, "regions_used": 0},
            "instability_events": [],
        }

    times = np.asarray([float(f["time_sec"]) for f in frame_f0], dtype=float)
    f0 = np.asarray(
        [np.nan if f.get("f0_hz") is None else float(f["f0_hz"]) for f in frame_f0],
        dtype=float,
    )
    voiced = np.isfinite(f0) & (f0 > 0)
    hop_sec = float(np.median(np.diff(times))) if len(times) > 1 else 512.0 / sr

    regions_raw = detect_sustained_regions(times, f0, voiced, hop_sec=hop_sec)

    public_regions = []
    residual_stds = []
    rms_vars = []
    for r in regions_raw:
        rms_var = _rms_variation_db(y, sr, r["start_sec"], r["end_sec"])
        r["rms_variation_db"] = round(rms_var, 2)
        residual_stds.append(float(r["residual_std_cents"]))
        rms_vars.append(rms_var)
        public_regions.append(
            {
                "start_sec": r["start_sec"],
                "end_sec": r["end_sec"],
                "duration_sec": r["duration_sec"],
                "median_f0_hz": r["median_f0_hz"],
                "residual_std_cents": r["residual_std_cents"],
                "rms_variation_db": r["rms_variation_db"],
            }
        )

    vibrato = analyze_vibrato_on_regions(regions_raw)
    events = phonation_instability_events(regions_raw)

    return {
        "sustained_regions": public_regions,
        "median_residual_std_cents": (
            None if not residual_stds else round(float(np.median(residual_stds)), 2)
        ),
        "median_rms_variation_db": (
            None if not rms_vars else round(float(np.median(rms_vars)), 2)
        ),
        "sustained_count": len(public_regions),
        "vibrato": vibrato,
        "instability_events": events,
        # keep raw for scoring internals (stripped from public API)
        "_regions_raw": regions_raw,
    }
