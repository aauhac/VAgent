"""Head–Chest continuous axis with signed family votes (v1.2).

signed_vote: -1 chest … +1 head
UNKNOWN / low mass → index None (never 0.5)
CONTACT never decides alone.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from . import config as cfg

_SOURCE_FAMILIES = frozenset({"SOURCE_FLOW", "HARMONIC_SOURCE"})


def _obs(seg: dict[str, Any]) -> dict[str, Any]:
    return seg.get("observations") or {}


def _src(seg: dict[str, Any]) -> dict[str, Any]:
    return ((seg.get("level2_proxies") or {}).get("glottal_source") or {})


def _f0(seg: dict[str, Any]) -> Optional[float]:
    v = _obs(seg).get("f0_hz")
    return float(v) if v is not None and float(v) > 0 else None


def _rms(seg: dict[str, Any]) -> Optional[float]:
    v = _obs(seg).get("rms")
    if v is None:
        v = seg.get("rms")
    return float(v) if v is not None else None


def pitch_band(f0: Optional[float]) -> str:
    if f0 is None:
        return "unknown"
    if f0 < cfg.F0_LOW_MAX:
        return "low"
    if f0 < cfg.F0_MID_MAX:
        return "mid"
    return "high"


def _collect_band_vals(
    segments: list[dict[str, Any]], band: str, key: str
) -> list[float]:
    vals = []
    for s in segments:
        if pitch_band(_f0(s)) != band:
            continue
        if key.startswith("src."):
            src = _src(s)
            if not src.get("valid"):
                continue
            v = src.get(key[4:])
        else:
            v = _obs(s).get(key)
        if v is not None:
            vals.append(float(v))
    return vals


def baseline_eligible(vals: list[float]) -> bool:
    if len(vals) < cfg.MIN_BASELINE_SAMPLES:
        return False
    med = abs(float(np.median(vals))) + 1e-9
    std = float(np.std(vals))
    return (std / med) >= cfg.MIN_BASELINE_STD_FRAC and std > 1e-9


def _band_or_global_baseline(
    segments: list[dict[str, Any]],
    band: str,
    key: str,
    global_baseline: dict[str, Any],
    gkey: str,
) -> tuple[Optional[float], str]:
    """Returns (baseline, mode) where mode is relative|absolute|none."""
    vals = _collect_band_vals(segments, band, key)
    if baseline_eligible(vals):
        return float(np.median(vals)), "relative"
    g = global_baseline.get(gkey)
    if g is not None:
        # Song-level baseline only if globally varied enough when enough segs
        all_vals = _collect_band_vals(segments, band, key) if False else None
        return float(g), "relative_global"
    return None, "none"


def _family_packet(
    *,
    status: str,
    signed_vote: float,
    vote_strength: float,
    reliability: float,
    chest: float,
    head: float,
    raw_value: Any = None,
    normalized_value: Any = None,
    evidence: Optional[list[str]] = None,
    applied: bool = True,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    out = {
        "status": status,
        "signed_vote": round(float(signed_vote), 3),
        "vote_strength": round(float(vote_strength), 3),
        "reliability": round(float(reliability), 3),
        "chest": round(float(chest), 3),
        "head": round(float(head), 3),
        "raw_value": raw_value,
        "normalized_value": normalized_value,
        "evidence": evidence or [],
        "applied": applied,
        "availability": "AVAILABLE" if status != "UNAVAILABLE" else "UNAVAILABLE",
    }
    if extra:
        out.update(extra)
    return out


def score_segment_head_chest(
    seg: dict[str, Any],
    *,
    all_segments: Optional[list[dict[str, Any]]] = None,
    global_baseline: Optional[dict[str, Any]] = None,
    disable_families: Optional[set[str]] = None,
) -> dict[str, Any]:
    all_segments = all_segments or []
    global_baseline = global_baseline or {}
    disable = set(disable_families or [])
    obs = _obs(seg)
    src = _src(seg)
    f0 = _f0(seg)
    band = pitch_band(f0)
    rms = _rms(seg)

    ve = seg.get("vocal_evidence") or {}
    if rms is not None and float(rms) <= 1e-5:
        return _unavailable(seg, reason="no_energy")
    if ve.get("vocal_energy") is not None and float(ve["vocal_energy"]) <= 0:
        return _unavailable(seg, reason="no_vocal_energy")

    period = obs.get("periodicity_primary_db")
    rough = bool(seg.get("roughness_hint")) or (
        period is not None and float(period) < 3.0 and not src.get("valid")
    )
    if rough and not src.get("valid"):
        return _unavailable(seg, reason="rough_invalid_source", register_validity="LOW")

    # Breathiness cues (do not auto-head)
    breathy = False
    if period is not None and float(period) < 6.0 and not src.get("valid"):
        breathy = True
    if seg.get("breathiness_hint"):
        breathy = True

    formant_conf = obs.get("formant_confidence")
    if formant_conf is None:
        formant_conf = (ve.get("formant_confidence") if isinstance(ve, dict) else None)

    base_naq, naq_mode = _band_or_global_baseline(
        all_segments, band, "src.estimated_naq", global_baseline, "naq"
    )
    base_oq, oq_mode = _band_or_global_baseline(
        all_segments, band, "src.estimated_oq_proxy", global_baseline, "oq"
    )
    base_h1, h1_mode = _band_or_global_baseline(
        all_segments, band, "raw_h1_h2_proxy_db", global_baseline, "h1_h2"
    )
    base_mfdr, mfdr_mode = _band_or_global_baseline(
        all_segments, band, "src.estimated_mfdr_norm_proxy", global_baseline, "mfdr_norm"
    )
    base_rms, _ = _band_or_global_baseline(
        all_segments, band, "rms", global_baseline, "rms"
    )

    family_contrib: dict[str, dict[str, Any]] = {}
    signed_parts: list[tuple[str, float, float]] = []  # (id, signed, weight_mass)

    # --- SOURCE_FLOW ---
    if "SOURCE_FLOW" in disable:
        family_contrib["SOURCE_FLOW"] = _family_packet(
            status="UNAVAILABLE",
            signed_vote=0,
            vote_strength=0,
            reliability=0,
            chest=0,
            head=0,
            applied=False,
            extra={"disabled": True},
        )
    elif src.get("valid"):
        flow_c = flow_h = 0.0
        flow_ev: list[str] = []
        signed = 0.0
        strength = 0.0
        rel = 1.0
        if rough:
            rel *= cfg.ROUGH_RELIABILITY
        naq = src.get("estimated_naq")
        oq = src.get("estimated_oq_proxy")
        mfdr = src.get("estimated_mfdr_norm_proxy")
        if naq is not None and base_naq is not None:
            d = float(naq) - float(base_naq)
            if d <= cfg.NAQ_CHEST_DELTA:
                flow_c += 1.0
                flow_ev.append("naq_rel_chest")
                signed -= 1.0
                strength += 1.0
            elif d >= cfg.NAQ_HEAD_DELTA:
                flow_h += 1.0
                flow_ev.append("naq_rel_head")
                signed += 1.0
                strength += 1.0
        elif naq is not None:
            # Absolute prior — not neutralized when baseline missing
            if float(naq) <= cfg.ABS_NAQ_CHEST:
                w = cfg.ABS_PRIOR_WEIGHT
                flow_c += w
                flow_ev.append("naq_abs_chest")
                signed -= 1.0
                strength += w
            elif float(naq) >= cfg.ABS_NAQ_HEAD:
                w = cfg.ABS_PRIOR_WEIGHT
                flow_h += w
                flow_ev.append("naq_abs_head")
                signed += 1.0
                strength += w
        if oq is not None and base_oq is not None:
            d = float(oq) - float(base_oq)
            if d <= cfg.OQ_CHEST_DELTA:
                flow_c += 1.0
                flow_ev.append("oq_rel_chest")
                signed -= 1.0
                strength += 1.0
            elif d >= cfg.OQ_HEAD_DELTA:
                flow_h += 1.0
                flow_ev.append("oq_rel_head")
                signed += 1.0
                strength += 1.0
        if mfdr is not None and base_mfdr is not None and float(base_mfdr) > 0:
            ratio = float(mfdr) / float(base_mfdr)
            # Intensity confound
            loud = (
                rms is not None
                and base_rms is not None
                and float(base_rms) > 0
                and float(rms) > float(base_rms) * 2.2
            )
            if ratio >= cfg.MFDR_CHEST_RATIO and not (loud and not flow_ev):
                flow_c += 1.0
                flow_ev.append("mfdr_rel_chest")
                signed -= 1.0
                strength += 1.0
            elif ratio <= 0.85:
                flow_h += 1.0
                flow_ev.append("mfdr_rel_head")
                signed += 1.0
                strength += 1.0

        if strength > 0:
            signed_n = float(np.clip(signed / max(strength, 1e-9), -1, 1))
        else:
            signed_n = 0.0
        mass_c = flow_c * cfg.WEIGHT_FLOW * rel
        mass_h = flow_h * cfg.WEIGHT_FLOW * rel
        st = (
            "CHEST"
            if mass_c > mass_h
            else "HEAD"
            if mass_h > mass_c
            else ("NEUTRAL" if (mass_c + mass_h) > 0 else "NO_DIRECTION")
        )
        family_contrib["SOURCE_FLOW"] = _family_packet(
            status=st,
            signed_vote=signed_n,
            vote_strength=strength * rel,
            reliability=rel,
            chest=mass_c,
            head=mass_h,
            raw_value={"naq": naq, "oq": oq, "mfdr": mfdr},
            normalized_value={"naq_mode": naq_mode, "oq_mode": oq_mode, "mfdr_mode": mfdr_mode},
            evidence=flow_ev,
        )
        if st in ("CHEST", "HEAD", "NEUTRAL") and (mass_c + mass_h) > 0:
            signed_parts.append(("SOURCE_FLOW", signed_n, mass_c + mass_h))
    else:
        family_contrib["SOURCE_FLOW"] = _family_packet(
            status="UNAVAILABLE",
            signed_vote=0,
            vote_strength=0,
            reliability=0,
            chest=0,
            head=0,
            applied=False,
        )

    # --- HARMONIC_SOURCE ---
    h1 = obs.get("raw_h1_h2_proxy_db")
    src_h1 = src.get("estimated_source_h1_h2_db") if src.get("valid") else None
    h_use = src_h1 if src_h1 is not None else h1
    if "HARMONIC_SOURCE" in disable:
        family_contrib["HARMONIC_SOURCE"] = _family_packet(
            status="UNAVAILABLE",
            signed_vote=0,
            vote_strength=0,
            reliability=0,
            chest=0,
            head=0,
            applied=False,
            extra={"disabled": True},
        )
    elif breathy and not src.get("valid") and h_use is not None:
        # breathiness ≠ head — suppress directional harmonic under contamination
        family_contrib["HARMONIC_SOURCE"] = _family_packet(
            status="UNAVAILABLE",
            signed_vote=0,
            vote_strength=0,
            reliability=0,
            chest=0,
            head=0,
            raw_value=float(h_use),
            applied=False,
            extra={"suppressed": "breathiness_contamination"},
        )
    elif h_use is not None:
        rel = 1.0
        if breathy:
            rel *= cfg.BREATHY_HARMONIC_RELIABILITY
        if rough:
            rel *= cfg.ROUGH_RELIABILITY
        if formant_conf is not None and float(formant_conf) < 0.35:
            rel *= cfg.FORMANT_LOW_HARMONIC_RELIABILITY
        harm_c = harm_h = 0.0
        signed = 0.0
        strength = 0.0
        if base_h1 is not None:
            d = float(h_use) - float(base_h1)
            if d <= cfg.H1H2_CHEST_DELTA:
                harm_c = 1.0 * cfg.WEIGHT_HARMONIC
                signed = -1.0
                strength = 1.0
            elif d >= cfg.H1H2_HEAD_DELTA:
                harm_h = 1.0 * cfg.WEIGHT_HARMONIC
                signed = 1.0
                strength = 1.0
        else:
            if float(h_use) <= cfg.ABS_H1H2_CHEST:
                w = cfg.ABS_PRIOR_WEIGHT * cfg.WEIGHT_HARMONIC
                harm_c = w
                signed = -1.0
                strength = cfg.ABS_PRIOR_WEIGHT
            elif float(h_use) >= cfg.ABS_H1H2_HEAD:
                w = cfg.ABS_PRIOR_WEIGHT * cfg.WEIGHT_HARMONIC
                harm_h = w
                signed = 1.0
                strength = cfg.ABS_PRIOR_WEIGHT
        harm_c *= rel
        harm_h *= rel
        st = (
            "CHEST"
            if harm_c > harm_h
            else "HEAD"
            if harm_h > harm_c
            else ("NEUTRAL" if (harm_c + harm_h) > 0 else "NO_DIRECTION")
        )
        family_contrib["HARMONIC_SOURCE"] = _family_packet(
            status=st,
            signed_vote=signed if strength > 0 else 0.0,
            vote_strength=strength * rel,
            reliability=rel,
            chest=harm_c,
            head=harm_h,
            raw_value=float(h_use),
            normalized_value={"h1_mode": h1_mode},
            # formant-corrected H1*-H2* hook (future): not applied in v1.2
            extra={"formant_corrected_hook": False},
        )
        if st in ("CHEST", "HEAD") and (harm_c + harm_h) > 0:
            signed_parts.append(("HARMONIC_SOURCE", signed, harm_c + harm_h))
    else:
        family_contrib["HARMONIC_SOURCE"] = _family_packet(
            status="UNAVAILABLE",
            signed_vote=0,
            vote_strength=0,
            reliability=0,
            chest=0,
            head=0,
            applied=False,
        )

    # --- SPECTRAL_WEIGHT ---
    tilt = obs.get("spectral_tilt_db_per_oct")
    e24 = obs.get("energy_2_4k")
    if "SPECTRAL_WEIGHT" in disable:
        family_contrib["SPECTRAL_WEIGHT"] = _family_packet(
            status="UNAVAILABLE",
            signed_vote=0,
            vote_strength=0,
            reliability=0,
            chest=0,
            head=0,
            applied=False,
            extra={"disabled": True},
        )
    elif tilt is not None or e24 is not None:
        rel = 1.0
        if breathy:
            rel *= cfg.BREATHY_SPECTRAL_RELIABILITY
        if rough:
            rel *= cfg.ROUGH_RELIABILITY
        fam_ok = True
        if (
            rms is not None
            and base_rms is not None
            and float(base_rms) > 0
            and float(rms) > float(base_rms) * 2.5
            and tilt is not None
            and float(tilt) >= cfg.TILT_CHEST
            and e24 is None
        ):
            fam_ok = False
        spec_c = spec_h = 0.0
        signed = 0.0
        strength = 0.0
        if fam_ok:
            if tilt is not None:
                if float(tilt) >= cfg.TILT_CHEST:
                    spec_c += cfg.WEIGHT_SPECTRAL
                    signed -= 1.0
                    strength += 1.0
                elif float(tilt) <= cfg.TILT_HEAD:
                    spec_h += cfg.WEIGHT_SPECTRAL
                    signed += 1.0
                    strength += 1.0
            if e24 is not None:
                if float(e24) >= 0.18:
                    spec_c += cfg.WEIGHT_SPECTRAL
                    signed -= 1.0
                    strength += 1.0
                elif float(e24) <= 0.08:
                    spec_h += cfg.WEIGHT_SPECTRAL
                    signed += 1.0
                    strength += 1.0
        spec_c *= rel
        spec_h *= rel
        # Only apply if source family present OR strong spectral mass
        source_ok = family_contrib.get("SOURCE_FLOW", {}).get("status") in (
            "CHEST",
            "HEAD",
            "NEUTRAL",
        ) or family_contrib.get("HARMONIC_SOURCE", {}).get("status") in ("CHEST", "HEAD")
        applied = bool(source_ok or (spec_c + spec_h) >= cfg.WEIGHT_SPECTRAL * 1.5)
        st = (
            "CHEST"
            if spec_c > spec_h
            else "HEAD"
            if spec_h > spec_c
            else ("NEUTRAL" if (spec_c + spec_h) > 0 else "NO_DIRECTION")
        )
        if not applied:
            st = "NO_DIRECTION" if st != "UNAVAILABLE" else st
        family_contrib["SPECTRAL_WEIGHT"] = _family_packet(
            status=st if applied else "NO_DIRECTION",
            signed_vote=(signed / max(strength, 1e-9)) if strength and applied else 0.0,
            vote_strength=strength * rel if applied else 0.0,
            reliability=rel,
            chest=spec_c if applied else 0.0,
            head=spec_h if applied else 0.0,
            raw_value={"tilt": tilt, "e24": e24},
            applied=applied,
        )
        if applied and st in ("CHEST", "HEAD") and (spec_c + spec_h) > 0:
            signed_parts.append(
                ("SPECTRAL_WEIGHT", signed / max(strength, 1e-9), spec_c + spec_h)
            )
    else:
        family_contrib["SPECTRAL_WEIGHT"] = _family_packet(
            status="UNAVAILABLE",
            signed_vote=0,
            vote_strength=0,
            reliability=0,
            chest=0,
            head=0,
            applied=False,
        )

    # --- CONTACT (supporting only) ---
    from audio_analyzer.vocal_function.evidence.families import firmer_like, lighter_like

    firm = firmer_like(seg, global_baseline)
    light = lighter_like(seg)
    contact_prof = seg.get("contact_profile_during") or seg.get("contact_hint")
    source_dir_ok = any(
        family_contrib.get(fid, {}).get("status") in ("CHEST", "HEAD")
        for fid in _SOURCE_FAMILIES
    )
    if "CONTACT" in disable:
        family_contrib["CONTACT"] = _family_packet(
            status="UNAVAILABLE",
            signed_vote=0,
            vote_strength=0,
            reliability=0,
            chest=0,
            head=0,
            applied=False,
            extra={"disabled": True},
        )
    elif firm or light or contact_prof:
        c_c = c_h = 0.0
        signed = 0.0
        if firm or contact_prof == "firmer_like":
            c_c = cfg.WEIGHT_CONTACT
            signed = -1.0
        if light or contact_prof == "lighter_like":
            c_h = cfg.WEIGHT_CONTACT
            signed = 1.0 if c_h >= c_c else signed
            if c_c and c_h:
                signed = 0.0
        applied = bool(source_dir_ok and (c_c or c_h))
        st = "CHEST" if c_c > c_h else "HEAD" if c_h > c_c else "NO_DIRECTION"
        family_contrib["CONTACT"] = _family_packet(
            status=st if (c_c or c_h) else "NO_DIRECTION",
            signed_vote=signed if applied else 0.0,
            vote_strength=cfg.WEIGHT_CONTACT if applied else 0.0,
            reliability=1.0 if applied else 0.0,
            chest=c_c if applied else 0.0,
            head=c_h if applied else 0.0,
            applied=applied,
            extra={"firm": bool(firm), "light": bool(light)},
        )
        if applied:
            signed_parts.append(("CONTACT", signed, c_c + c_h))
    else:
        family_contrib["CONTACT"] = _family_packet(
            status="UNAVAILABLE",
            signed_vote=0,
            vote_strength=0,
            reliability=0,
            chest=0,
            head=0,
            applied=False,
        )

    chest_raw = sum(float(f.get("chest") or 0) for f in family_contrib.values())
    head_raw = sum(float(f.get("head") or 0) for f in family_contrib.values())
    evidence_mass = float(chest_raw + head_raw)
    directionality = (
        abs(chest_raw - head_raw) / max(evidence_mass, 1e-9) if evidence_mass > 0 else 0.0
    )

    # Family agreement among directional source+spectral votes
    dir_votes = [
        float(family_contrib[fid]["signed_vote"])
        for fid in ("SOURCE_FLOW", "HARMONIC_SOURCE", "SPECTRAL_WEIGHT")
        if family_contrib.get(fid, {}).get("status") in ("CHEST", "HEAD")
        and family_contrib[fid].get("applied", True)
    ]
    if len(dir_votes) >= 2:
        signs = [1 if v > 0 else -1 for v in dir_votes if abs(v) > 1e-6]
        if signs:
            agreement = abs(sum(signs)) / len(signs)
        else:
            agreement = 0.0
    elif len(dir_votes) == 1:
        agreement = 0.55
    else:
        agreement = 0.0

    n_source_dir = sum(
        1
        for fid in _SOURCE_FAMILIES
        if family_contrib.get(fid, {}).get("status") in ("CHEST", "HEAD")
    )
    families_used = [
        fid
        for fid, info in family_contrib.items()
        if info.get("applied")
        and info.get("status") not in ("UNAVAILABLE",)
        and (float(info.get("chest") or 0) > 0 or float(info.get("head") or 0) > 0)
    ]

    base_meta = {
        "start_sec": seg.get("start_sec"),
        "end_sec": seg.get("end_sec"),
        "chest_raw_evidence": round(chest_raw, 3),
        "head_raw_evidence": round(head_raw, 3),
        "evidence_mass": round(evidence_mass, 3),
        "directionality": round(directionality, 3),
        "family_agreement": round(agreement, 3),
        "family_contribution": family_contrib,
        "signed_family_votes": {
            fid: family_contrib[fid].get("signed_vote") for fid in cfg.FAMILY_IDS
        },
        "evidence_families": families_used,
        "n_families": len(families_used),
        "n_source_families": n_source_dir,
        "f0_hz": f0,
        "pitch_band": band,
        "rms": rms,
        "f0_used_as_register_vote": False,
        "breathy_contamination_guard": breathy,
        "absolute_vs_relative": {
            "naq_mode": naq_mode,
            "oq_mode": oq_mode,
            "h1_mode": h1_mode,
            "mfdr_mode": mfdr_mode,
        },
    }

    if evidence_mass < cfg.MIN_EVIDENCE_MASS_SEGMENT:
        return {
            **base_meta,
            "head_chest_index": None,
            "chest_score": round(chest_raw, 3),
            "head_score": round(head_raw, 3),
            "confidence": "low",
            "status": "INSUFFICIENT",
            "reason": "low_evidence_mass",
            "register_validity": "LOW",
        }
    if n_source_dir < 1:
        return {
            **base_meta,
            "head_chest_index": None,
            "chest_score": round(chest_raw, 3),
            "head_score": round(head_raw, 3),
            "confidence": "low",
            "status": "INSUFFICIENT",
            "reason": "no_source_family_direction",
            "register_validity": "LOW",
        }

    index = head_raw / max(evidence_mass, 1e-9)
    if len(families_used) >= cfg.MIN_FAMILIES_FOR_SEGMENT:
        if chest_raw >= 1.5 * (head_raw + 1e-6):
            index = min(index, 0.35)
        if head_raw >= 1.5 * (chest_raw + 1e-6):
            index = max(index, 0.65)

    conf = "low"
    if (
        len(families_used) >= 3
        and evidence_mass >= 1.5
        and directionality >= 0.15
        and agreement >= cfg.MIN_FAMILY_AGREEMENT_HIGH
    ):
        conf = "high"
    elif len(families_used) >= cfg.MIN_FAMILIES_FOR_SEGMENT and evidence_mass >= cfg.MIN_EVIDENCE_MASS_SEGMENT:
        conf = "medium"
    elif evidence_mass >= 1.2 and agreement < 0.4:
        conf = "medium"  # mixed evidence — not high

    return {
        **base_meta,
        "head_chest_index": float(np.clip(index, 0.0, 1.0)),
        "chest_score": round(chest_raw, 3),
        "head_score": round(head_raw, 3),
        "confidence": conf,
        "status": "OK",
        "register_validity": "OK",
    }


def _unavailable(
    seg: dict[str, Any], *, reason: str, register_validity: str = "LOW"
) -> dict[str, Any]:
    empty = {
        fid: _family_packet(
            status="UNAVAILABLE",
            signed_vote=0,
            vote_strength=0,
            reliability=0,
            chest=0,
            head=0,
            applied=False,
        )
        for fid in cfg.FAMILY_IDS
    }
    return {
        "start_sec": seg.get("start_sec"),
        "end_sec": seg.get("end_sec"),
        "head_chest_index": None,
        "chest_score": None,
        "head_score": None,
        "chest_raw_evidence": None,
        "head_raw_evidence": None,
        "evidence_mass": 0.0,
        "directionality": None,
        "family_agreement": 0.0,
        "confidence": "low",
        "status": "UNAVAILABLE",
        "reason": reason,
        "register_validity": register_validity,
        "evidence_families": [],
        "family_contribution": empty,
        "signed_family_votes": {fid: 0.0 for fid in cfg.FAMILY_IDS},
        "n_families": 0,
        "n_source_families": 0,
        "f0_hz": _f0(seg),
        "pitch_band": pitch_band(_f0(seg)),
        "rms": _rms(seg),
        "f0_used_as_register_vote": False,
    }


def _seg_weight(row: dict[str, Any]) -> float:
    if row.get("head_chest_index") is None:
        return 0.0
    conf_w = {"high": 1.0, "medium": 0.7, "low": 0.35}.get(row.get("confidence") or "low", 0.3)
    mass_w = min(1.5, float(row.get("evidence_mass") or 0) / 1.2)
    fam_w = min(1.0, 0.25 * float(row.get("n_families") or 0))
    agree = float(row.get("family_agreement") or 0.5)
    # Cap influence of low-agreement blocks so one chest-heavy block can't dominate
    agree_w = 0.55 + 0.45 * agree
    return max(0.05, conf_w * (0.35 + fam_w) * max(0.4, mass_w) * agree_w)


def weighted_index(rows: list[dict[str, Any]]) -> Optional[float]:
    usable = [
        r
        for r in rows
        if r.get("head_chest_index") is not None
        and float(r.get("evidence_mass") or 0) >= cfg.MIN_EVIDENCE_MASS_SEGMENT
    ]
    if len(usable) < cfg.MIN_SEGMENTS_FOR_RATIO:
        return None
    xs = np.array([float(r["head_chest_index"]) for r in usable], dtype=float)
    ws = np.array([_seg_weight(r) for r in usable], dtype=float)
    if float(ws.sum()) <= 0:
        return None
    order = np.argsort(xs)
    xs, ws = xs[order], ws[order]
    n = len(xs)
    if n >= 6:
        lo, hi = max(1, n // 10), max(n - n // 10, n // 2 + 1)
        xs, ws = xs[lo:hi], ws[lo:hi]
    # Prefer trimmed weighted mean; also expose median for audit
    return float(np.average(xs, weights=ws))


def song_evidence_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    usable = [r for r in rows if r.get("head_chest_index") is not None]
    mass = float(sum(float(r.get("evidence_mass") or 0) for r in usable))
    dirs = [float(r["directionality"]) for r in usable if r.get("directionality") is not None]
    agrees = [float(r.get("family_agreement") or 0) for r in usable]
    chest_sum = float(sum(float(r.get("chest_raw_evidence") or 0) for r in usable))
    head_sum = float(sum(float(r.get("head_raw_evidence") or 0) for r in usable))
    global_ratio_dir = abs(chest_sum - head_sum) / max(chest_sum + head_sum, 1e-9)
    mean_signed = {}
    for fid in cfg.FAMILY_IDS:
        vals = []
        for r in usable:
            v = (r.get("signed_family_votes") or {}).get(fid)
            if v is not None and (r.get("family_contribution") or {}).get(fid, {}).get("status") in (
                "CHEST",
                "HEAD",
            ):
                vals.append(float(v))
        mean_signed[fid] = round(float(np.mean(vals)), 3) if vals else None
    return {
        "n_usable": len(usable),
        "total_evidence_mass": round(mass, 3),
        "chest_raw_sum": round(chest_sum, 3),
        "head_raw_sum": round(head_sum, 3),
        "global_ratio_directionality": round(global_ratio_dir, 3),
        "segment_directionality_mean": round(float(np.mean(dirs)), 3) if dirs else 0.0,
        "segment_directionality_median": round(float(np.median(dirs)), 3) if dirs else 0.0,
        # legacy alias kept for callers
        "mean_directionality": round(float(np.mean(dirs)), 3) if dirs else 0.0,
        "mean_family_agreement": round(float(np.mean(agrees)), 3) if agrees else 0.0,
        "mean_source_families": round(
            float(np.mean([float(r.get("n_source_families") or 0) for r in usable])), 3
        )
        if usable
        else 0.0,
        "mean_signed_family_votes": mean_signed,
    }


def ratio_eligible(stats: dict[str, Any]) -> bool:
    return (
        int(stats.get("n_usable") or 0) >= cfg.MIN_SEGMENTS_FOR_RATIO
        and float(stats.get("total_evidence_mass") or 0) >= cfg.MIN_SONG_EVIDENCE_MASS
        and float(stats.get("mean_source_families") or 0) >= cfg.MIN_FAMILY_COVERAGE_SONG * 0.5
    )


def detect_neutral_collapse(
    rows: list[dict[str, Any]],
    ranges: dict[str, Any],
    *,
    index: Optional[float],
    stats: dict[str, Any],
) -> bool:
    if index is None:
        return False
    if abs(float(index) - 0.5) > cfg.NEUTRAL_COLLAPSE_EPS:
        return False
    if float(stats.get("global_ratio_directionality") or 0) >= 0.18:
        return False
    if float(stats.get("total_evidence_mass") or 0) >= cfg.MIN_SONG_EVIDENCE_MASS * 3.0:
        # strong intermediate evidence — not collapse
        return False
    bands = ranges.get("bands") or ranges
    near = avail = 0
    for band in ("low", "mid", "high"):
        b = bands.get(band) or {}
        if not b.get("available") or b.get("index") is None:
            continue
        avail += 1
        if abs(float(b["index"]) - 0.5) <= cfg.NEUTRAL_COLLAPSE_EPS:
            near += 1
    return avail >= 2 and near >= 2


def index_to_ratios(index: Optional[float]) -> dict[str, Any]:
    if index is None:
        return {"available": False, "chest_ratio": None, "head_ratio": None, "index": None}
    head = max(0, min(100, int(round(float(index) * 100))))
    return {
        "available": True,
        "chest_ratio": 100 - head,
        "head_ratio": head,
        "index": round(float(index), 3),
    }


def aggregate_range_profiles(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    coverage: dict[str, float] = {}
    warnings: list[str] = []
    total_w = sum(_seg_weight(r) for r in rows if r.get("head_chest_index") is not None) or 1.0
    raw_all = [float(r["head_chest_index"]) for r in rows if r.get("head_chest_index") is not None]
    raw_var = float(np.var(raw_all)) if len(raw_all) >= 3 else 0.0
    band_idxs = []
    for band in ("low", "mid", "high"):
        band_rows = [
            r
            for r in rows
            if r.get("pitch_band") == band and r.get("head_chest_index") is not None
        ]
        w = sum(_seg_weight(r) for r in band_rows)
        coverage[band] = round(w / total_w, 3)
        raw_idxs = [float(r["head_chest_index"]) for r in band_rows]
        if len(band_rows) < 2:
            out[band] = {
                "available": False,
                "chest_ratio": None,
                "head_ratio": None,
                "index": None,
                "n_segments": len(band_rows),
                "mass": round(sum(float(r.get("evidence_mass") or 0) for r in band_rows), 3),
                "raw_variance": None,
            }
        else:
            idx = weighted_index(band_rows)
            if idx is None:
                out[band] = {
                    "available": False,
                    "chest_ratio": None,
                    "head_ratio": None,
                    "index": None,
                    "n_segments": len(band_rows),
                    "mass": round(sum(float(r.get("evidence_mass") or 0) for r in band_rows), 3),
                    "raw_variance": round(float(np.var(raw_idxs)), 4) if len(raw_idxs) > 1 else 0.0,
                }
            else:
                ratios = index_to_ratios(idx)
                out[band] = {
                    **ratios,
                    "n_segments": len(band_rows),
                    "mass": round(sum(float(r.get("evidence_mass") or 0) for r in band_rows), 3),
                    "raw_variance": round(float(np.var(raw_idxs)), 4) if len(raw_idxs) > 1 else 0.0,
                    "raw_indexes": [round(x, 3) for x in raw_idxs[:12]],
                }
                band_idxs.append(idx)
    if len(band_idxs) >= 2 and raw_var > 0.02:
        if float(np.var(band_idxs)) < 0.002:
            warnings.append("OVER_SMOOTHED_RANGE_PROFILE_WARNING")
    return {"bands": out, "coverage": coverage, "warnings": warnings}


def aggregate_family_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for fid in cfg.FAMILY_IDS:
        counts = {"CHEST": 0, "HEAD": 0, "NEUTRAL": 0, "NO_DIRECTION": 0, "UNAVAILABLE": 0}
        signed_vals = []
        for r in rows:
            info = (r.get("family_contribution") or {}).get(fid) or {}
            st = info.get("status") or "UNAVAILABLE"
            if st not in counts:
                st = "NO_DIRECTION"
            counts[st] += 1
            if st in ("CHEST", "HEAD") and info.get("signed_vote") is not None:
                signed_vals.append(float(info["signed_vote"]))
        ranked = sorted(
            ((k, v) for k, v in counts.items() if k != "UNAVAILABLE"),
            key=lambda kv: kv[1],
            reverse=True,
        )
        dominant = ranked[0][0] if ranked and ranked[0][1] > 0 else "UNAVAILABLE"
        if counts["UNAVAILABLE"] >= sum(counts.values()) * 0.7:
            dominant = "UNAVAILABLE"
        summary[fid] = {
            "dominant": dominant,
            "counts": counts,
            "mean_signed_vote": round(float(np.mean(signed_vals)), 3) if signed_vals else None,
            "coverage": round(1.0 - counts["UNAVAILABLE"] / max(sum(counts.values()), 1), 3),
        }
    return summary


def score_all_segments(
    segments: list[dict[str, Any]],
    *,
    baseline: Optional[dict[str, Any]] = None,
    disable_families: Optional[set[str]] = None,
) -> list[dict[str, Any]]:
    return [
        score_segment_head_chest(
            s,
            all_segments=segments,
            global_baseline=baseline,
            disable_families=disable_families,
        )
        for s in segments
    ]


def family_ablation(
    segments: list[dict[str, Any]],
    *,
    baseline: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Leave-one-family-out Head/Chest ratios for developer audit."""
    out: dict[str, Any] = {}
    full = score_all_segments(segments, baseline=baseline)
    full_idx = weighted_index(full)
    out["FULL"] = index_to_ratios(full_idx)
    for fid in cfg.FAMILY_IDS:
        rows = score_all_segments(segments, baseline=baseline, disable_families={fid})
        idx = weighted_index(rows)
        out[f"without_{fid}"] = index_to_ratios(idx)
    return out
