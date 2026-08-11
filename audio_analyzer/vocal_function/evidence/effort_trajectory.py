"""Effort trajectory evidence (v2.8).

Excess effort is judged from PRE → DURING → POST change, not absolute loudness.
CORE: intensity_trajectory, temporal_attack, recovery_persistence
SUPPORT: regularity_cost, spectral_residual, contact_shift
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from audio_analyzer.vocal_function.evidence.effort_contact import firmer_like, lighter_like


def rms_to_db(rms: Optional[float]) -> Optional[float]:
    if rms is None:
        return None
    r = float(rms)
    if r <= 0:
        return None
    return float(20.0 * np.log10(max(r, 1e-12)))


def extract_micro_intensity_db(
    chunk: np.ndarray,
    sr: int,
    *,
    win_sec: float = 0.08,
    hop_sec: float = 0.04,
) -> dict[str, Any]:
    """Short-window RMS dB trajectory inside one segment (debug / slope)."""
    if chunk is None or len(chunk) < max(8, int(0.05 * sr)):
        return {
            "series_db": [],
            "slope_db_per_sec": None,
            "peak_db": None,
            "median_db": None,
            "persistence_frac": None,
        }
    win = max(8, int(win_sec * sr))
    hop = max(4, int(hop_sec * sr))
    series = []
    for i in range(0, max(1, len(chunk) - win + 1), hop):
        w = chunk[i : i + win]
        rms = float(np.sqrt(np.mean(w**2) + 1e-12))
        series.append(rms_to_db(rms))
    clean = [float(x) for x in series if x is not None]
    if len(clean) < 3:
        return {
            "series_db": clean,
            "slope_db_per_sec": None,
            "peak_db": max(clean) if clean else None,
            "median_db": float(np.median(clean)) if clean else None,
            "persistence_frac": None,
        }
    # Robust slope via median-smoothed linear fit on time axis
    sm = np.asarray(clean, dtype=float)
    if len(sm) >= 5:
        sm = np.convolve(sm, np.ones(3) / 3.0, mode="same")
    t = np.arange(len(sm)) * hop_sec
    # Theil-Sen-ish: median of pairwise slopes
    slopes = []
    for i in range(len(sm)):
        for j in range(i + 1, len(sm)):
            dt = t[j] - t[i]
            if dt > 1e-6:
                slopes.append((sm[j] - sm[i]) / dt)
    slope = float(np.median(slopes)) if slopes else 0.0
    peak = float(np.max(sm))
    med = float(np.median(sm))
    persist = float(np.mean(sm >= (med + 0.5 * max(0.0, peak - med))))
    return {
        "series_db": [round(float(x), 2) for x in clean],
        "slope_db_per_sec": round(slope, 3),
        "peak_db": round(peak, 2),
        "median_db": round(med, 2),
        "persistence_frac": round(persist, 3),
    }


def _obs(seg: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not seg:
        return {}
    return seg.get("observations") or {}


def _intensity_db(seg: Optional[dict[str, Any]]) -> Optional[float]:
    if not seg:
        return None
    obs = _obs(seg)
    if obs.get("intensity_db") is not None:
        return float(obs["intensity_db"])
    return rms_to_db(obs.get("rms") if obs.get("rms") is not None else seg.get("rms"))


def _perturb(seg: Optional[dict[str, Any]]) -> Optional[float]:
    v = _obs(seg).get("f0_frame_period_perturbation_proxy_percent")
    return float(v) if v is not None else None


def _period(seg: Optional[dict[str, Any]]) -> Optional[float]:
    v = _obs(seg).get("periodicity_primary_db")
    return float(v) if v is not None else None


def _onset(seg: Optional[dict[str, Any]]) -> Optional[float]:
    v = _obs(seg).get("onset_slope_db_per_sec")
    return float(v) if v is not None else None


def _e24(seg: Optional[dict[str, Any]]) -> Optional[float]:
    v = _obs(seg).get("energy_2_4k")
    return float(v) if v is not None else None


def _contact_score(seg: Optional[dict[str, Any]], baseline: Optional[dict[str, Any]]) -> Optional[float]:
    if not seg:
        return None
    firm = firmer_like(seg, baseline)
    light = lighter_like(seg)
    if firm and not light:
        return 1.0
    if light and not firm:
        return 0.0
    if firm and light:
        return 0.5
    return None


def score_intensity_trajectory(
    pre: Optional[dict[str, Any]],
    during: dict[str, Any],
    post: Optional[dict[str, Any]] = None,
    baseline: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    pre_db = _intensity_db(pre)
    during_db = _intensity_db(during)
    post_db = _intensity_db(post)
    delta = None if pre_db is None or during_db is None else float(during_db - pre_db)
    base_db = rms_to_db((baseline or {}).get("rms")) if baseline else None
    vs_base = None if base_db is None or during_db is None else float(during_db - base_db)

    micro = (_obs(during).get("intensity_micro") or {}) if during else {}
    slope = micro.get("slope_db_per_sec")
    if slope is None and pre_db is not None and during_db is not None:
        dt = max(
            0.25,
            float(during.get("end_sec") or 0) - float(during.get("start_sec") or 0),
        )
        slope = delta / dt if delta is not None else None
    # Micro slope inside segment also counts as trajectory evidence
    micro_rising = slope is not None and float(slope) >= 4.0

    peak_overshoot = None
    if during_db is not None and pre_db is not None:
        peak_overshoot = max(0.0, float(during_db - pre_db))
        if micro.get("peak_db") is not None and pre_db is not None:
            peak_overshoot = max(peak_overshoot, float(micro["peak_db"]) - pre_db)

    abs_loud = during_db is not None and during_db >= -18.0
    rising_vs_pre = delta is not None and delta >= 3.5
    # Intra-segment micro slope alone is noisy; require steep slope + persistence
    micro_ok = bool(
        slope is not None
        and float(slope) >= 8.0
        and float(micro.get("persistence_frac") or 0) >= 0.55
    )
    n_base = int((baseline or {}).get("n_baseline_segments") or 0)
    rising_vs_base = bool(vs_base is not None and vs_base >= 9.0 and n_base >= 6)
    rising = bool(rising_vs_pre or micro_ok or rising_vs_base)

    status = "NONE"
    if abs_loud and not rising and (delta is None or abs(delta) < 2.0):
        status = "STATIC_LOUD"
    elif rising:
        status = "RISING"
    elif abs_loud:
        status = "STATIC_LOUD"

    positive = bool(rising)
    strength = 0.0
    if rising:
        strength = min(
            1.0,
            max(0.0, (float(delta or 0) / 8.0) + (float(slope or 0) / 20.0) + (float(vs_base or 0) / 12.0)),
        )

    return {
        "pre_db": None if pre_db is None else round(pre_db, 2),
        "during_db": None if during_db is None else round(during_db, 2),
        "post_db": None if post_db is None else round(post_db, 2),
        "baseline_db": None if base_db is None else round(base_db, 2),
        "delta_db": None if delta is None else round(delta, 2),
        "vs_baseline_db": None if vs_base is None else round(vs_base, 2),
        "slope_db_per_sec": None if slope is None else round(float(slope), 3),
        "peak_overshoot_db": None if peak_overshoot is None else round(float(peak_overshoot), 2),
        "persistence": micro.get("persistence_frac"),
        "status": status,
        "absolute_loud": bool(abs_loud),
        "positive": positive,
        "strength": round(strength, 3),
        "loudness_level": (
            "high" if abs_loud else ("mid" if during_db is not None and during_db >= -28 else "low")
        ),
    }


def score_temporal_attack_cost(
    pre: Optional[dict[str, Any]],
    during: dict[str, Any],
    *,
    intensity_rising: bool = False,
) -> dict[str, Any]:
    o_pre = _onset(pre)
    o_dur = _onset(during)
    delta = None if o_pre is None or o_dur is None else float(o_dur - o_pre)
    escalating = delta is not None and delta >= 25.0 and (o_dur or 0) >= 70.0
    absolute_hard = (o_dur or 0) >= 90.0
    # Absolute hard onset alone is weak; pairs with rising intensity trajectory
    positive = bool(
        escalating
        or (absolute_hard and intensity_rising)
        or (absolute_hard and (o_pre is None or (o_pre or 0) < 55))
    )
    strength = 0.0
    if escalating:
        strength = min(1.0, float(delta) / 80.0)
    elif positive and absolute_hard:
        strength = 0.5 if intensity_rising else 0.4
    return {
        "pre": o_pre,
        "during": o_dur,
        "delta": None if delta is None else round(delta, 2),
        "positive": positive,
        "strength": round(strength, 3),
    }


def score_regularity_cost_delta(
    pre: Optional[dict[str, Any]],
    during: dict[str, Any],
    *,
    intensity_rising: bool = False,
) -> dict[str, Any]:
    """Support family — delta vs pre, not absolute roughness presence."""
    p_pre, p_dur = _perturb(pre), _perturb(during)
    per_pre, per_dur = _period(pre), _period(during)
    pert_delta = None if p_pre is None or p_dur is None else float(p_dur - p_pre)
    per_delta = None if per_pre is None or per_dur is None else float(per_pre - per_dur)
    art = bool((_obs(during).get("f0_tracker_artifact") or {}).get("suspect"))
    positive = False
    strength = 0.0
    if art:
        return {
            "perturb_delta": pert_delta,
            "periodicity_drop_db": per_delta,
            "positive": False,
            "strength": 0.0,
            "reliability": 0.2,
            "reason": "tracker_artifact",
        }
    if pert_delta is not None and pert_delta >= 1.2 and (p_dur or 0) >= 2.0:
        positive = True
        strength = min(1.0, pert_delta / 4.0)
    if per_delta is not None and per_delta >= 3.0 and (per_dur or 99) <= 8.0:
        positive = True
        strength = max(strength, min(1.0, per_delta / 8.0))
    # First segment / flat neighbors: allow absolute irregularity only as support
    # when intensity is already rising (never alone).
    if (
        not positive
        and intensity_rising
        and (p_dur or 0) >= 2.5
        and (per_dur or 99) <= 6.0
    ):
        positive = True
        strength = 0.35
    return {
        "perturb_delta": None if pert_delta is None else round(pert_delta, 3),
        "periodicity_drop_db": None if per_delta is None else round(per_delta, 3),
        "positive": positive,
        "strength": round(strength, 3),
        "reliability": 0.7 if positive else 0.5,
        "reason": "delta" if positive else "stable_or_weak",
    }


def score_spectral_residual(
    pre: Optional[dict[str, Any]],
    during: dict[str, Any],
    *,
    intensity: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Support family — PRE→DURING spectral change; damp when static loud only."""
    e_pre, e_dur = _e24(pre), _e24(during)
    delta = None if e_pre is None or e_dur is None else float(e_dur - e_pre)
    # Loudness-conditioned soft gate: if intensity rising strongly, demand larger spectral jump
    rising = bool(intensity and intensity.get("positive"))
    need = 0.04 if rising else 0.06
    positive = delta is not None and delta >= need and (e_dur or 0) >= 0.12
    # Static loud alone should not count spectral residual strongly
    if intensity and intensity.get("status") == "STATIC_LOUD" and not rising:
        positive = False
    strength = 0.0
    if positive and delta is not None:
        strength = min(1.0, float(delta) / 0.15)
    return {
        "e24_delta": None if delta is None else round(delta, 4),
        "positive": positive,
        "strength": round(strength, 3),
        "reliability": 0.45 if positive else 0.4,
    }


def score_contact_shift(
    pre: Optional[dict[str, Any]],
    during: dict[str, Any],
    baseline: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Support only — firmness increase vs pre, not absolute firm."""
    c_pre = _contact_score(pre, baseline)
    c_dur = _contact_score(during, baseline)
    delta = None
    if c_pre is not None and c_dur is not None:
        delta = float(c_dur - c_pre)
    # Absolute firm without shift is weak/no support
    positive = delta is not None and delta >= 0.4
    strength = 0.0 if not positive else min(1.0, float(delta))
    return {
        "pre": c_pre,
        "during": c_dur,
        "delta": None if delta is None else round(delta, 3),
        "absolute_firm": bool(c_dur is not None and c_dur >= 0.65),
        "positive": positive,
        "strength": round(strength, 3),
    }


def score_recovery_cost(
    pre: Optional[dict[str, Any]],
    during: dict[str, Any],
    post: Optional[dict[str, Any]],
    *,
    during_loaded: bool = False,
) -> dict[str, Any]:
    """CORE family — slow return toward pre baseline after a loaded during."""
    if post is None or not during_loaded:
        return {
            "returned_to_baseline": None if post is None else True,
            "post_intensity_delta": None,
            "post_regularity_cost": None,
            "positive": False,
            "strength": 0.0,
            "fast_recovery": True if post is not None else None,
        }
    pre_db, post_db, dur_db = _intensity_db(pre), _intensity_db(post), _intensity_db(during)
    post_int_delta = None if pre_db is None or post_db is None else float(post_db - pre_db)
    p_pre, p_post = _perturb(pre), _perturb(post)
    post_reg = None if p_pre is None or p_post is None else float(p_post - p_pre)

    still_loud = post_int_delta is not None and post_int_delta >= 2.5 and (
        dur_db is None or post_db is None or float(post_db) >= float(dur_db) - 1.5
    )
    still_irreg = post_reg is not None and post_reg >= 1.2
    positive = bool(still_loud or still_irreg)
    fast = False
    if post_int_delta is not None and post_int_delta <= 1.0 and (post_reg is None or post_reg < 0.8):
        fast = True
        positive = False
    strength = 0.0
    if still_loud:
        strength = min(1.0, float(post_int_delta) / 6.0)
    if still_irreg:
        strength = max(strength, min(1.0, float(post_reg) / 3.0))
    return {
        "returned_to_baseline": bool(fast),
        "post_intensity_delta": None if post_int_delta is None else round(post_int_delta, 2),
        "post_regularity_cost": None if post_reg is None else round(post_reg, 3),
        "positive": positive,
        "strength": round(strength, 3),
        "fast_recovery": bool(fast),
    }


def compute_effort_event_context(
    during: dict[str, Any],
    *,
    pre: Optional[dict[str, Any]] = None,
    post: Optional[dict[str, Any]] = None,
    baseline: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    intensity = score_intensity_trajectory(pre, during, post, baseline=baseline)
    attack = score_temporal_attack_cost(
        pre, during, intensity_rising=bool(intensity.get("positive"))
    )
    during_loaded = bool(intensity.get("positive") or attack.get("positive"))
    recovery = score_recovery_cost(
        pre, during, post, during_loaded=during_loaded
    )
    regularity = score_regularity_cost_delta(
        pre, during, intensity_rising=bool(intensity.get("positive"))
    )
    spectral = score_spectral_residual(pre, during, intensity=intensity)
    contact = score_contact_shift(pre, during, baseline)

    core = {
        "intensity_trajectory": bool(intensity.get("positive")),
        "temporal_attack": bool(attack.get("positive")),
        "recovery_persistence": bool(recovery.get("positive")),
    }
    support = {
        "regularity_cost": bool(regularity.get("positive")),
        "spectral_residual": bool(spectral.get("positive")),
        "contact_shift": bool(contact.get("positive")),
    }
    # Stable firm (no shift): spectral residual is often loudness/brightness confound
    if contact.get("absolute_firm") and not contact.get("positive"):
        support["spectral_residual"] = False
        spectral = {
            **spectral,
            "positive": False,
            "strength": 0.0,
            "reason": "stable_firm_brightness_damped",
        }

    core_n = sum(1 for v in core.values() if v)
    support_n = sum(1 for v in support.values() if v)

    # Controlled crescendo / loud swell: intensity (+ maybe recovery) without other costs
    crescendo_only = bool(
        intensity.get("positive")
        and not attack.get("positive")
        and not support["regularity_cost"]
        and not support["spectral_residual"]
        and not support["contact_shift"]
    )
    controlled_crescendo = bool(crescendo_only and not recovery.get("positive"))
    persistent_crescendo_only = bool(crescendo_only and recovery.get("positive"))

    elevated = False
    if controlled_crescendo or persistent_crescendo_only:
        # Volume trajectory alone (even with slow return) ≠ excess effort
        elevated = False
        # Downgrade recovery from counting as a second core in this case
        if persistent_crescendo_only:
            core["recovery_persistence"] = False
            core_n = sum(1 for v in core.values() if v)
    elif core_n >= 2:
        elevated = True
    elif core_n >= 1 and support_n >= 1:
        elevated = True
    else:
        elevated = False

    # Score: acoustic excess-effort index (not muscle %)
    score = 0.0
    if intensity.get("positive"):
        score += 0.28 * float(intensity.get("strength") or 0.5)
    if attack.get("positive"):
        score += 0.24 * float(attack.get("strength") or 0.5)
    if core.get("recovery_persistence"):
        score += 0.22 * float(recovery.get("strength") or 0.5)
    if support.get("regularity_cost"):
        score += 0.12 * float(regularity.get("strength") or 0.5)
    if support.get("spectral_residual"):
        score += 0.08 * float(spectral.get("strength") or 0.5)
    if support.get("contact_shift"):
        score += 0.06 * float(contact.get("strength") or 0.5)
    if not elevated:
        score = min(score, 0.28)

    return {
        "intensity": intensity,
        "attack": attack,
        "regularity_cost": regularity,
        "spectral_cost": spectral,
        "contact_shift": contact,
        "recovery": recovery,
        "core_families": core,
        "support_families": support,
        "core_family_count": core_n,
        "support_family_count": support_n,
        "controlled_crescendo": controlled_crescendo or persistent_crescendo_only,
        "elevated": elevated,
        "final_score": round(min(1.0, float(score)), 3),
        "loudness_level": intensity.get("loudness_level"),
        "why": _why_blob(intensity, attack, recovery, regularity, spectral, contact, elevated),
    }


def _why_blob(intensity, attack, recovery, regularity, spectral, contact, elevated) -> dict[str, Any]:
    return {
        "absolute_loud": intensity.get("status"),
        "intensity_slope": intensity.get("slope_db_per_sec"),
        "intensity_delta_db": intensity.get("delta_db"),
        "attack_cost": "HIGH" if attack.get("positive") else "LOW",
        "regularity_delta": "HIGH" if regularity.get("positive") else "LOW",
        "spectral_residual": "HIGH" if spectral.get("positive") else "LOW",
        "recovery": (
            "FAST"
            if recovery.get("fast_recovery")
            else ("SLOW" if recovery.get("positive") else "OK")
        ),
        "contact": (
            "SHIFT"
            if contact.get("positive")
            else ("FIRM" if contact.get("absolute_firm") else "MID/LIGHT")
        ),
        "elevated": elevated,
    }


def effort_like_trajectory(
    during: dict[str, Any],
    *,
    pre: Optional[dict[str, Any]] = None,
    post: Optional[dict[str, Any]] = None,
    baseline: Optional[dict[str, Any]] = None,
) -> bool:
    return bool(
        compute_effort_event_context(
            during, pre=pre, post=post, baseline=baseline
        ).get("elevated")
    )


def effort_score_trajectory(
    during: dict[str, Any],
    *,
    pre: Optional[dict[str, Any]] = None,
    post: Optional[dict[str, Any]] = None,
    baseline: Optional[dict[str, Any]] = None,
) -> float:
    return float(
        compute_effort_event_context(
            during, pre=pre, post=post, baseline=baseline
        ).get("final_score")
        or 0.0
    )
