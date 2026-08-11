"""Dynamic swell → effort evidence using Song v2.8/v2.9 trajectory semantics."""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from audio_analyzer.diagnostic.evidence.schema import empty_evidence, make_evidence
from audio_analyzer.features.phonation import extract_phonation_features
from audio_analyzer.features.pitch import extract_pitch_features
from audio_analyzer.vocal_function.evidence.effort_trajectory import (
    compute_effort_event_context,
    extract_micro_intensity_db,
    rms_to_db,
)


def _slice_thirds(y: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n = len(y)
    a, b = n // 3, 2 * n // 3
    return y[:a], y[a:b], y[b:]


def _seg_from_audio(
    chunk: np.ndarray,
    sr: int,
    *,
    start_sec: float,
    end_sec: float,
) -> dict[str, Any]:
    pitch = extract_pitch_features(chunk, sr)
    phon = extract_phonation_features(chunk, sr, pitch)
    rms = float(np.sqrt(np.mean(chunk.astype(float) ** 2) + 1e-12)) if len(chunk) else 0.0
    micro = extract_micro_intensity_db(chunk, sr)
    f0s = [f.get("f0_hz") for f in (pitch.get("frame_f0") or []) if f.get("f0_hz")]
    # crude perturbation proxy from consecutive f0 cents
    perturb = None
    if len(f0s) >= 4:
        cents = []
        for i in range(1, len(f0s)):
            cents.append(abs(1200 * np.log2((f0s[i] + 1e-10) / (f0s[i - 1] + 1e-10))))
        perturb = float(np.median(cents)) / 10.0  # soft scale into percent-like
    period = None
    # Use phonation residual as soft periodicity stand-in when CPP absent
    residual = phon.get("median_residual_std_cents")
    if residual is not None:
        period = max(2.0, 16.0 - float(residual) / 5.0)
    obs = {
        "rms": rms,
        "intensity_db": rms_to_db(rms),
        "onset_slope_db_per_sec": micro.get("slope_db_per_sec"),
        "periodicity_primary_db": period,
        "f0_frame_period_perturbation_proxy_percent": perturb,
        "energy_2_4k": None,
        "spectral_tilt_db_per_oct": None,
        "f0_tracker_artifact": {"suspect": False},
    }
    # spectral proxies if present on phonation
    if phon.get("energy_2_4k") is not None:
        obs["energy_2_4k"] = phon.get("energy_2_4k")
    if phon.get("spectral_tilt_db_per_oct") is not None:
        obs["spectral_tilt_db_per_oct"] = phon.get("spectral_tilt_db_per_oct")
    return {
        "start_sec": start_sec,
        "end_sec": end_sec,
        "valid": True,
        "voiced_ratio": float(pitch.get("voiced_ratio") or 0.5),
        "rms": rms,
        "observations": obs,
        "vocal_evidence": {
            "vocal_specific": True,
            "vocal_dominance": 0.85,
            "vocal_confidence": 0.7,
            "vocal_energy": 1.0,
        },
        "level2_proxies": {"glottal_source": {"valid": False}, "gif_gate": {"valid": False}},
        "_micro_intensity": micro,
    }


def build_dynamic_swell_dimension_evidence(
    y: np.ndarray,
    sr: int,
    *,
    quality_valid: bool,
    compliance_ok: bool,
) -> dict[str, dict[str, Any]]:
    if not quality_valid:
        return {
            "effort": empty_evidence("effort", reason="quality_fail", quality_valid=False),
            "dynamic_response": empty_evidence(
                "dynamic_response", reason="quality_fail", quality_valid=False
            ),
        }
    if not compliance_ok:
        # Flat / non-swell recording cannot resolve effort
        return {
            "effort": empty_evidence(
                "effort", reason="swell_compliance_fail", quality_valid=True
            ),
            "dynamic_response": empty_evidence(
                "dynamic_response", reason="swell_compliance_fail", quality_valid=True
            ),
        }

    pre_a, mid_a, post_a = _slice_thirds(y)
    n = len(y)
    pre = _seg_from_audio(pre_a, sr, start_sec=0.0, end_sec=(n / 3) / sr)
    mid = _seg_from_audio(mid_a, sr, start_sec=(n / 3) / sr, end_sec=(2 * n / 3) / sr)
    post = _seg_from_audio(post_a, sr, start_sec=(2 * n / 3) / sr, end_sec=n / sr)
    ctx = compute_effort_event_context(mid, pre=pre, post=post, baseline=None)

    inten = ctx.get("intensity") or {}
    attack = ctx.get("attack") or {}
    reg = ctx.get("regularity_cost") or {}
    spec = ctx.get("spectral_cost") or {}
    shift = ctx.get("contact_shift") or {}
    rec = ctx.get("recovery") or {}
    elevated = bool(ctx.get("elevated"))
    score = float(ctx.get("final_score") or 0.0)

    families = {
        "intensity_trajectory": bool(inten.get("positive")),
        "temporal_attack": bool(attack.get("positive")),
        "regularity_cost": bool(reg.get("positive")),
        "spectral_residual": bool(spec.get("positive")),
        "contact_shift": bool(shift.get("positive")),
        "recovery": bool(rec.get("positive")),
    }
    n_fam = sum(1 for v in families.values() if v)

    # Controlled crescendo defense: intensity rise alone ≠ high effort
    if not elevated:
        status = "LOW"
        estimate = max(0.05, score)
        conf = 0.72 if inten.get("status") in ("rising", "swell_like", "elevated", None) or True else 0.6
        # Valid measurement of LOW effort
        eligible = True
        reason = "controlled_loud_or_easy_swell"
        conf = 0.74 if (not families["regularity_cost"] and not families["temporal_attack"]) else 0.65
    else:
        status = "ELEVATED"
        estimate = max(0.45, score)
        conf = 0.7 if n_fam >= 2 else 0.55
        eligible = n_fam >= 1 and conf >= 0.5
        reason = "elevated_effort_trajectory"

    effort = make_evidence(
        "effort",
        available=True,
        estimate=round(float(estimate), 3),
        status=status,
        confidence_score=conf,
        family_count=max(1, n_fam),
        evidence_families=families,
        evidence_mass=score,
        resolution_eligible=eligible,
        quality_valid=True,
        reason=reason,
        confidence_source="effort_trajectory_v28",
        extra={
            "trajectory": {
                "intensity": inten,
                "attack": attack,
                "regularity_cost": reg,
                "spectral_residual": spec,
                "contact_shift": shift,
                "recovery": rec,
                "elevated": elevated,
                "final_score": score,
            }
        },
    )

    # Dynamic response: whether intensity actually changed as instructed
    dyn_ok = bool(inten.get("delta_db") is not None and abs(float(inten.get("delta_db") or 0)) >= 2.5)
    dynamic = make_evidence(
        "dynamic_response",
        available=True,
        estimate=1.0 if dyn_ok else 0.2,
        status="RESPONSIVE" if dyn_ok else "FLAT",
        confidence_score=0.7 if dyn_ok else 0.45,
        family_count=1,
        evidence_families={"intensity_delta": dyn_ok},
        evidence_mass=0.7 if dyn_ok else 0.2,
        resolution_eligible=dyn_ok,
        quality_valid=True,
        reason="intensity_trajectory_present" if dyn_ok else "weak_dynamic_change",
        confidence_source="effort_trajectory_v28",
    )
    return {"effort": effort, "dynamic_response": dynamic}
