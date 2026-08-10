"""
Simplified IAIF-style glottal inverse filtering (Alku 1992 inspired).

This is an AUDIO PROXY, not a clinical glottal-flow measurement.
Does not claim equivalence to EGG closed quotient.
"""

from __future__ import annotations

from typing import Any, Optional, Tuple

import numpy as np
from scipy.signal import lfilter
import librosa

from . import config as cfg


def _preemphasis(x: np.ndarray, a: float = 0.97) -> np.ndarray:
    y = np.empty_like(x, dtype=float)
    y[0] = x[0]
    y[1:] = x[1:] - a * x[:-1]
    return y


def _safe_lpc(frame: np.ndarray, order: int) -> np.ndarray:
    order = max(1, min(order, len(frame) // 3))
    if len(frame) < order + 2:
        return np.array([1.0])
    try:
        a = librosa.lpc(frame * np.hanning(len(frame)), order=order)
        if not np.all(np.isfinite(a)):
            return np.array([1.0])
        return np.asarray(a, dtype=float)
    except Exception:
        return np.array([1.0])


def iaif_frame(
    frame: np.ndarray,
    *,
    nv: int = cfg.NV_DEFAULT,
    ng: int = cfg.NG_DEFAULT,
    d: float = cfg.LEAKY,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Returns (glottal_flow_estimate, vt_lpc, glottis_lpc, lip_lpc).
    """
    x = np.asarray(frame, dtype=float)
    if len(x) < 64:
        return x.copy(), np.array([1.0]), np.array([1.0]), np.array([1.0, -d])

    # Lip radiation inverse (leaky integration)
    lip = np.array([1.0, -d], dtype=float)
    x1 = lfilter([1.0], lip, x)

    # First estimate of glottal contribution
    ag1 = _safe_lpc(x1, ng)
    g1 = lfilter(ag1, [1.0], x1)

    # Vocal tract estimate on residual after removing first glottal estimate
    av = _safe_lpc(g1, nv)
    # Inverse filter speech with VT to get glottal flow
    ug = lfilter(av, [1.0], x1)

    # Refine glottal LPC on estimated flow
    ag = _safe_lpc(ug, ng)
    ug2 = lfilter(ag, [1.0], ug)

    return ug2, av, ag, lip


def inverse_filter_signal(
    y: np.ndarray,
    sr: int,
    f0_hz: Optional[float] = None,
) -> dict[str, Any]:
    """Frame-wise IAIF over a short segment; returns concatenated glottal estimate."""
    y = np.asarray(y, dtype=float)
    if len(y) < int(0.05 * sr):
        return {"valid": False, "reason": "too_short", "glottal_flow": None}

    frame_n = int(cfg.MAX_FRAME_SEC * sr)
    hop = int(cfg.HOP_SEC * sr)
    if f0_hz and f0_hz > 0:
        # Prefer ~2–3 periods per frame when F0 known
        frame_n = int(np.clip(3.0 * sr / f0_hz, cfg.MIN_FRAME_SEC * sr, cfg.MAX_FRAME_SEC * sr))

    flows = []
    vt_orders = []
    for i in range(0, max(1, len(y) - frame_n), hop):
        frame = y[i : i + frame_n]
        if len(frame) < frame_n // 2:
            break
        ug, av, ag, lip = iaif_frame(frame)
        flows.append(ug)
        vt_orders.append(len(av) - 1)

    if not flows:
        return {"valid": False, "reason": "no_frames", "glottal_flow": None}

    # Stitch by hop (simple; research-grade GCI alignment deferred)
    out = np.zeros(len(y), dtype=float)
    wsum = np.zeros(len(y), dtype=float)
    win = np.hanning(frame_n)
    for idx, ug in enumerate(flows):
        start = idx * hop
        n = min(len(ug), len(win), len(y) - start)
        if n <= 0:
            break
        out[start : start + n] += ug[:n] * win[:n]
        wsum[start : start + n] += win[:n]
    mask = wsum > 1e-8
    out[mask] /= wsum[mask]

    return {
        "valid": True,
        "reason": None,
        "glottal_flow": out,
        "method": cfg.GIF_METHOD,
        "mean_vt_order": float(np.mean(vt_orders)) if vt_orders else None,
        "f0_hz_used": f0_hz,
    }
