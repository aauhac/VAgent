"""
vocal_quality/evidence.py
-------------------------
Map segment observations → independent evidence families.
CPP and HNR are NOT independent (same periodicity family).
"""

from __future__ import annotations

from typing import Any, Optional

from . import config as cfg


def _flag(cond: bool) -> Optional[bool]:
    return bool(cond) if cond is not None else None


def segment_evidence_flags(obs: dict[str, Any]) -> dict[str, Any]:
    """Return per-family booleans for breathy / pressed / rough cues."""
    o = obs.get("observations") or {}
    per = o.get("periodicity_primary_db")
    tilt = o.get("spectral_tilt_db_per_oct")
    h1h2 = o.get("raw_h1_h2_proxy_db")
    onset = o.get("onset_slope_db_per_sec")
    perturb = o.get("f0_frame_period_perturbation_proxy_percent")
    centroid = o.get("spectral_centroid_hz")

    breathy_periodicity = per is not None and float(per) < cfg.BREATHY_CPP_LOW
    breathy_spectral = False
    if tilt is not None and float(tilt) <= cfg.BREATHY_TILT_STEEP:
        breathy_spectral = True
    if h1h2 is not None and float(h1h2) >= cfg.BREATHY_H1H2_HIGH:
        breathy_spectral = True

    pressed_periodicity = per is not None and float(per) > cfg.PRESSED_CPP_HIGH
    pressed_spectral = False
    if tilt is not None and float(tilt) >= cfg.PRESSED_TILT_FLAT:
        pressed_spectral = True
    if h1h2 is not None and float(h1h2) <= cfg.PRESSED_H1H2_LOW:
        pressed_spectral = True
    pressed_temporal = onset is not None and float(onset) >= cfg.PRESSED_ONSET_ABRUPT

    rough_periodicity = False
    if per is not None and float(per) < cfg.ROUGH_CPP_DROP:
        rough_periodicity = True
    if perturb is not None and float(perturb) >= cfg.ROUGH_PERTURB_HIGH:
        rough_periodicity = True

    return {
        "breathy": {
            "periodicity": breathy_periodicity,
            "spectral_or_harmonic": breathy_spectral,
            # intensity family intentionally unused for breathy HIGH
        },
        "pressed": {
            "periodicity": pressed_periodicity,
            "spectral_or_harmonic": pressed_spectral,
            "temporal_or_onset": pressed_temporal,
        },
        "rough": {
            "periodicity": rough_periodicity,
            "temporal": rough_periodicity,  # distribution handled at aggregation
        },
        "timbre": {
            "centroid_hz": centroid,
            "tilt": tilt,
            "h1h2": h1h2,
        },
        "onset": {
            "slope": onset,
            "establishment": o.get("periodicity_establishment_ratio"),
        },
    }


def count_true_families(family_flags: dict[str, bool]) -> int:
    return sum(1 for v in family_flags.values() if v is True)


def prevalence_label(ratio: float, *, any_hit: bool) -> str:
    if not any_hit or ratio <= 0:
        return "not_observed"
    if ratio < cfg.PREVALENCE_RARE:
        return "rare"
    if ratio < cfg.PREVALENCE_OCCASIONAL:
        return "occasional"
    if ratio < cfg.PREVALENCE_REPEATED:
        return "repeated"
    if ratio < cfg.PREVALENCE_DOMINANT:
        return "repeated"
    return "dominant"
