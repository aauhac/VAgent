"""
scoring/duration_policy_v3.py
-----------------------------
Deterministic vocal-active clip selection for long songs.

Does NOT cherry-pick the "best" singing. Selection is signal-only:
highest mean voiced-frame density in a fixed-length window.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from . import config_v3 as cfg


def build_voiced_mask(
    pitch: Optional[dict[str, Any]],
    *,
    duration_sec: float,
    hop_sec: float = 0.25,
) -> tuple[np.ndarray, float]:
    """Return (mask over time grid, hop_sec). True = voiced/F0 present."""
    n = max(1, int(np.ceil(duration_sec / hop_sec)))
    mask = np.zeros(n, dtype=bool)
    frames = list((pitch or {}).get("frame_f0") or [])
    if not frames:
        return mask, hop_sec
    for fr in frames:
        t = fr.get("time_sec")
        hz = fr.get("f0_hz")
        if t is None or hz is None:
            continue
        idx = int(float(t) / hop_sec)
        if 0 <= idx < n:
            mask[idx] = True
    return mask, hop_sec


def select_score_clip(
    duration_sec: float,
    pitch: Optional[dict[str, Any]],
    *,
    clip_sec: float = cfg.LONG_SONG_SCORE_CLIP_SEC,
    max_full_sec: float = cfg.RECOMMENDED_MAX_SCORE_SEC,
) -> dict[str, Any]:
    """
    If duration <= max_full_sec: use full audio.
    Else: pick contiguous clip_sec with max voiced density (deterministic).
    """
    duration_sec = float(duration_sec)
    if duration_sec <= max_full_sec + 1e-6:
        return {
            "policy": "full",
            "start_sec": 0.0,
            "end_sec": duration_sec,
            "clip_sec": duration_sec,
            "voiced_density": None,
            "truncated": False,
        }

    clip = min(float(clip_sec), duration_sec)
    mask, hop = build_voiced_mask(pitch, duration_sec=duration_sec)
    win = max(1, int(round(clip / hop)))
    if mask.size < win:
        return {
            "policy": "full_fallback",
            "start_sec": 0.0,
            "end_sec": duration_sec,
            "clip_sec": duration_sec,
            "voiced_density": float(np.mean(mask)) if mask.size else 0.0,
            "truncated": False,
        }

    # Sliding sum of voiced frames
    c = np.cumsum(mask.astype(np.float64))
    # sum of mask[i:i+win] = c[i+win-1] - c[i-1]
    dens = c[win - 1 :] - np.concatenate([[0.0], c[:-win]])
    best_i = int(np.argmax(dens))
    # tie-break: earliest index (argmax already picks first)
    start = best_i * hop
    end = min(duration_sec, start + clip)
    density = float(dens[best_i] / win) if win else 0.0
    return {
        "policy": "vocal_active_clip",
        "start_sec": round(start, 3),
        "end_sec": round(end, 3),
        "clip_sec": round(end - start, 3),
        "voiced_density": round(density, 4),
        "truncated": True,
        "note": (
            f"duration {duration_sec:.1f}s > {max_full_sec:.0f}s; "
            f"scoring uses deterministic vocal-active {clip:.0f}s clip"
        ),
    }


def slice_audio(
    y: np.ndarray,
    sr: int,
    start_sec: float,
    end_sec: float,
) -> np.ndarray:
    a = max(0, int(float(start_sec) * sr))
    b = min(len(y), max(a + 1, int(float(end_sec) * sr)))
    return np.asarray(y[a:b], dtype=np.float32)
