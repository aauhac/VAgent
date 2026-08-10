"""GIF validity gate — do not trust source params without these checks."""

from __future__ import annotations

from typing import Any, Optional

from . import config as cfg


def gif_validity(
    *,
    voiced_ratio: float,
    snr_proxy_db: Optional[float],
    f0_hz: Optional[float],
    periodicity_db: Optional[float],
    harmonic_confidence: Optional[float],
    vocal_dominant: bool,
    separation_artifact: bool,
    formant_confidence: Optional[float] = None,
) -> dict[str, Any]:
    reasons = []
    if not vocal_dominant:
        reasons.append("not_vocal_dominant")
    if voiced_ratio < cfg.MIN_VOICED_RATIO:
        reasons.append("low_voiced_ratio")
    if snr_proxy_db is not None and snr_proxy_db < cfg.MIN_SNR_PROXY_DB:
        reasons.append("low_snr_proxy")
    if f0_hz is None or not (cfg.MIN_F0_HZ <= f0_hz <= cfg.MAX_F0_HZ):
        reasons.append("unstable_or_missing_f0")
    if periodicity_db is not None and periodicity_db < cfg.MIN_PERIODICITY_DB:
        reasons.append("weak_periodicity")
    if harmonic_confidence is not None and harmonic_confidence < cfg.MIN_HARMONIC_CONF:
        reasons.append("weak_harmonic_structure")
    if separation_artifact:
        reasons.append("separation_artifact")
    if formant_confidence is not None and formant_confidence < 0.25:
        reasons.append("low_formant_confidence")

    ok = len(reasons) == 0
    return {
        "valid": ok,
        "reasons": reasons,
        "measurement_mode": cfg.MEASUREMENT_MODE_DEFAULT,
        "note": None
        if ok
        else "GIF/source parameters set to UNKNOWN due to validity gate.",
    }
