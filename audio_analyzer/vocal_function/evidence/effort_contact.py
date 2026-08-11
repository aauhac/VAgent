"""Contact / effort evidence families (v2.7).

CONTACT continuum: light ↔ firm (acoustic proxies).
EFFORT continuum: easy ↔ excess-effort-like (independent of contact).

Contact firmness alone must never imply high effort.
"""

from __future__ import annotations

from typing import Any, Optional

from audio_analyzer.vocal_function import config as cfg


def _obs(seg: dict[str, Any]) -> dict[str, Any]:
    return seg.get("observations") or {}


def _src(seg: dict[str, Any]) -> dict[str, Any]:
    return ((seg.get("level2_proxies") or {}).get("glottal_source") or {})


def _gate(seg: dict[str, Any]) -> dict[str, Any]:
    return ((seg.get("level2_proxies") or {}).get("gif_gate") or {})


def gif_usable(seg: dict[str, Any]) -> bool:
    src = _src(seg)
    gate = _gate(seg)
    return bool(src.get("valid") or gate.get("valid"))


def contact_family_availability(seg: dict[str, Any]) -> dict[str, bool]:
    """Which contact evidence families have usable raw metrics (not directional)."""
    obs = _obs(seg)
    src = _src(seg)
    gif = gif_usable(seg)
    flow = bool(gif and (src.get("estimated_naq") is not None or src.get("estimated_oq_proxy") is not None))
    harmonic = obs.get("raw_h1_h2_proxy_db") is not None
    spectral = obs.get("energy_2_4k") is not None or obs.get("spectral_tilt_db_per_oct") is not None
    temporal = obs.get("onset_slope_db_per_sec") is not None
    return {
        "glottal_source": flow,
        "harmonic": harmonic,
        "spectral": spectral,
        "temporal": temporal,
    }


def contact_multi_family_fallback_ok(seg: dict[str, Any]) -> bool:
    """GIF optional: need ≥2 non-source directional families with metrics present."""
    fam = contact_family_availability(seg)
    supporting = [k for k in ("harmonic", "spectral", "temporal") if fam.get(k)]
    return len(supporting) >= 2


def lighter_like(seg: dict[str, Any]) -> bool:
    obs = _obs(seg)
    src = _src(seg)
    hits = 0
    if gif_usable(seg) and src.get("estimated_naq") is not None:
        if float(src["estimated_naq"]) >= cfg.NAQ_LIGHTER_HINT:
            hits += 1
        if (src.get("estimated_oq_proxy") or 0) >= 0.55:
            hits += 1
    h1h2 = obs.get("raw_h1_h2_proxy_db")
    if h1h2 is not None and float(h1h2) >= cfg.H1H2_LIGHTER_DB:
        hits += 1
    tilt = obs.get("spectral_tilt_db_per_oct")
    if tilt is not None and float(tilt) <= -14:
        hits += 1
    return hits >= 2


def firmer_like(
    seg: dict[str, Any],
    baseline: dict[str, Any] | None = None,
) -> bool:
    """
    Firm-like requires ≥2 independent families.

    NAQ + relative MFDR share glottal_flow (no double vote).
    Spectral (2–4k) supports only when flow or harmonic already present.
    """
    obs = _obs(seg)
    src = _src(seg)
    families: set[str] = set()

    naq = src.get("estimated_naq") if gif_usable(seg) else None
    if naq is not None and float(naq) <= cfg.NAQ_FIRMER_HINT:
        families.add("glottal_flow")

    mfdr_n = src.get("estimated_mfdr_norm_proxy") if gif_usable(seg) else None
    base_mfdr = (baseline or {}).get("mfdr_norm")
    if (
        mfdr_n is not None
        and base_mfdr is not None
        and float(base_mfdr) > 0
        and float(mfdr_n) >= float(base_mfdr) * 1.35
    ):
        families.add("glottal_flow")

    h1h2 = obs.get("raw_h1_h2_proxy_db")
    if h1h2 is not None and float(h1h2) <= cfg.H1H2_FIRMER_DB:
        families.add("harmonic")

    e24 = obs.get("energy_2_4k")
    if e24 is not None and float(e24) >= 0.15 and families.intersection({"glottal_flow", "harmonic"}):
        families.add("spectral")

    # Temporal support only as third family (onset harden) — never alone
    onset = obs.get("onset_slope_db_per_sec")
    if (
        onset is not None
        and float(onset) >= 80
        and families.intersection({"glottal_flow", "harmonic", "spectral"})
    ):
        families.add("temporal")

    return len(families) >= 2


def contact_direction_score(
    seg: dict[str, Any],
    baseline: dict[str, Any] | None = None,
) -> Optional[float]:
    """
    Segment contact evidence score: 0.0 light … 1.0 firm.
    None when directional evidence is insufficient (no fake midpoint).
    """
    firm = firmer_like(seg, baseline)
    light = lighter_like(seg)
    if firm and not light:
        return 1.0
    if light and not firm:
        return 0.0
    if firm and light:
        return 0.5

    # Partial directional lean (single strong cue) — not enough for continuum vote
    return None


def contact_evidence_packet(
    seg: dict[str, Any],
    baseline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    obs = _obs(seg)
    src = _src(seg)
    gif = gif_usable(seg)
    avail = contact_family_availability(seg)

    flow_dir = None
    flow_str = 0.0
    if gif and src.get("estimated_naq") is not None:
        naq = float(src["estimated_naq"])
        if naq <= cfg.NAQ_FIRMER_HINT:
            flow_dir, flow_str = "firm", min(1.0, (cfg.NAQ_FIRMER_HINT - naq) / max(cfg.NAQ_FIRMER_HINT, 1e-6))
        elif naq >= cfg.NAQ_LIGHTER_HINT:
            flow_dir, flow_str = "light", min(1.0, (naq - cfg.NAQ_LIGHTER_HINT) / 0.2)

    harm_dir = None
    harm_str = 0.0
    h1h2 = obs.get("raw_h1_h2_proxy_db")
    if h1h2 is not None:
        h = float(h1h2)
        if h <= cfg.H1H2_FIRMER_DB:
            harm_dir, harm_str = "firm", min(1.0, (cfg.H1H2_FIRMER_DB - h + 2) / 4)
        elif h >= cfg.H1H2_LIGHTER_DB:
            harm_dir, harm_str = "light", min(1.0, (h - cfg.H1H2_LIGHTER_DB + 2) / 8)

    spec_dir = None
    spec_str = 0.0
    e24 = obs.get("energy_2_4k")
    tilt = obs.get("spectral_tilt_db_per_oct")
    if e24 is not None and float(e24) >= 0.15:
        spec_dir, spec_str = "firm", min(1.0, float(e24) / 0.3)
    elif tilt is not None and float(tilt) <= -14:
        spec_dir, spec_str = "light", min(1.0, abs(float(tilt) + 10) / 12)

    temp_dir = None
    temp_str = 0.0
    onset = obs.get("onset_slope_db_per_sec")
    if onset is not None and float(onset) >= 80:
        temp_dir, temp_str = "firm", min(1.0, float(onset) / 120.0)

    score = contact_direction_score(seg, baseline)
    directional = [d for d in (flow_dir, harm_dir, spec_dir, temp_dir) if d]
    family_count = sum(1 for v in avail.values() if v)
    evidence_mass = round(
        (flow_str if flow_dir else 0)
        + (harm_str if harm_dir else 0)
        + (spec_str if spec_dir else 0)
        + 0.5 * (temp_str if temp_dir else 0),
        3,
    )
    agreement = None
    if len(directional) >= 2:
        agreement = len(set(directional)) == 1

    return {
        "flow": {
            "available": avail["glottal_source"],
            "direction": flow_dir,
            "strength": round(flow_str, 3),
            "reliability": 0.75 if gif else 0.0,
        },
        "harmonic": {
            "available": avail["harmonic"],
            "direction": harm_dir,
            "strength": round(harm_str, 3),
            "reliability": 0.65 if avail["harmonic"] else 0.0,
        },
        "spectral": {
            "available": avail["spectral"],
            "direction": spec_dir,
            "strength": round(spec_str, 3),
            "reliability": 0.45 if avail["spectral"] else 0.0,
        },
        "temporal": {
            "available": avail["temporal"],
            "direction": temp_dir,
            "strength": round(temp_str, 3),
            "reliability": 0.4 if avail["temporal"] else 0.0,
        },
        "final_score": score,
        "evidence_mass": evidence_mass,
        "family_count": family_count,
        "family_agreement": agreement,
        "gif_supported": gif,
        "fallback_supported": (not gif) and contact_multi_family_fallback_ok(seg) and score is not None,
    }


def _intensity_spike(seg: dict[str, Any], baseline: dict[str, Any] | None) -> bool:
    obs = _obs(seg)
    if not baseline or baseline.get("rms") is None or obs.get("rms") is None:
        return False
    base = float(baseline["rms"])
    if base <= 0:
        return False
    return float(obs["rms"]) > base * 2.5


def _spectral_compression_like(seg: dict[str, Any], baseline: dict[str, Any] | None) -> bool:
    """Relative upper-band concentration — not absolute brightness."""
    obs = _obs(seg)
    e24 = obs.get("energy_2_4k")
    if e24 is None:
        return False
    e24 = float(e24)
    base_e = (baseline or {}).get("energy_24k")
    if base_e is not None and float(base_e) > 0:
        return e24 >= max(0.15, float(base_e) * 1.45)
    # Without baseline: require strong absolute band energy (harder path)
    return e24 >= 0.22


def effort_family_hits(
    seg: dict[str, Any],
    baseline: dict[str, Any] | None = None,
    *,
    recovery_slow: bool = False,
) -> dict[str, bool]:
    """Legacy segment-local family flags (absolute). Prefer trajectory context in fusion."""
    obs = _obs(seg)
    rough = (obs.get("f0_frame_period_perturbation_proxy_percent") or 0) >= 2.5
    period_drop = (obs.get("periodicity_primary_db") or 99) <= 6.0
    onset_hard = (obs.get("onset_slope_db_per_sec") or 0) >= 80
    return {
        "intensity": _intensity_spike(seg, baseline),
        "temporal": bool(onset_hard),
        "regularity": bool(rough or period_drop),
        "spectral": _spectral_compression_like(seg, baseline),
        "recovery": bool(recovery_slow),
        "contact": firmer_like(seg, baseline),
    }


def independent_effort_family_count(
    hits: dict[str, bool],
) -> int:
    """Families that do not require firm contact."""
    return sum(
        1
        for k in ("intensity", "temporal", "regularity", "spectral", "recovery")
        if hits.get(k)
    )


def effort_secondary_signs(
    seg: dict[str, Any],
    baseline: dict[str, Any] | None = None,
) -> bool:
    """Any non-contact effort family hit (observation layer)."""
    hits = effort_family_hits(seg, baseline)
    return independent_effort_family_count(hits) >= 1


def effort_like(
    seg: dict[str, Any],
    baseline: dict[str, Any] | None = None,
    *,
    recovery_slow: bool = False,
    pre: dict[str, Any] | None = None,
    post: dict[str, Any] | None = None,
) -> bool:
    """
    Excess effort-like acoustic pattern (v2.8).

    Prefer PRE/DURING/POST trajectory when neighbors are provided.
    Support-only (regularity + spectral) cannot elevate.
    Absolute loud / firm / bright / rough / high-F0 alone cannot elevate.
    """
    from audio_analyzer.vocal_function.evidence.effort_trajectory import (
        effort_like_trajectory,
    )

    if pre is not None or post is not None:
        return effort_like_trajectory(seg, pre=pre, post=post, baseline=baseline)

    hits = effort_family_hits(seg, baseline, recovery_slow=recovery_slow)
    core_n = sum(1 for k in ("intensity", "temporal", "recovery") if hits.get(k))
    support_n = sum(1 for k in ("regularity", "spectral") if hits.get(k))
    # Absolute firm contact is NOT a core/support substitute for contact_shift
    if core_n >= 2:
        return True
    if core_n >= 1 and support_n >= 1:
        return True
    return False


def effort_score(
    seg: dict[str, Any],
    baseline: dict[str, Any] | None = None,
    *,
    recovery_slow: bool = False,
    pre: dict[str, Any] | None = None,
    post: dict[str, Any] | None = None,
) -> float:
    """Acoustic effort evidence index 0..1 — not muscle tension %."""
    from audio_analyzer.vocal_function.evidence.effort_trajectory import (
        effort_score_trajectory,
    )

    if pre is not None or post is not None:
        return effort_score_trajectory(seg, pre=pre, post=post, baseline=baseline)

    hits = effort_family_hits(seg, baseline, recovery_slow=recovery_slow)
    core_n = sum(1 for k in ("intensity", "temporal", "recovery") if hits.get(k))
    support_n = sum(1 for k in ("regularity", "spectral") if hits.get(k))
    score = 0.3 * core_n + 0.12 * support_n
    if not effort_like(seg, baseline, recovery_slow=recovery_slow):
        score = min(score, 0.28)
    return float(min(1.0, round(score, 3)))


def effort_evidence_packet(
    seg: dict[str, Any],
    baseline: dict[str, Any] | None = None,
    *,
    recovery_slow: bool = False,
    pre: dict[str, Any] | None = None,
    post: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from audio_analyzer.vocal_function.evidence.effort_trajectory import (
        compute_effort_event_context,
    )

    if pre is not None or post is not None:
        ctx = compute_effort_event_context(seg, pre=pre, post=post, baseline=baseline)
        return {
            "families": {
                **{k: v for k, v in (ctx.get("core_families") or {}).items()},
                **{k: v for k, v in (ctx.get("support_families") or {}).items()},
            },
            "family_count": int(ctx.get("core_family_count") or 0)
            + int(ctx.get("support_family_count") or 0),
            "independent_family_count": int(ctx.get("core_family_count") or 0),
            "effort_like": bool(ctx.get("elevated")),
            "effort_score": float(ctx.get("final_score") or 0),
            "trajectory": ctx,
            "contact_optional_support": bool(
                (ctx.get("support_families") or {}).get("contact_shift")
            ),
        }

    hits = effort_family_hits(seg, baseline, recovery_slow=recovery_slow)
    n_ind = independent_effort_family_count(hits)
    return {
        "families": hits,
        "family_count": n_ind + (1 if hits.get("contact") else 0),
        "independent_family_count": n_ind,
        "effort_like": effort_like(seg, baseline, recovery_slow=recovery_slow),
        "effort_score": effort_score(seg, baseline, recovery_slow=recovery_slow),
        "contact_optional_support": bool(hits.get("contact")),
    }
