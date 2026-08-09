"""
preprocessing/preview.py
------------------------
Preview-only enhancement (never used for spectral/phonation scoring).
"""

from __future__ import annotations

import numpy as np

from audio_analyzer.legacy.vocal_enhancer import prepare_vocal_for_preview


def build_preview_signal(y: np.ndarray, sr: int) -> tuple[np.ndarray, dict]:
    """
    Create a listening-friendly preview copy.
    Falls back to raw analysis signal if enhancer is unavailable.
    """
    try:
        y_prev, report = prepare_vocal_for_preview(y, sr)
        return y_prev.astype(np.float32), {"method": "legacy_preview", **(report or {})}
    except Exception as exc:  # noqa: BLE001 — preview must never break analysis
        return y.astype(np.float32), {"method": "passthrough", "error": str(exc)}
