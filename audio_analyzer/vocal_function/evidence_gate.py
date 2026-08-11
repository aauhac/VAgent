"""
Vocal Evidence Gate — every functional claim needs vocal-specific evidence.

v2.10: separates vocal attribution from pitch-tracking confidence.
Legacy vocal_specific remains as compatibility (= VOCAL_CONFIRMED).
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from audio_analyzer.vocal_function import config as cfg
from audio_analyzer.vocal_function.vocal_attribution import (
    STATE_CONFIRMED,
    classify_segment_vocal_attribution,
    claim_vocal_suitability,
)

# Confidence for main UI cards (negative conclusions also need this)
MAIN_DISPLAY_MIN = "medium"  # hide "low"


def _rms(x: np.ndarray) -> float:
    if x is None or len(x) == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.asarray(x, dtype=float) ** 2)) + 1e-12)


def _band_energy(y: np.ndarray, sr: int, lo: float, hi: float) -> float:
    if y is None or len(y) < 64:
        return 0.0
    spec = np.abs(np.fft.rfft(y * np.hanning(len(y)))) ** 2
    freqs = np.fft.rfftfreq(len(y), 1.0 / sr)
    m = (freqs >= lo) & (freqs < hi)
    return float(np.sum(spec[m]) + 1e-12)


def spectral_transition_score(y: np.ndarray, sr: int, start: float, end: float) -> float:
    """Crude mid-band energy change across window halves."""
    a, b = int(start * sr), int(end * sr)
    chunk = y[max(0, a) : min(len(y), b)]
    if len(chunk) < sr // 4:
        return 0.0
    mid = len(chunk) // 2
    e1 = _band_energy(chunk[:mid], sr, 500, 4000)
    e2 = _band_energy(chunk[mid:], sr, 500, 4000)
    return float(abs(np.log10(e2 / e1)))


def normalize_artifact_flags(artifact_flags: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Map pipeline flag names onto gate keys."""
    af = dict(artifact_flags or {})
    if af.get("demucs_high_band_loss_likely") or af.get("high_band_loss_likely"):
        af["high_freq_loss"] = True
        af["separation_artifact"] = True
    if af.get("relative_low_mid_inflation_likely"):
        af["separation_bleed"] = True
        af["separation_artifact"] = True
    return af


def segment_vocal_evidence(
    *,
    y_vocals: np.ndarray,
    sr: int,
    start_sec: float,
    end_sec: float,
    pitch: dict[str, Any],
    segment_obs: Optional[dict[str, Any]] = None,
    y_no_vocals: Optional[np.ndarray] = None,
    artifact_flags: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    LEVEL-0 gate for one window.

    Returns legacy vocal_specific (= VOCAL_CONFIRMED) plus vocal_attribution packet.
    """
    af = normalize_artifact_flags(artifact_flags)
    a, b = int(start_sec * sr), int(end_sec * sr)
    vchunk = y_vocals[max(0, a) : min(len(y_vocals), b)]
    vocal_energy = _rms(vchunk)

    no_e = 0.0
    stem_present = y_no_vocals is not None and len(y_no_vocals) > 0
    if stem_present:
        nchunk = y_no_vocals[max(0, a) : min(len(y_no_vocals), b)]
        if len(nchunk) > 0:
            no_e = _rms(nchunk)

    ratio = vocal_energy / (no_e + 1e-12) if stem_present else None
    if stem_present:
        vocal_dominance = float(vocal_energy / (vocal_energy + no_e + 1e-12))
    else:
        vocal_dominance = float(min(1.0, (segment_obs or {}).get("voiced_ratio") or 0.0))

    # F0 / voicing from pitch frames in window (TRACKING — not universal anti-vocal)
    frames = pitch.get("frame_f0") or []
    f0s = []
    for fr in frames:
        t = fr.get("time_sec")
        hz = fr.get("f0_hz")
        if t is None:
            continue
        if float(start_sec) <= float(t) < float(end_sec) and hz and float(hz) > 0:
            f0s.append(float(hz))
    voiced_n = len(f0s)
    total_est = max(1, int((end_sec - start_sec) / 0.01))
    voicing_confidence = min(1.0, voiced_n / max(3, total_est * 0.3))
    f0_confidence = min(1.0, voiced_n / 5.0) if f0s else 0.0

    obs = (segment_obs or {}).get("observations") or segment_obs or {}
    period = obs.get("periodicity_primary_db")
    periodicity_confidence = (
        min(1.0, max(0.0, float(period) / 15.0)) if period is not None else 0.0
    )
    voiced_ratio = (segment_obs or {}).get("voiced_ratio")

    # Accompaniment contamination: same spectral transition in both stems
    accomp_match = 0.0
    if stem_present:
        tv = spectral_transition_score(y_vocals, sr, start_sec, end_sec)
        tn = spectral_transition_score(y_no_vocals, sr, start_sec, end_sec)
        if tv > 0.15 and tn > 0.15:
            accomp_match = float(min(1.0, tn / (tv + 1e-12)))

    sep_risk = "high" if af.get("separation_artifact") or af.get("high_freq_loss") else "low"
    if accomp_match >= 0.7:
        sep_risk = "high"

    attribution = classify_segment_vocal_attribution(
        vocal_dominance=vocal_dominance,
        vocal_vs_instrumental_ratio=ratio,
        vocal_energy=vocal_energy,
        f0_confidence=f0_confidence,
        voicing_confidence=voicing_confidence,
        periodicity_confidence=periodicity_confidence,
        accompaniment_match=accomp_match,
        separation_artifact_risk=sep_risk,
        stem_present=stem_present,
        voiced_ratio=float(voiced_ratio) if voiced_ratio is not None else None,
    )

    # Legacy compatibility: vocal_specific == CONFIRMED only
    vocal_specific = attribution["state"] == STATE_CONFIRMED
    # Keep reject_reasons as attribution reason_codes (no longer treat F0 alone as non-vocal)
    reasons = list(attribution.get("reason_codes") or [])

    # Split confidences (do not force one universal mean that over-weights F0)
    vocal_confidence = float(attribution.get("confidence_score") or 0.0)
    tracking_confidence = float((attribution.get("tracking") or {}).get("tracking_confidence") or 0.0)

    claim_suitability = {
        fam: claim_vocal_suitability(fam, attribution)
        for fam in ("effort", "breathiness", "contact", "roughness", "register", "onset", "resonance")
    }

    return {
        "vocal_specific": bool(vocal_specific),
        "vocal_confidence": round(vocal_confidence, 3),
        "vocal_dominance": round(vocal_dominance, 3),
        "voicing_confidence": round(voicing_confidence, 3),
        "f0_confidence": round(f0_confidence, 3),
        "periodicity_confidence": round(periodicity_confidence, 3),
        "vocal_energy": round(vocal_energy, 6),
        "no_vocals_energy": round(no_e, 6),
        "vocal_vs_instrumental_ratio": None if ratio is None else round(float(ratio), 3),
        "accompaniment_match": round(accomp_match, 3),
        "artifact_risk": sep_risk,
        "separation_artifact_risk": sep_risk,
        "harmonic_vocal_confidence": round(periodicity_confidence * f0_confidence, 3),
        "reject_reasons": reasons,
        # v2.10 additive
        "vocal_attribution": attribution,
        "vocal_attribution_state": attribution["state"],
        "vocal_attribution_confidence": attribution.get("confidence_score"),
        "tracking_confidence": round(tracking_confidence, 3),
        "tracking": attribution.get("tracking"),
        "contamination": attribution.get("contamination"),
        "claim_suitability": claim_suitability,
    }


def accompaniment_contamination_at(
    y_vocals: np.ndarray,
    y_no_vocals: np.ndarray,
    sr: int,
    start_sec: float,
    end_sec: float,
) -> dict[str, Any]:
    tv = spectral_transition_score(y_vocals, sr, start_sec, end_sec)
    tn = spectral_transition_score(y_no_vocals, sr, start_sec, end_sec)
    match = float(min(1.0, tn / (tv + 1e-12))) if tv > 0.1 and tn > 0.1 else 0.0
    contaminated = match >= 0.7 and tn >= 0.15
    return {
        "possible_accompaniment_contamination": contaminated,
        "vocals_transition": tv,
        "no_vocals_transition": tn,
        "accompaniment_match": match,
        "reason_code": "ACCOMPANIMENT_CONTAMINATION" if contaminated else None,
    }
