"""Vocal-tract / formant estimation (audio-only, style-aware descriptive)."""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
import librosa

from . import config as cfg


def estimate_formants(
    y: np.ndarray,
    sr: int,
    *,
    f0_hz: Optional[float] = None,
    n_formants: int = 5,
) -> dict[str, Any]:
    """LPC root formant estimate — confidence gated; no universal targets."""
    x = np.asarray(y, dtype=float)
    if len(x) < int(0.04 * sr):
        return {"valid": False, "reason": "too_short", "formants_hz": [], "confidence": 0.0}

    # Pre-emphasize
    x = np.append(x[0], x[1:] - 0.97 * x[:-1])
    order = min(cfg.LPC_ORDER, max(8, len(x) // 4))
    try:
        a = librosa.lpc(x * np.hanning(len(x)), order=order)
    except Exception:
        return {"valid": False, "reason": "lpc_failed", "formants_hz": [], "confidence": 0.0}

    roots = np.roots(a)
    roots = roots[np.imag(roots) >= 0]
    angs = np.arctan2(np.imag(roots), np.real(roots))
    freqs = sorted(angs * (sr / (2 * np.pi)))
    # Bandwidth proxy from root radius
    bw = []
    formants = []
    for r, ang in zip(roots, angs):
        f = abs(ang) * (sr / (2 * np.pi))
        if 90 < f < sr * 0.45:
            b = -np.log(np.abs(r) + 1e-12) * (sr / np.pi)
            formants.append(float(f))
            bw.append(float(b))
    pairs = sorted(zip(formants, bw), key=lambda t: t[0])
    formants = [p[0] for p in pairs][:n_formants]
    bw = [p[1] for p in pairs][:n_formants]

    # Confidence: spacing + F0 relation
    conf = 0.5
    if f0_hz and f0_hz > 200 and formants:
        # High F0: formants poorly resolved → lower confidence
        conf *= max(0.2, 1.0 - (f0_hz - 200) / 800.0)
    if len(formants) >= 2:
        conf = min(1.0, conf + 0.2)
    if any(b > 600 for b in bw[:2]):
        conf *= 0.7

    valid = len(formants) >= 2 and conf >= cfg.MIN_FORMANT_CONFIDENCE
    return {
        "valid": valid,
        "reason": None if valid else "low_confidence_or_sparse",
        "formants_hz": formants,
        "bandwidths_hz": bw,
        "confidence": float(conf),
        "f1_hz": formants[0] if formants else None,
        "f2_hz": formants[1] if len(formants) > 1 else None,
        "f3_hz": formants[2] if len(formants) > 2 else None,
        "f4_hz": formants[3] if len(formants) > 3 else None,
        "f5_hz": formants[4] if len(formants) > 4 else None,
        "grade": "B",
    }


def harmonic_formant_alignment(
    y: np.ndarray,
    sr: int,
    f0_hz: float,
    formants_hz: list[float],
) -> dict[str, Any]:
    """Proximity of H1/H2 to F1/F2 — descriptive, no universal ideal."""
    if not f0_hz or f0_hz <= 0 or not formants_hz:
        return {"available": False}
    spec = np.abs(np.fft.rfft(y * np.hanning(len(y))))
    freqs = np.fft.rfftfreq(len(y), 1.0 / sr)
    out = {}
    for hi, harm in enumerate([1, 2, 3], start=1):
        ht = harm * f0_hz
        if ht >= freqs[-1]:
            break
        idx = int(np.argmin(np.abs(freqs - ht)))
        nearest_f = min(formants_hz, key=lambda f: abs(f - ht))
        out[f"H{hi}_to_nearest_formant_hz"] = float(abs(nearest_f - ht))
        out[f"H{hi}_nearest_formant"] = float(nearest_f)
    out["available"] = True
    return out
