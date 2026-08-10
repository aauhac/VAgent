"""Glottal closure instant (GCI) proxies from estimated glottal flow derivative."""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
from scipy.signal import find_peaks


def estimate_gci(
    glottal_flow: np.ndarray,
    sr: int,
    f0_hz: Optional[float] = None,
) -> dict[str, Any]:
    """
    Peak of negative dU/dt ≈ GCI proxy (Alku / SE-DREAMS family idea).

    Returns sample indices — NOT ground-truth laryngoscopic GCI.
    """
    g = np.asarray(glottal_flow, dtype=float)
    if len(g) < 8:
        return {"valid": False, "gci_samples": [], "goi_samples": []}

    dg = np.diff(g, prepend=g[0])
    # Closure ≈ strong negative derivative peak
    neg = -dg
    min_dist = int(0.5 * sr / max(f0_hz or 150.0, 60.0))
    peaks, props = find_peaks(neg, distance=max(3, min_dist), prominence=np.std(neg) * 0.3 + 1e-12)
    # GOI proxy: positive derivative peaks between GCIs
    pos_peaks, _ = find_peaks(dg, distance=max(3, min_dist // 2), prominence=np.std(dg) * 0.25 + 1e-12)

    return {
        "valid": bool(len(peaks) >= 2),
        "gci_samples": peaks.tolist(),
        "goi_samples": pos_peaks.tolist(),
        "n_gci": int(len(peaks)),
        "f0_implied_hz": float(sr / np.median(np.diff(peaks))) if len(peaks) >= 2 else None,
    }
