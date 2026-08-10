"""Contact vs effort evidence flags (independent axes)."""

from __future__ import annotations

from typing import Any

from audio_analyzer.vocal_function import config as cfg


def contact_flags(seg: dict[str, Any]) -> dict[str, bool]:
    obs = seg.get("observations") or {}
    src = ((seg.get("level2_proxies") or {}).get("glottal_source") or {})
    flags = {
        "glottal_flow": False,
        "harmonic": False,
        "periodicity": False,
        "spectral": False,
    }
    naq = src.get("estimated_naq") if src.get("valid") else None
    h1h2 = obs.get("raw_h1_h2_proxy_db")
    tilt = obs.get("spectral_tilt_db_per_oct")
    period = obs.get("periodicity_primary_db")

    # Directional only — no clinical thresholds
    if naq is not None:
        flags["glottal_flow"] = True  # usable family presence
    if h1h2 is not None:
        flags["harmonic"] = True
    if period is not None and period > 0:
        flags["periodicity"] = True
    if tilt is not None:
        flags["spectral"] = True
    return flags


def lighter_like(seg: dict[str, Any]) -> bool:
    obs = seg.get("observations") or {}
    src = ((seg.get("level2_proxies") or {}).get("glottal_source") or {})
    hits = 0
    if src.get("valid") and src.get("estimated_naq") is not None:
        if src["estimated_naq"] >= cfg.NAQ_LIGHTER_HINT:
            hits += 1
        if (src.get("estimated_oq_proxy") or 0) >= 0.55:
            hits += 1
    h1h2 = obs.get("raw_h1_h2_proxy_db")
    if h1h2 is not None and h1h2 >= cfg.H1H2_LIGHTER_DB:
        hits += 1
    tilt = obs.get("spectral_tilt_db_per_oct")
    if tilt is not None and tilt <= -14:
        hits += 1
    return hits >= 2


def firmer_like(seg: dict[str, Any]) -> bool:
    obs = seg.get("observations") or {}
    src = ((seg.get("level2_proxies") or {}).get("glottal_source") or {})
    hits = 0
    if src.get("valid") and src.get("estimated_naq") is not None:
        if src["estimated_naq"] <= cfg.NAQ_FIRMER_HINT:
            hits += 1
        if (src.get("estimated_mfdr_proxy") or 0) > 0:
            hits += 1
    h1h2 = obs.get("raw_h1_h2_proxy_db")
    if h1h2 is not None and h1h2 <= cfg.H1H2_FIRMER_DB:
        hits += 1
    e24 = obs.get("energy_2_4k")
    if e24 is not None and e24 >= 0.15:
        hits += 1
    return hits >= 2


def effort_like(seg: dict[str, Any], baseline: dict[str, Any] | None = None) -> bool:
    """
    Strain/effort is NOT firm contact alone.
    Needs multi-sign: compression-like + (roughness OR periodicity drop OR onset harden OR persistence).
    """
    obs = seg.get("observations") or {}
    src = ((seg.get("level2_proxies") or {}).get("glottal_source") or {})
    compression = firmer_like(seg)
    if not compression and not (
        src.get("valid") and (src.get("estimated_naq") or 1) <= cfg.NAQ_FIRMER_HINT
    ):
        # still allow effort without firm if strong roughness + intensity spike — rare
        compression = False

    rough = (obs.get("f0_frame_period_perturbation_proxy_percent") or 0) >= 2.5
    period_drop = (obs.get("periodicity_primary_db") or 99) <= 6.0
    onset_hard = (obs.get("onset_slope_db_per_sec") or 0) >= 80
    intensity_spike = False
    if baseline and baseline.get("rms") and obs.get("rms"):
        intensity_spike = float(obs["rms"]) > float(baseline["rms"]) * 2.5

    secondary = sum([rough, period_drop, onset_hard, intensity_spike])
    return bool(compression and secondary >= 1)


def leakage_like(seg: dict[str, Any]) -> bool:
    obs = seg.get("observations") or {}
    period = obs.get("periodicity_primary_db")
    h1h2 = obs.get("raw_h1_h2_proxy_db")
    tilt = obs.get("spectral_tilt_db_per_oct")
    fam = 0
    if period is not None and period <= 8:
        fam += 1
    if h1h2 is not None and h1h2 >= 7:
        fam += 1
    if tilt is not None and tilt <= -16:
        fam += 1
    src = ((seg.get("level2_proxies") or {}).get("glottal_source") or {})
    if src.get("valid") and (src.get("estimated_oq_proxy") or 0) >= 0.6:
        fam += 1
    return fam >= 2
