"""Dimension-specific segment validity (v2.3).

Global segment.valid is no longer the sole gate for all dimensions.
"""

from __future__ import annotations

from typing import Any

from audio_analyzer.vocal_evidence.phonation_quality import vocal_presence_ok


def _cap(label: str) -> str:
    return label if label in ("high", "medium", "low") else "low"


def build_validity_by_dimension(seg: dict[str, Any]) -> dict[str, Any]:
    """
    Attach per-dimension validity.
    Breathiness must NOT require GIF validity or strong F0 tracking.
    Contact / glottal source claims still require stronger gates.
    """
    obs = seg.get("observations") or {}
    ve = seg.get("vocal_evidence") or {}
    src = ((seg.get("level2_proxies") or {}).get("glottal_source") or {})
    gate = ((seg.get("level2_proxies") or {}).get("gif_gate") or {})
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

    # --- contact / glottal: needs stronger evidence ---
    gif_ok = bool(src.get("valid") or gate.get("valid"))
    contact_valid = bool(
        presence
        and energy_ok
        and (ve.get("vocal_specific", False) or (f0 and period is not None))
        and gif_ok
    )
    glottal_contact = {
        "valid": contact_valid,
        "coverage_reason": []
        if contact_valid
        else (
            ["gif_invalid"]
            if not gif_ok
            else (["weak_vocal_evidence"] if not ve.get("vocal_specific") else ["insufficient"])
        ),
        "available_families": ["glottal_source"] if gif_ok else [],
        "missing_families": [] if gif_ok else ["glottal_source"],
        "confidence_cap": "medium" if contact_valid else "low",
        "gif_required": True,
    }

    effort = {
        "valid": bool(presence and energy_ok and (period is not None or gif_ok)),
        "coverage_reason": [],
        "available_families": [],
        "missing_families": [],
        "confidence_cap": "medium" if presence else "low",
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
        "valid": bool(presence and energy_ok and (obs.get("energy_2_4k") is not None or obs.get("spectral_centroid_hz") is not None)),
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
    # Fallback: legacy global valid for non-breathiness dims
    if dimension == "breathiness":
        return vocal_presence_ok(seg)
    return bool(seg.get("valid"))
