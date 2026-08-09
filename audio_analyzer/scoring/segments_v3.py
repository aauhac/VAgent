"""
scoring/segments_v3.py
----------------------
Time-window segment metrics for projection / resonance / dynamic axes.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from audio_analyzer.legacy.acoustic_metrics import compute_core_acoustic_metrics

from . import config_v3 as cfg


def build_windows(duration_sec: float, *, max_windows: int = 24) -> list[tuple[float, float]]:
    if duration_sec <= 0:
        return []
    win = cfg.SEGMENT_WINDOW_SEC
    hop = cfg.SEGMENT_HOP_SEC
    out: list[tuple[float, float]] = []
    t = 0.0
    while t + win * 0.5 < duration_sec:
        end = min(duration_sec, t + win)
        if end - t >= win * 0.6:
            out.append((round(t, 3), round(end, 3)))
        t += hop
    if not out and duration_sec >= 1.0:
        out.append((0.0, round(duration_sec, 3)))
    # Cap compute: uniformly subsample windows for long songs
    if len(out) > max_windows:
        idx = np.linspace(0, len(out) - 1, max_windows)
        out = [out[int(round(i))] for i in idx]
    return out


def _segment_active(y: np.ndarray, sr: int, start: float, end: float, peak_rms: float) -> bool:
    a = int(start * sr)
    b = int(end * sr)
    chunk = y[a:b]
    if len(chunk) < sr // 4:
        return False
    rms = float(np.sqrt(np.mean(chunk**2)))
    return rms >= peak_rms * cfg.SEGMENT_MIN_RMS_RATIO


def compute_spectral_segments(
    y: np.ndarray,
    sr: int,
) -> list[dict[str, Any]]:
    duration = len(y) / float(sr)
    windows = build_windows(duration)
    if not windows:
        return []
    peak_rms = float(np.sqrt(np.mean(y**2))) + 1e-9
    # Use a slightly higher local peak for activity
    frame_rms = np.sqrt(
        np.maximum(
            np.convolve(y**2, np.ones(sr // 10) / max(sr // 10, 1), mode="same"),
            0,
        )
    )
    peak_rms = float(np.max(frame_rms)) + 1e-9

    segs: list[dict[str, Any]] = []
    for start, end in windows:
        if not _segment_active(y, sr, start, end, peak_rms):
            continue
        a = int(start * sr)
        b = max(a + 1, int(end * sr))
        chunk = y[a:b]
        try:
            m = compute_core_acoustic_metrics(chunk, sr)
        except Exception:
            continue
        segs.append(
            {
                "start_sec": start,
                "end_sec": end,
                "spr_db": m.get("spr_db"),
                "singer_formant_prominence_db": m.get("singer_formant_prominence_db"),
                "weight_gap_db": m.get("weight_gap_db"),
                "mouth_gap_db": m.get("mouth_gap_db"),
                "spectral_slope_db_per_oct": m.get("spectral_slope_db_per_oct"),
            }
        )
    return segs


def compute_dynamic_segments(
    waveform: dict[str, Any],
    *,
    y: Optional[np.ndarray] = None,
    sr: Optional[int] = None,
) -> list[dict[str, Any]]:
    """Build dynamic segment stats from per-second summary or audio."""
    per_sec = list(waveform.get("per_second_summary") or [])
    if not per_sec and y is not None and sr:
        duration = len(y) / float(sr)
        windows = build_windows(duration)
        segs = []
        for start, end in windows:
            a = int(start * sr)
            b = max(a + 1, int(end * sr))
            chunk = y[a:b]
            if len(chunk) < sr // 5:
                continue
            # frame rms
            hop = 512
            frames = []
            for i in range(0, len(chunk) - hop, hop):
                fr = chunk[i : i + hop]
                frames.append(float(np.sqrt(np.mean(fr**2))))
            if len(frames) < 3:
                continue
            arr = np.asarray(frames, dtype=float)
            thr = float(np.max(arr)) * 0.05
            voiced = arr[arr >= thr]
            if len(voiced) < 2:
                continue
            dr = float(20 * np.log10(np.max(voiced) + 1e-10) - 20 * np.log10(np.min(voiced) + 1e-10))
            diffs = np.abs(np.diff(20 * np.log10(arr + 1e-10)))
            abrupt = float(np.mean(diffs >= cfg.ABRUPT_JUMP_DB))
            segs.append(
                {
                    "start_sec": start,
                    "end_sec": end,
                    "dynamic_range_db": round(dr, 2),
                    "abrupt_ratio": round(abrupt, 3),
                    "rms_std": round(float(np.std(arr)), 6),
                }
            )
        return segs

    # Fall back: group seconds into ~3s windows
    if not per_sec:
        return []
    segs = []
    win = max(1, int(cfg.SEGMENT_WINDOW_SEC))
    for i in range(0, len(per_sec), win):
        chunk = per_sec[i : i + win]
        rms = np.asarray([c.get("rms_mean") or 0.0 for c in chunk], dtype=float)
        if len(rms) < 1 or float(np.max(rms)) <= 1e-8:
            continue
        thr = float(np.max(rms)) * 0.05
        voiced = rms[rms >= thr]
        if len(voiced) < 1:
            continue
        dr = float(20 * np.log10(np.max(voiced) + 1e-10) - 20 * np.log10(np.min(voiced) + 1e-10))
        db = 20 * np.log10(rms + 1e-10)
        diffs = np.abs(np.diff(db)) if len(db) > 1 else np.asarray([0.0])
        abrupt = float(np.mean(diffs >= cfg.ABRUPT_JUMP_DB)) if len(diffs) else 0.0
        segs.append(
            {
                "start_sec": float(chunk[0].get("second", i)),
                "end_sec": float(chunk[-1].get("second", i) + 1),
                "dynamic_range_db": round(dr, 2),
                "abrupt_ratio": round(abrupt, 3),
                "rms_std": round(float(np.std(rms)), 6),
            }
        )
    return segs
