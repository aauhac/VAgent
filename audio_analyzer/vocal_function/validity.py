"""Dimension-specific segment validity (v2.3 / v2.7).

Global segment.valid is no longer the sole gate for all dimensions.
Contact and effort use their own family-aware validity (GIF is not absolute).
"""

from __future__ import annotations

from typing import Any

from audio_analyzer.vocal_evidence.phonation_quality import vocal_presence_ok
from audio_analyzer.vocal_function.evidence.effort_contact import (
    contact_family_availability,
    contact_multi_family_fallback_ok,
    gif_usable,
)


def _cap(label: str) -> str:
    return label if label in ("high", "medium", "low") else "low"


def build_validity_by_dimension(seg: dict[str, Any]) -> dict[str, Any]:
    """
    Attach per-dimension validity.

    Breathiness / roughness / effort must NOT require GIF or strong F0 tracking.
    Contact may use GIF (strong) OR multi-family harmonic+spectral(+temporal) fallback.
    """
    obs = seg.get("observations") or {}
    ve = seg.get("vocal_evidence") or {}
    src = ((seg.get("level2_proxies") or {}).get("glottal_source") or {})
    presence = vocal_presence_ok(seg)
    period = obs.get("periodicity_primary_db")
    f0 = obs.get("f0_hz")
    rms = obs.get("rms")
    if rms is None:
        rms = seg.get("rms")
    # Missing rms OK when proxies exist; near-zero rms rejects
    energy_ok = not (rms is not None and float(rms) <= 1e-5)
    duration_ok = True  # segment builder already enforces window length

    # --- breathiness: vocal presence + any computable family ---
    breathy_families = []
    if period is not None:
        breathy_families.append("periodicity_noise")
    if obs.get("raw_h1_h2_proxy_db") is not None or obs.get("spectral_tilt_db_per_oct") is not None:
        breathy_families.append("harmonic_spectral")
    if src.get("valid"):
        breathy_families.append("glottal_source")
    breathy_valid = bool(presence and energy_ok and duration_ok and breathy_families)
    breathy_missing = [
        x
        for x in ("periodicity_noise", "harmonic_spectral", "glottal_source")
        if x not in breathy_families
    ]
    breathiness = {
        "valid": breathy_valid,
        "coverage_reason": []
        if breathy_valid
        else (
            ["no_vocal_presence"]
            if not presence
            else (["no_energy"] if not energy_ok else ["no_computable_families"])
        ),
        "available_families": breathy_families,
        "missing_families": breathy_missing,
        "confidence_cap": _cap(
            "medium" if len(breathy_families) >= 2 else ("low" if breathy_families else "low")
        ),
        "gif_required": False,
    }

    # --- roughness: presence + ability to measure irregularity OR periodicity ---
    rough_ok = presence and energy_ok and (
        period is not None
        or obs.get("f0_frame_period_perturbation_proxy_percent") is not None
        or obs.get("f0_dropout_ratio") is not None
    )
    roughness = {
        "valid": rough_ok,
        "coverage_reason": [] if rough_ok else ["insufficient_irregularity_metrics"],
        "available_families": [
            k
            for k, cond in (
                ("periodicity_loss", period is not None),
                ("irregularity", obs.get("f0_frame_period_perturbation_proxy_percent") is not None),
                ("dropout", obs.get("f0_dropout_ratio") is not None),
            )
            if cond
        ],
        "missing_families": [],
        "confidence_cap": "medium" if rough_ok else "low",
        "gif_required": False,
    }

    # --- contact: GIF strong OR multi-family fallback (not absolute GIF gate) ---
    gif_ok = gif_usable(seg)
    fam_avail = contact_family_availability(seg)
    contact_families = [k for k, ok in fam_avail.items() if ok]
    fallback_ok = contact_multi_family_fallback_ok(seg)
    # Rough/pressed phonation may weaken F0; do not require vocal_specific+F0 for contact recall
    contact_valid = bool(presence and energy_ok and (gif_ok or fallback_ok))
    if contact_valid and gif_ok:
        contact_cap = "medium"
    elif contact_valid and fallback_ok:
        contact_cap = "low"  # availability ↑ without confidence inflation
    else:
        contact_cap = "low"
    missing_contact = [
        k for k in ("glottal_source", "harmonic", "spectral", "temporal") if k not in contact_families
    ]
    glottal_contact = {
        "valid": contact_valid,
        "coverage_reason": []
        if contact_valid
        else (
            ["no_vocal_presence"]
            if not presence
            else (
                ["no_energy"]
                if not energy_ok
                else (
                    ["gif_invalid_and_insufficient_fallback"]
                    if not gif_ok
                    else ["insufficient_families"]
                )
            )
        ),
        "available_families": contact_families,
        "missing_families": missing_contact,
        "confidence_cap": _cap(contact_cap),
        "gif_required": False,
        "gif_supported": gif_ok,
        "fallback_supported": bool(fallback_ok and not gif_ok),
    }

    # --- effort: presence + energy + any effort-related acoustic family ---
    # Strong F0 / GIF NOT required — rough/pressed must remain measurable.
    effort_families = []
    if obs.get("rms") is not None or rms is not None:
        effort_families.append("intensity")
    if obs.get("onset_slope_db_per_sec") is not None:
        effort_families.append("temporal")
    if (
        period is not None
        or obs.get("f0_frame_period_perturbation_proxy_percent") is not None
        or obs.get("f0_dropout_ratio") is not None
    ):
        effort_families.append("regularity")
    if obs.get("energy_2_4k") is not None or obs.get("spectral_tilt_db_per_oct") is not None:
        effort_families.append("spectral")
    if gif_ok or fam_avail.get("glottal_source") or fam_avail.get("harmonic"):
        effort_families.append("contact")  # optional supporting family availability
    # recovery is fusion/episode-level; mark as conceptually available
    effort_families.append("recovery")
    effort_valid = bool(
        presence and energy_ok and len([f for f in effort_families if f != "recovery"]) >= 1
    )
    effort = {
        "valid": effort_valid,
        "coverage_reason": []
        if effort_valid
        else (
            ["no_vocal_presence"]
            if not presence
            else (["no_energy"] if not energy_ok else ["no_effort_families"])
        ),
        "available_families": effort_families,
        "missing_families": [
            x
            for x in ("intensity", "temporal", "regularity", "spectral", "contact", "recovery")
            if x not in effort_families
        ],
        "confidence_cap": _cap("medium" if effort_valid and len(effort_families) >= 3 else "low"),
        "gif_required": False,
    }

    register = {
        "valid": bool(
            presence
            and ve.get("vocal_specific", False)
            and f0 is not None
            and (ve.get("f0_confidence") or 0) >= 0.35
        ),
        "coverage_reason": []
        if (f0 and ve.get("vocal_specific"))
        else ["needs_vocal_specific_f0"],
        "available_families": [],
        "missing_families": [],
        "confidence_cap": "medium" if ve.get("vocal_specific") else "low",
        "gif_required": False,
    }

    resonance = {
        "valid": bool(
            presence
            and energy_ok
            and (obs.get("energy_2_4k") is not None or obs.get("spectral_centroid_hz") is not None)
        ),
        "coverage_reason": [],
        "available_families": [],
        "missing_families": [],
        "confidence_cap": "medium" if presence else "low",
        "gif_required": False,
    }

    onset = {
        "valid": bool(presence and obs.get("onset_slope_db_per_sec") is not None),
        "coverage_reason": [],
        "available_families": [],
        "missing_families": [],
        "confidence_cap": "medium" if presence else "low",
        "gif_required": False,
    }

    vibrato = {
        "valid": bool(presence and f0 is not None),
        "coverage_reason": [],
        "available_families": [],
        "missing_families": [],
        "confidence_cap": "low",
        "gif_required": False,
    }

    return {
        "breathiness": breathiness,
        "roughness": roughness,
        "glottal_contact": glottal_contact,
        "effort": effort,
        "register": register,
        "resonance": resonance,
        "onset": onset,
        "vibrato": vibrato,
    }


def dim_valid(seg: dict[str, Any], dimension: str) -> bool:
    vbd = seg.get("validity_by_dimension") or {}
    d = vbd.get(dimension) or {}
    if d:
        return bool(d.get("valid"))
    # Lazy build for synthetic/test segments
    if dimension in ("breathiness", "roughness", "glottal_contact", "effort"):
        built = build_validity_by_dimension(seg).get(dimension) or {}
        return bool(built.get("valid"))
    return bool(seg.get("valid"))
