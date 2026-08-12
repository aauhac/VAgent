"""Sustain task dimension evidence (contact / breathiness / stability / resonance)."""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from audio_analyzer.diagnostic.evidence.schema import empty_evidence, make_evidence, metric_value, obs_map
from audio_analyzer.vocal_evidence.phonation_quality import (
    breathy_family_flags,
    breathy_negative_flags,
    classify_breathy_segment,
    classify_rough_segment,
)
from audio_analyzer.vocal_function.evidence.effort_contact import (
    contact_family_availability,
    contact_multi_family_fallback_ok,
    firmer_like,
    gif_usable,
    lighter_like,
)


def _seg_from_task(
    *,
    omap: dict[str, Any],
    phonation_summary: Optional[dict[str, Any]] = None,
    quality_ok: bool = True,
) -> dict[str, Any]:
    """Build a segment-like dict so Song evidence helpers can be reused."""
    observations = {
        "periodicity_primary_db": metric_value(omap, "cepstral_prominence_proxy_db"),
        "raw_h1_h2_proxy_db": metric_value(omap, "raw_h1_h2_proxy_db"),
        "spectral_tilt_db_per_oct": metric_value(omap, "spectral_tilt_db_per_oct"),
        "energy_2_4k": metric_value(omap, "energy_2_4k_ratio") or metric_value(omap, "energy_2_4k"),
        "onset_slope_db_per_sec": metric_value(omap, "onset_slope_db_per_sec"),
        "f0_frame_period_perturbation_proxy_percent": metric_value(
            omap, "f0_frame_period_perturbation_proxy_percent"
        )
        or metric_value(omap, "perturbation_proxy_percent"),
        "f0_dropout_ratio": metric_value(omap, "f0_dropout_ratio"),
        "rms": metric_value(omap, "rms"),
    }
    residual = (phonation_summary or {}).get("median_residual_std_cents")
    if residual is None:
        residual = metric_value(omap, "sustained_residual_f0_cents")
    if residual is not None:
        observations["sustained_residual_f0_cents"] = residual
    # Prefer observation metric for periodicity when present
    if observations.get("periodicity_primary_db") is None:
        observations["periodicity_primary_db"] = metric_value(omap, "hnr_ac_proxy_db")
    if observations.get("f0_frame_period_perturbation_proxy_percent") is None:
        observations["f0_frame_period_perturbation_proxy_percent"] = metric_value(
            omap, "f0_frame_period_perturbation_proxy_percent"
        )
    src = {
        "valid": False,
        "estimated_naq": metric_value(omap, "estimated_naq"),
        "estimated_oq_proxy": metric_value(omap, "estimated_oq_proxy"),
    }
    if src["estimated_naq"] is not None or src["estimated_oq_proxy"] is not None:
        src["valid"] = True
    return {
        "valid": quality_ok,
        "voiced_ratio": 0.7 if quality_ok else 0.1,
        "rms": observations.get("rms") or 0.05,
        "observations": observations,
        "vocal_evidence": {
            "vocal_specific": True,
            "vocal_dominance": 0.85,
            "vocal_confidence": 0.75,
            "vocal_energy": 1.0,
        },
        "level2_proxies": {
            "glottal_source": src,
            "gif_gate": {"valid": bool(src.get("valid"))},
        },
    }


def evidence_contact(seg: dict[str, Any], *, quality_valid: bool) -> dict[str, Any]:
    if not quality_valid:
        return empty_evidence("contact", reason="quality_fail", quality_valid=False)
    fam = contact_family_availability(seg)
    family_hits = {k: bool(v) for k, v in fam.items()}
    n_avail = sum(1 for v in fam.values() if v)
    # Hard rule: raw H1-H2 alone ≠ contact resolved
    only_h1h2 = fam.get("harmonic") and not fam.get("glottal_source") and not fam.get("spectral") and not fam.get("temporal")
    if only_h1h2 or n_avail < 1:
        return make_evidence(
            "contact",
            available=False,
            family_count=n_avail,
            evidence_families=family_hits,
            resolution_eligible=False,
            quality_valid=quality_valid,
            reason="h1h2_alone_or_no_families" if only_h1h2 else "no_contact_families",
            confidence_source="contact_family_availability",
        )

    firm = firmer_like(seg)
    light = lighter_like(seg)
    gif = gif_usable(seg)
    multi = contact_multi_family_fallback_ok(seg)

    if firm and (gif or multi):
        status = "FIRM_LEANING"
        estimate = 0.7
        conf = 0.78 if gif else 0.62
        eligible = True
        reason = "multi_family_firm" if multi or gif else "firm_weak"
    elif light and (gif or multi):
        status = "LIGHT_LEANING"
        estimate = 0.3
        conf = 0.76 if gif else 0.6
        eligible = True
        reason = "multi_family_light"
    elif multi:
        status = "MID"
        estimate = 0.5
        conf = 0.55
        eligible = True
        reason = "multi_family_mid_low_conf"
    else:
        return make_evidence(
            "contact",
            available=True,
            estimate=None,
            status="INSUFFICIENT",
            confidence_score=0.3,
            family_count=n_avail,
            evidence_families=family_hits,
            resolution_eligible=False,
            quality_valid=quality_valid,
            reason="insufficient_family_agreement",
            confidence_source="contact_family_availability",
        )

    return make_evidence(
        "contact",
        available=True,
        estimate=estimate,
        status=status,
        confidence_score=conf,
        family_count=n_avail,
        evidence_families=family_hits,
        evidence_mass=conf,
        resolution_eligible=eligible and conf >= 0.5,
        quality_valid=quality_valid,
        reason=reason,
        confidence_source="metric_family_aggregation",
    )


def evidence_breathiness(seg: dict[str, Any], *, quality_valid: bool) -> dict[str, Any]:
    if not quality_valid:
        return empty_evidence("breathiness", reason="quality_fail", quality_valid=False)
    fam = breathy_family_flags(seg)
    neg = breathy_negative_flags(seg)
    c = classify_breathy_segment(seg)
    n_pos = int(fam.get("n_positive") or 0)
    n_avail = len(fam.get("available_families") or [])
    # Hard rule: single weak periodicity ≠ resolve
    if n_pos <= 1 and not neg.get("strong") and c.get("verdict") != "NEGATIVE":
        return make_evidence(
            "breathiness",
            available=n_avail > 0,
            estimate=None,
            status="INSUFFICIENT",
            confidence_score=0.28 if n_avail else None,
            family_count=n_pos,
            evidence_families={
                "periodicity_noise": fam.get("periodicity_noise"),
                "harmonic_spectral": fam.get("harmonic_spectral"),
                "glottal_source": fam.get("glottal_source"),
            },
            resolution_eligible=False,
            quality_valid=quality_valid,
            reason="single_family_or_weak",
            confidence_source="breathy_family_flags",
        )

    if c.get("verdict") == "POSITIVE":
        return make_evidence(
            "breathiness",
            available=True,
            estimate=0.7,
            status="BREATHY",
            confidence_score=0.72,
            family_count=n_pos,
            evidence_families={
                "periodicity_noise": fam.get("periodicity_noise"),
                "harmonic_spectral": fam.get("harmonic_spectral"),
                "glottal_source": fam.get("glottal_source"),
            },
            evidence_mass=float(n_pos) / 3.0,
            resolution_eligible=True,
            quality_valid=quality_valid,
            reason=c.get("reason") or "multi_family_breathy",
            confidence_source="classify_breathy_segment",
        )
    if c.get("verdict") == "NEGATIVE":
        return make_evidence(
            "breathiness",
            available=True,
            estimate=0.15,
            status="LOW",
            confidence_score=0.7,
            family_count=int(neg.get("n_negative") or 0),
            evidence_families={"negative": neg.get("details") or []},
            evidence_mass=0.7,
            resolution_eligible=True,
            quality_valid=quality_valid,
            reason=c.get("reason") or "explicit_anti_breathy",
            confidence_source="breathy_negative_flags",
        )
    return make_evidence(
        "breathiness",
        available=True,
        estimate=None,
        status="INSUFFICIENT",
        confidence_score=0.35,
        family_count=n_pos,
        evidence_families=fam,
        resolution_eligible=False,
        quality_valid=quality_valid,
        reason=c.get("reason") or "insufficient",
        confidence_source="classify_breathy_segment",
    )


def evidence_stability(seg: dict[str, Any], *, quality_valid: bool) -> dict[str, Any]:
    """Steady/unstable axis — not identical to roughness irregularity."""
    if not quality_valid:
        return empty_evidence("stability", reason="quality_fail", quality_valid=False)
    obs = seg.get("observations") or {}
    residual = obs.get("sustained_residual_f0_cents")
    period = obs.get("periodicity_primary_db")
    perturb = obs.get("f0_frame_period_perturbation_proxy_percent")
    dropout = obs.get("f0_dropout_ratio")
    art = (obs.get("f0_tracker_artifact") or {}).get("suspect")
    families = {
        "residual_f0": residual is not None,
        "periodicity": period is not None,
        "perturbation": perturb is not None,
        "dropout": dropout is not None,
    }
    n = sum(1 for v in families.values() if v)
    if n < 1 or art:
        return make_evidence(
            "stability",
            available=False,
            family_count=n,
            evidence_families=families,
            resolution_eligible=False,
            quality_valid=quality_valid,
            reason="tracker_artifact" if art else "no_stability_metrics",
            confidence_source="sustain_stability",
        )

    unstable_hits = 0
    if residual is not None and float(residual) >= 35.0:
        unstable_hits += 1
    if perturb is not None and float(perturb) >= 2.5:
        unstable_hits += 1
    if period is not None and float(period) <= 7.0:
        unstable_hits += 1
    if dropout is not None and float(dropout) >= 0.25:
        unstable_hits += 1

    # Roughness-specific is informative but not required for stability axis
    rough = classify_rough_segment(seg)
    if unstable_hits >= 2:
        status = "UNSTABLE"
        estimate = 0.7
        conf = 0.7
        eligible = True
        reason = "multi_cue_unstable"
    elif unstable_hits == 0 and n >= 2:
        status = "STEADY"
        estimate = 0.2
        conf = 0.72
        eligible = True
        reason = "multi_cue_steady"
    else:
        status = "INSUFFICIENT"
        estimate = None
        conf = 0.35
        eligible = False
        reason = "weak_stability_cues"

    return make_evidence(
        "stability",
        available=True,
        estimate=estimate,
        status=status,
        confidence_score=conf,
        family_count=n,
        evidence_families={**families, "rough_verdict": rough.get("verdict")},
        evidence_mass=conf if eligible else 0.2,
        resolution_eligible=eligible,
        quality_valid=quality_valid,
        reason=reason,
        confidence_source="sustain_stability_cues",
        extra={"note": "stability_axis_not_roughness"},
    )


def evidence_resonance(seg: dict[str, Any], *, quality_valid: bool, vowel: str = "i") -> dict[str, Any]:
    if not quality_valid:
        return empty_evidence("resonance", reason="quality_fail", quality_valid=False)
    obs = seg.get("observations") or {}
    tilt = obs.get("spectral_tilt_db_per_oct")
    e24 = obs.get("energy_2_4k")
    families = {"spectral_tilt": tilt is not None, "energy_2_4k": e24 is not None}
    n = sum(1 for v in families.values() if v)
    if n < 1:
        return empty_evidence("resonance", reason="no_resonance_metrics", quality_valid=quality_valid)
    # Presence / relative brightness only — not formant physiology claim
    bright = (e24 is not None and float(e24) >= 0.12) or (tilt is not None and float(tilt) >= -12)
    dull = (e24 is not None and float(e24) <= 0.05) or (tilt is not None and float(tilt) <= -18)
    if bright or dull:
        status = "BRIGHT" if bright else "DARK"
        return make_evidence(
            "resonance",
            available=True,
            estimate=0.65 if bright else 0.35,
            status=status,
            confidence_score=0.58 if n >= 2 else 0.45,
            family_count=n,
            evidence_families=families,
            evidence_mass=0.55,
            resolution_eligible=n >= 2,
            quality_valid=quality_valid,
            reason="spectral_resonance_cues",
            confidence_source="spectral_families",
            extra={"vowel": vowel},
        )
    return make_evidence(
        "resonance",
        available=True,
        estimate=0.5,
        status="MID",
        confidence_score=0.4,
        family_count=n,
        evidence_families=families,
        resolution_eligible=False,
        quality_valid=quality_valid,
        reason="weak_resonance_cues",
        confidence_source="spectral_families",
        extra={"vowel": vowel},
    )


def evidence_effort_sustain(
    seg: dict[str, Any],
    *,
    quality_valid: bool,
    context: str = "baseline",
) -> dict[str, Any]:
    """Controlled-task effort cue — LOUD≠EFFORT, FIRM≠EFFORT.

    Status is severity/availability, not mere OBSERVED:
    INSUFFICIENT | LOW | INCREASED | HIGH
    Absolute severity is weak alone; HIGH_NOTE contrast uses baseline vs high.
    """
    if not quality_valid:
        return empty_evidence(
            "effort",
            reason="quality_or_compliance_failed",
            quality_valid=False,
        )
    obs = seg.get("observations") or {}
    rms = obs.get("rms")
    period = obs.get("periodicity_primary_db")
    tilt = obs.get("spectral_tilt_db_per_oct")
    firm = bool(firmer_like(seg))
    light = bool(lighter_like(seg))
    families = {
        "rms": rms is not None,
        "periodicity": period is not None,
        "spectral_tilt": tilt is not None,
        "contact_proxy": firm or light,
    }
    family_count = sum(1 for v in families.values() if v)
    if family_count < 2:
        return empty_evidence(
            "effort",
            reason="insufficient_effort_families",
            quality_valid=quality_valid,
        )

    # Relative proxy score in [0,1] — not absolute physiological effort.
    score = 0.35
    cues: list[str] = []
    if period is not None and float(period) <= 8.0:
        score += 0.22
        cues.append("low_periodicity")
    if firm:
        score += 0.18
        cues.append("firmer_contact_proxy")
    if tilt is not None and float(tilt) <= -8.0:
        score += 0.12
        cues.append("steep_tilt")
    if rms is not None and float(rms) >= 0.12:
        # intensity support only — never sole HIGH
        score += 0.08
        cues.append("elevated_rms_support")
    if light and not firm:
        score -= 0.15
        cues.append("lighter_contact_proxy")

    score = max(0.05, min(0.95, score))
    if score >= 0.72:
        status = "HIGH"
    elif score >= 0.55:
        status = "INCREASED"
    else:
        status = "LOW"

    return make_evidence(
        "effort",
        available=True,
        estimate=round(score, 3),
        status=status,
        confidence_score=0.5 + 0.1 * min(family_count, 3),
        family_count=family_count,
        evidence_families=families,
        evidence_mass=round(score, 3),
        resolution_eligible=True,
        quality_valid=quality_valid,
        reason=f"effort_{context}_{status.lower()}",
        confidence_source="multi_family_effort_proxy",
        extra={
            "rms": rms,
            "periodicity_primary_db": period,
            "spectral_tilt_db_per_oct": tilt,
            "effort_cues": cues,
            "context": context,
            # OBSERVED is availability alias — severity is status above
            "availability": "AVAILABLE",
        },
    )


def evidence_effort_high_sustain(
    seg: dict[str, Any],
    *,
    quality_valid: bool,
) -> dict[str, Any]:
    """High-note sustain effort — severity, not mere presence of RMS/periodicity."""
    return evidence_effort_sustain(seg, quality_valid=quality_valid, context="high_note")


def build_sustain_dimension_evidence(
    task_result: dict[str, Any],
    *,
    quality_valid: bool,
    compliance_ok: bool,
) -> dict[str, dict[str, Any]]:
    tid = task_result.get("task_id") or "sustain_a"
    omap = obs_map(task_result.get("observations"))
    seg = _seg_from_task(
        omap=omap,
        phonation_summary=task_result.get("phonation_summary"),
        quality_ok=quality_valid and compliance_ok,
    )
    usable = quality_valid and compliance_ok
    out = {
        "contact": evidence_contact(seg, quality_valid=usable),
        "breathiness": evidence_breathiness(seg, quality_valid=usable),
        "stability": evidence_stability(seg, quality_valid=usable),
    }
    if tid == "sustain_a":
        out["effort"] = evidence_effort_sustain(seg, quality_valid=usable, context="baseline")
        out["resonance"] = evidence_resonance(seg, quality_valid=usable, vowel="a")
    if tid == "sustain_i":
        out["resonance"] = evidence_resonance(seg, quality_valid=usable, vowel="i")
    if tid == "high_note_sustain_a":
        out["resonance"] = evidence_resonance(seg, quality_valid=usable, vowel="a")
        out["effort"] = evidence_effort_high_sustain(seg, quality_valid=usable)
        # Task completion alone insufficient: compliance gate already in usable
        if not usable:
            for ev in out.values():
                if isinstance(ev, dict):
                    ev["resolution_eligible"] = False
    return out
