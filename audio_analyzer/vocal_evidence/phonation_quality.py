"""Shared breathiness / roughness evidence families (VQ + Functional).

Interpretation (aggregation) stays in each engine; evidence routing is shared.
"""

from __future__ import annotations

from typing import Any, Optional


# Soft directional cues — uncalibrated; not clinical thresholds
BREATHY_PERIOD_DB = 8.0
BREATHY_H1H2_DB = 7.0
BREATHY_TILT = -16.0
BREATHY_OQ = 0.58

ROUGH_PERIOD_DB = 6.0
ROUGH_PERTURB = 2.5
ROUGH_DROPOUT = 0.15


def _obs(seg: dict[str, Any]) -> dict[str, Any]:
    return seg.get("observations") or {}


def _src(seg: dict[str, Any]) -> dict[str, Any]:
    return ((seg.get("level2_proxies") or {}).get("glottal_source") or {})


def vocal_presence_ok(seg: dict[str, Any]) -> bool:
    """Phonatory / vocal energy present — not silence or pure noise.

    Presence ≠ periodic voicing: breathy phonation may have weak F0/periodicity.
    """
    obs = _obs(seg)
    rms = obs.get("rms")
    if rms is None:
        rms = seg.get("rms")
    # Explicit near-silence rejects; missing rms allowed when proxies exist
    if rms is not None and float(rms) <= 1e-5:
        return False
    ve = seg.get("vocal_evidence") or {}
    if ve.get("vocal_energy") is not None and float(ve["vocal_energy"]) <= 0:
        return False
    # Reject clear accompaniment-only
    if (ve.get("accompaniment_match") or 0) >= 0.85 and (ve.get("vocal_dominance") or 0) < 0.35:
        return False
    period = obs.get("periodicity_primary_db")
    has_proxy = (
        period is not None
        or obs.get("raw_h1_h2_proxy_db") is not None
        or obs.get("spectral_tilt_db_per_oct") is not None
        or obs.get("spectral_centroid_hz") is not None
    )
    if rms is None and not has_proxy:
        return False
    voiced = seg.get("voiced_ratio")
    # Very low voiced + no periodicity + no spectral proxy → not phonatory
    if voiced is not None and float(voiced) < 0.08 and not has_proxy:
        return False
    return True


def breathy_family_flags(seg: dict[str, Any]) -> dict[str, Any]:
    """
    Independent breathy families (no double-count within family).
    A. PERIODICITY/NOISE — CPP/HNR primary (same family)
    B. HARMONIC/SPECTRAL — H1-H2 or tilt
    C. GLOTTAL_SOURCE — OQ/NAQ leakier-like when GIF valid
    """
    obs = _obs(seg)
    src = _src(seg)
    per = obs.get("periodicity_primary_db")
    h1h2 = obs.get("raw_h1_h2_proxy_db")
    tilt = obs.get("spectral_tilt_db_per_oct")

    periodicity_noise = per is not None and float(per) <= BREATHY_PERIOD_DB
    harmonic_spectral = False
    if h1h2 is not None and float(h1h2) >= BREATHY_H1H2_DB:
        harmonic_spectral = True
    if tilt is not None and float(tilt) <= BREATHY_TILT:
        harmonic_spectral = True

    glottal_source = False
    if src.get("valid"):
        oq = src.get("estimated_oq_proxy")
        naq = src.get("estimated_naq")
        if oq is not None and float(oq) >= BREATHY_OQ:
            glottal_source = True
        if naq is not None and float(naq) >= 0.15:
            glottal_source = True

    available = []
    if per is not None:
        available.append("periodicity_noise")
    if h1h2 is not None or tilt is not None:
        available.append("harmonic_spectral")
    if src.get("valid"):
        available.append("glottal_source")

    return {
        "periodicity_noise": periodicity_noise,
        "harmonic_spectral": harmonic_spectral,
        "glottal_source": glottal_source,
        "available_families": available,
        "n_positive": sum(
            [periodicity_noise, harmonic_spectral, glottal_source]
        ),
    }


def breathy_negative_flags(seg: dict[str, Any]) -> dict[str, Any]:
    """Explicit anti-breathy evidence (not merely missing positive)."""
    obs = _obs(seg)
    per = obs.get("periodicity_primary_db")
    h1h2 = obs.get("raw_h1_h2_proxy_db")
    tilt = obs.get("spectral_tilt_db_per_oct")
    neg = 0
    details = []
    if per is not None and float(per) >= 10.0:
        neg += 1
        details.append("periodicity_preserved")
    if h1h2 is not None and float(h1h2) <= 3.0:
        neg += 1
        details.append("h1h2_not_breathy")
    if tilt is not None and float(tilt) >= -12.0:
        neg += 1
        details.append("tilt_not_breathy")
    return {"n_negative": neg, "details": details, "strong": neg >= 2}


def classify_breathy_segment(seg: dict[str, Any]) -> dict[str, Any]:
    """
    Returns verdict: POSITIVE | NEGATIVE | INSUFFICIENT
    GIF invalid does NOT force INSUFFICIENT if other families available.
    """
    if not vocal_presence_ok(seg):
        return {
            "verdict": "INSUFFICIENT",
            "reason": "no_vocal_presence",
            "families": {},
            "negative": {},
        }
    fam = breathy_family_flags(seg)
    neg = breathy_negative_flags(seg)
    n_avail = len(fam.get("available_families") or [])
    if n_avail < 1:
        return {
            "verdict": "INSUFFICIENT",
            "reason": "no_breathy_families_computable",
            "families": fam,
            "negative": neg,
        }
    if fam["n_positive"] >= 2:
        return {
            "verdict": "POSITIVE",
            "reason": "multi_family_breathy",
            "families": fam,
            "negative": neg,
        }
    if fam["n_positive"] == 1 and n_avail >= 2 and not neg.get("strong"):
        # single family with other families computable but not positive → weak / insufficient for hit
        return {
            "verdict": "INSUFFICIENT",
            "reason": "single_family_only",
            "families": fam,
            "negative": neg,
        }
    if fam["n_positive"] == 0 and neg.get("strong"):
        return {
            "verdict": "NEGATIVE",
            "reason": "explicit_anti_breathy",
            "families": fam,
            "negative": neg,
        }
    if fam["n_positive"] == 0 and n_avail >= 2:
        return {
            "verdict": "NEGATIVE",
            "reason": "evaluable_no_positive",
            "families": fam,
            "negative": neg,
        }
    return {
        "verdict": "INSUFFICIENT",
        "reason": "weak_or_partial",
        "families": fam,
        "negative": neg,
    }


def rough_family_flags(seg: dict[str, Any]) -> dict[str, Any]:
    """
    Roughness needs irregularity-specific evidence — CPP drop alone is NOT enough.
    A. PERIODICITY_LOSS
    B. IRREGULARITY (perturbation)
    C. DROPOUT / discontinuity
    """
    obs = _obs(seg)
    per = obs.get("periodicity_primary_db")
    perturb = obs.get("f0_frame_period_perturbation_proxy_percent")
    dropout = obs.get("f0_dropout_ratio")

    periodicity_loss = per is not None and float(per) <= ROUGH_PERIOD_DB
    irregularity = perturb is not None and float(perturb) >= ROUGH_PERTURB
    dropout_flag = dropout is not None and float(dropout) >= ROUGH_DROPOUT

    return {
        "periodicity_loss": periodicity_loss,
        "irregularity": irregularity,
        "dropout": dropout_flag,
        "n_positive": sum([periodicity_loss, irregularity, dropout_flag]),
        "has_irregularity_specific": bool(irregularity or dropout_flag),
    }


def classify_rough_segment(seg: dict[str, Any]) -> dict[str, Any]:
    if not vocal_presence_ok(seg):
        return {"verdict": "INSUFFICIENT", "reason": "no_vocal_presence", "families": {}}
    fam = rough_family_flags(seg)
    # Hard rule: periodicity loss alone ≠ rough
    if fam["periodicity_loss"] and not fam["has_irregularity_specific"]:
        return {
            "verdict": "REJECTED",
            "reason": "periodicity_loss_without_irregularity",
            "families": fam,
        }
    if fam["has_irregularity_specific"] and (
        fam["periodicity_loss"] or fam["irregularity"]
    ):
        return {
            "verdict": "POSITIVE",
            "reason": "irregularity_specific",
            "families": fam,
        }
    if fam["irregularity"] and fam["dropout"]:
        return {
            "verdict": "POSITIVE",
            "reason": "irregularity_and_dropout",
            "families": fam,
        }
    return {
        "verdict": "NEGATIVE" if fam["n_positive"] == 0 else "INSUFFICIENT",
        "reason": "no_rough_hit",
        "families": fam,
    }


def disambiguate_breathy_vs_rough(seg: dict[str, Any]) -> dict[str, Any]:
    b = classify_breathy_segment(seg)
    r = classify_rough_segment(seg)
    label = "NEITHER"
    if b["verdict"] == "POSITIVE" and r["verdict"] == "POSITIVE":
        label = "MIXED"
    elif b["verdict"] == "POSITIVE":
        label = "BREATHY"
    elif r["verdict"] == "POSITIVE":
        label = "ROUGH"
    return {"label": label, "breathy": b, "rough": r}
