"""Episode builder v2.2 — true PRE/DURING/POST context + shift cause classification."""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from audio_analyzer.vocal_function import config as cfg


def merge_overlapping(
    windows: list[dict[str, Any]],
    *,
    gap_sec: float = 0.75,
    type_key: str = "type",
) -> list[dict[str, Any]]:
    if not windows:
        return []
    ordered = sorted(windows, key=lambda w: float(w.get("start_sec") or 0))
    episodes: list[dict[str, Any]] = []
    cur = dict(ordered[0])
    cur["members"] = [ordered[0]]
    for w in ordered[1:]:
        same = (w.get(type_key) or cur.get(type_key)) == cur.get(type_key)
        if same and float(w.get("start_sec") or 0) <= float(cur.get("end_sec") or 0) + gap_sec:
            cur["end_sec"] = max(float(cur["end_sec"]), float(w.get("end_sec") or 0))
            cur["members"].append(w)
            if w.get("concern"):
                cur["concern"] = True
        else:
            episodes.append(cur)
            cur = dict(w)
            cur["members"] = [w]
    episodes.append(cur)
    return episodes


def _vocal_valid(seg: dict[str, Any]) -> bool:
    """Legacy global gate — contact/register/high-note style episodes."""
    if not seg.get("valid"):
        return False
    ve = seg.get("vocal_evidence") or {}
    return bool(ve.get("vocal_specific", True))


def _episode_segment_ok(seg: dict[str, Any], episode_type: str) -> bool:
    """Dimension-aware gate: breathiness/effort/contact must not require global valid/GIF."""
    from audio_analyzer.vocal_function.validity import dim_valid
    from audio_analyzer.vocal_evidence.phonation_quality import vocal_presence_ok

    if episode_type == "AIR_LEAKAGE":
        return dim_valid(seg, "breathiness") or vocal_presence_ok(seg)
    if episode_type == "ROUGHNESS":
        return dim_valid(seg, "roughness") or vocal_presence_ok(seg)
    if episode_type == "GENERAL_EFFORT":
        return dim_valid(seg, "effort") or vocal_presence_ok(seg)
    if episode_type in ("HIGH_NOTE",):
        # High-note F0 still prefers vocal-specific, but effort concern can use effort dim
        return _vocal_valid(seg) or dim_valid(seg, "effort")
    return _vocal_valid(seg)


def select_pre_context(
    all_segments: list[dict[str, Any]],
    *,
    episode_start: float,
    max_sec: float = cfg.PRE_CONTEXT_MAX_SEC,
    n: int = cfg.PRE_CONTEXT_N,
) -> list[dict[str, Any]]:
    """Segments BEFORE episode start (outside episode), nearest first."""
    lo = episode_start - max_sec
    cands = [
        s
        for s in all_segments
        if _vocal_valid(s)
        and float(s.get("end_sec") or 0) <= episode_start + 1e-6
        and float(s.get("start_sec") or 0) >= lo
    ]
    cands.sort(key=lambda s: float(s.get("end_sec") or 0), reverse=True)
    return list(reversed(cands[:n]))


def select_post_context(
    all_segments: list[dict[str, Any]],
    *,
    episode_end: float,
    max_sec: float = cfg.POST_CONTEXT_MAX_SEC,
    n: int = cfg.POST_CONTEXT_N,
) -> list[dict[str, Any]]:
    """Segments AFTER episode end (outside episode), nearest first."""
    hi = episode_end + max_sec
    cands = [
        s
        for s in all_segments
        if _vocal_valid(s)
        and float(s.get("start_sec") or 0) >= episode_end - 1e-6
        and float(s.get("end_sec") or 0) <= hi
    ]
    cands.sort(key=lambda s: float(s.get("start_sec") or 0))
    return cands[:n]


def _med(vals: list[Optional[float]]) -> Optional[float]:
    clean = [float(v) for v in vals if v is not None]
    return float(np.median(clean)) if clean else None


def _delta(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None:
        return None
    return float(b - a)


def _rms_db(rms: Optional[float]) -> Optional[float]:
    if rms is None or rms <= 0:
        return None
    return float(20.0 * np.log10(max(rms, 1e-12)))


def _intensity_delta_db(pre_rms: Optional[float], during_rms: Optional[float]) -> Optional[float]:
    if pre_rms is None or during_rms is None or pre_rms <= 0 or during_rms <= 0:
        return None
    return float(20.0 * np.log10(max(during_rms, 1e-12) / max(pre_rms, 1e-12)))


def _agg_pool(segs: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate acoustic/proxy fields from segment list."""
    f0s, rmss, periods, naqs, oqs, mfdrs, h1s, e24s, cents = (
        [],
        [],
        [],
        [],
        [],
        [],
        [],
        [],
        [],
    )
    f1s, f2s, form_confs, onset_slopes, firms, efforts, leaks = (
        [],
        [],
        [],
        [],
        [],
        [],
        [],
    )
    for s in segs:
        obs = s.get("observations") or {}
        src = ((s.get("level2_proxies") or {}).get("glottal_source") or {})
        form = ((s.get("level2_proxies") or {}).get("formants") or {})
        if obs.get("f0_hz"):
            f0s.append(float(obs["f0_hz"]))
        if obs.get("rms") is not None:
            rmss.append(float(obs["rms"]))
        p = s.get("periodicity")
        if p is None:
            p = obs.get("periodicity_primary_db")
        if p is not None:
            periods.append(float(p))
        if src.get("valid"):
            if src.get("estimated_naq") is not None:
                naqs.append(float(src["estimated_naq"]))
            if src.get("estimated_oq_proxy") is not None:
                oqs.append(float(src["estimated_oq_proxy"]))
            if src.get("estimated_mfdr_norm_proxy") is not None:
                mfdrs.append(float(src["estimated_mfdr_norm_proxy"]))
        if obs.get("raw_h1_h2_proxy_db") is not None:
            h1s.append(float(obs["raw_h1_h2_proxy_db"]))
        if obs.get("energy_2_4k") is not None:
            e24s.append(float(obs["energy_2_4k"]))
        if obs.get("spectral_centroid_hz") is not None:
            cents.append(float(obs["spectral_centroid_hz"]))
        if obs.get("onset_slope_db_per_sec") is not None:
            onset_slopes.append(float(obs["onset_slope_db_per_sec"]))
        if form.get("f1_hz") is not None:
            f1s.append(float(form["f1_hz"]))
        if form.get("f2_hz") is not None:
            f2s.append(float(form["f2_hz"]))
        if form.get("confidence") is not None:
            form_confs.append(float(form["confidence"]))
        elif form.get("valid") is True:
            form_confs.append(0.6)
        elif form.get("valid") is False:
            form_confs.append(0.2)
        if s.get("contact_profile_during") == "firmer_like":
            firms.append(1.0)
        elif s.get("contact_profile_during"):
            firms.append(0.0)
        if s.get("effort_during") == "elevated" or s.get("concern"):
            efforts.append(1.0)
        if s.get("leakage_like"):
            leaks.append(1.0)
    return {
        "f0_hz": _med(f0s),
        "rms": _med(rmss),
        "rms_db": _rms_db(_med(rmss)),
        "periodicity": _med(periods),
        "naq": _med(naqs),
        "oq": _med(oqs),
        "mfdr_norm": _med(mfdrs),
        "h1_h2": _med(h1s),
        "energy_2_4k": _med(e24s),
        "spectral_centroid_hz": _med(cents),
        "f1_hz": _med(f1s),
        "f2_hz": _med(f2s),
        "formant_confidence": _med(form_confs),
        "onset_slope": _med(onset_slopes),
        "contact_firmness": float(np.mean(firms)) if firms else None,
        "strain_like": float(np.mean(efforts)) if efforts else 0.0,
        "air_leakage": float(np.mean(leaks)) if leaks else None,
        "n": len(segs),
        "mid_presence": (
            "낮은 편"
            if e24s and float(np.median(e24s)) < 0.12
            else ("높은 편" if e24s and float(np.median(e24s)) > 0.2 else "보통")
        )
        if e24s
        else None,
    }


def _shift_flags(pre: dict[str, Any], during: dict[str, Any]) -> dict[str, Any]:
    """Independent SOURCE / EFFORT / RESONANCE / REGISTER shift scores (0–1 soft)."""
    naq_d = _delta(pre.get("naq"), during.get("naq"))
    oq_d = _delta(pre.get("oq"), during.get("oq"))
    mfdr_d = _delta(pre.get("mfdr_norm"), during.get("mfdr_norm"))
    h1_d = _delta(pre.get("h1_h2"), during.get("h1_h2"))
    e24_d = _delta(pre.get("energy_2_4k"), during.get("energy_2_4k"))
    cent_d = _delta(pre.get("spectral_centroid_hz"), during.get("spectral_centroid_hz"))
    f1_d = _delta(pre.get("f1_hz"), during.get("f1_hz"))
    f2_d = _delta(pre.get("f2_hz"), during.get("f2_hz"))
    intensity_d = _intensity_delta_db(pre.get("rms"), during.get("rms"))
    period_d = _delta(pre.get("periodicity"), during.get("periodicity"))
    f0_pre, f0_dur = pre.get("f0_hz"), during.get("f0_hz")
    f0_cents = None
    if f0_pre and f0_dur and f0_pre > 0 and f0_dur > 0:
        f0_cents = float(1200.0 * np.log2(f0_dur / f0_pre))

    # SOURCE: directional PRE→DURING glottal/harmonic change (not mere presence)
    src_hits = 0
    src_n = 0
    if naq_d is not None:
        src_n += 1
        if abs(naq_d) >= cfg.NAQ_SHIFT_HINT:
            src_hits += 1
    if oq_d is not None:
        src_n += 1
        if abs(oq_d) >= 0.05:
            src_hits += 1
    if mfdr_d is not None and pre.get("mfdr_norm"):
        src_n += 1
        if abs(mfdr_d) >= abs(float(pre["mfdr_norm"])) * cfg.MFDR_NORM_SHIFT_RATIO:
            src_hits += 1
    if h1_d is not None:
        src_n += 1
        if abs(h1_d) >= cfg.H1H2_SHIFT_DB:
            src_hits += 1
    source_shift = (src_hits / src_n) if src_n else 0.0

    # EFFORT: intensity + onset + roughness/periodicity + strain
    eff_hits = 0
    eff_n = 0
    if intensity_d is not None:
        eff_n += 1
        if intensity_d >= cfg.INTENSITY_OVERSHOOT_DB:
            eff_hits += 1
    if during.get("onset_slope") is not None:
        eff_n += 1
        if float(during["onset_slope"]) >= 80:
            eff_hits += 1
    if period_d is not None:
        eff_n += 1
        if period_d <= -2.0:
            eff_hits += 1
    if (during.get("strain_like") or 0) >= 0.4:
        eff_n += 1
        eff_hits += 1
    effort_shift = (eff_hits / max(1, eff_n)) if eff_n else float(during.get("strain_like") or 0)

    # RESONANCE: spectral/formant PRE→DURING (direction-aware later)
    res_hits = 0
    res_n = 0
    form_ok = (during.get("formant_confidence") or 0) >= 0.4 or (
        pre.get("formant_confidence") or 0
    ) >= 0.4
    if e24_d is not None:
        res_n += 1
        if abs(e24_d) >= cfg.ENERGY_24K_SHIFT:
            res_hits += 1
    if cent_d is not None:
        res_n += 1
        if abs(cent_d) >= cfg.CENTROID_SHIFT_HZ:
            res_hits += 1
    if form_ok and f1_d is not None:
        res_n += 1
        if abs(f1_d) >= 40:
            res_hits += 1
    if form_ok and f2_d is not None:
        res_n += 1
        if abs(f2_d) >= 60:
            res_hits += 1
    resonance_shift = (res_hits / res_n) if res_n else 0.0

    # REGISTER: large F0 jump + source change
    register_shift = 0.0
    if f0_cents is not None and abs(f0_cents) >= cfg.F0_JUMP_CENTS_REGISTER:
        register_shift = 0.5 + (0.5 if source_shift >= 0.4 else 0.0)

    return {
        "source_shift": round(float(source_shift), 3),
        "effort_shift": round(float(effort_shift), 3),
        "resonance_shift": round(float(resonance_shift), 3),
        "register_shift": round(float(register_shift), 3),
        "deltas": {
            "naq_delta": naq_d,
            "oq_delta": oq_d,
            "mfdr_norm_delta": mfdr_d,
            "h1_h2_delta": h1_d,
            "energy_2_4k_delta": e24_d,
            "spectral_centroid_delta": cent_d,
            "f1_delta": f1_d if form_ok else None,
            "f2_delta": f2_d if form_ok else None,
            "intensity_delta_db": intensity_d,
            "periodicity_delta": period_d,
            "f0_delta_cents": f0_cents,
        },
        "formant_usable": form_ok,
    }


def classify_cause_hint(shifts: dict[str, Any], *, e24_delta: Optional[float] = None) -> str:
    """Map independent shifts → SOURCE / EFFORT / RESONANCE / REGISTER / MIXED / UNCLEAR."""
    thr = 0.4
    high = {
        "SOURCE": (shifts.get("source_shift") or 0) >= thr,
        "EFFORT": (shifts.get("effort_shift") or 0) >= thr,
        "RESONANCE": (shifts.get("resonance_shift") or 0) >= thr,
        "REGISTER": (shifts.get("register_shift") or 0) >= thr,
    }
    # Directional resonance subtype tags (not abs collapse)
    resonance_kind = None
    if high["RESONANCE"] and e24_delta is not None:
        if e24_delta <= -cfg.ENERGY_24K_SHIFT:
            resonance_kind = "RESONANCE_PRESENCE_LOSS"
        elif e24_delta >= cfg.ENERGY_24K_SHIFT:
            resonance_kind = "RESONANCE_EXCESS_SHARPNESS"

    active = [k for k, v in high.items() if v]
    if len(active) >= 2:
        hint = "MIXED"
    elif len(active) == 1:
        hint = active[0]
        if hint == "RESONANCE" and resonance_kind:
            hint = resonance_kind
        elif hint == "SOURCE":
            hint = "SOURCE"
        elif hint == "EFFORT":
            hint = "EFFORT"
        elif hint == "REGISTER":
            hint = "REGISTER"
    else:
        hint = "UNCLEAR"
    return hint


def _provisional_phases(start: float, end: float) -> dict[str, Any]:
    dur = max(1e-6, end - start)
    return {
        "ENTRY": {"start_sec": start, "end_sec": start + 0.2 * dur},
        "PEAK": {"start_sec": start + 0.2 * dur, "end_sec": start + 0.45 * dur},
        "SUSTAIN": {"start_sec": start + 0.45 * dur, "end_sec": start + 0.75 * dur},
        "EXIT": {"start_sec": start + 0.75 * dur, "end_sec": start + 0.9 * dur},
        "RECOVERY": {"start_sec": start + 0.9 * dur, "end_sec": end},
        "phase_method": "PROVISIONAL",
        "phase_confidence": "low",
    }


def _acoustic_phases(members: list[dict[str, Any]], start: float, end: float) -> Optional[dict[str, Any]]:
    if len(members) < 3:
        return None
    f0s, mids = [], []
    for m in members:
        obs = m.get("observations") or {}
        f0 = obs.get("f0_hz") or m.get("f0_hz")
        mid = (float(m.get("start_sec") or 0) + float(m.get("end_sec") or 0)) / 2.0
        if f0:
            f0s.append(float(f0))
            mids.append(mid)
    if len(f0s) < 3:
        return None
    peak_i = int(np.argmax(f0s))
    peak_f0 = f0s[peak_i]
    sustain_idxs = [i for i, f in enumerate(f0s) if abs(f - peak_f0) / peak_f0 < 0.03]
    if not sustain_idxs:
        return None
    sustain_start = mids[min(sustain_idxs)]
    sustain_end = mids[max(sustain_idxs)]
    recovery_start = float(members[-1].get("start_sec") or end)
    conf = "medium" if len(f0s) >= 4 else "low"
    return {
        "ENTRY": {"start_sec": start, "end_sec": min(mids[peak_i], end)},
        "PEAK": {"start_sec": mids[peak_i], "end_sec": min(mids[peak_i] + 0.15, end)},
        "SUSTAIN": {"start_sec": sustain_start, "end_sec": sustain_end},
        "EXIT": {"start_sec": sustain_end, "end_sec": recovery_start},
        "RECOVERY": {"start_sec": recovery_start, "end_sec": end},
        "phase_method": "ACOUSTIC",
        "phase_confidence": conf,
    }


def build_feature_matrix(
    members: list[dict[str, Any]],
    pre_segs: list[dict[str, Any]],
    post_segs: list[dict[str, Any]],
    *,
    episode_type: str = "HIGH_NOTE",
) -> dict[str, Any]:
    pre = _agg_pool(pre_segs)
    during = _agg_pool(members)
    post = _agg_pool(post_segs)
    shifts = _shift_flags(pre, during)
    d = shifts["deltas"]

    intensity_delta = d.get("intensity_delta_db")
    intensity_overshoot_proxy = None
    if intensity_delta is not None:
        intensity_overshoot_proxy = float(max(0.0, intensity_delta - cfg.INTENSITY_OVERSHOOT_DB))

    # Recovery from POST (not last member)
    recovery: dict[str, Any]
    if not post_segs:
        recovery = {
            "returned_to_baseline": None,
            "recovery_time_sec": None,
            "post_effort_delta": None,
            "post_contact_delta": None,
            "post_periodicity_delta": None,
            "status": "UNKNOWN",
        }
    else:
        post_effort_d = _delta(during.get("strain_like"), post.get("strain_like"))
        post_period_d = _delta(during.get("periodicity"), post.get("periodicity"))
        post_contact_d = _delta(during.get("contact_firmness"), post.get("contact_firmness"))
        returned = False
        if (during.get("strain_like") or 0) >= 0.4 and (post.get("strain_like") or 0) < 0.35:
            returned = True
        if during.get("periodicity") and post.get("periodicity"):
            if float(post["periodicity"]) >= float(during["periodicity"]) - 1.0:
                returned = returned or (during.get("strain_like") or 0) < 0.4
        recovery_time = None
        if post_segs:
            recovery_time = float(post_segs[0].get("start_sec") or 0) - float(
                members[-1].get("end_sec") or members[-1].get("start_sec") or 0
            )
            recovery_time = max(0.0, recovery_time)
        recovery = {
            "returned_to_baseline": returned,
            "recovery_time_sec": recovery_time,
            "post_effort_delta": post_effort_d,
            "post_contact_delta": post_contact_d,
            "post_periodicity_delta": post_period_d,
            "status": "OBSERVED",
        }

    rough = any(m.get("roughness") for m in members)
    # leakage from members or leakage_like flags
    leak_vals = []
    for m in members:
        if m.get("leakage_like"):
            leak_vals.append(1.0)
        obs = m.get("observations") or {}
        # soft proxy: high H1-H2 + low periodicity
        if (obs.get("raw_h1_h2_proxy_db") or 0) >= 7 and (obs.get("periodicity_primary_db") or 99) <= 8:
            leak_vals.append(1.0)
    air_leakage = float(np.mean(leak_vals)) if leak_vals else during.get("air_leakage")

    form_conf = during.get("formant_confidence")
    f0_cont = "continuous"
    if d.get("f0_delta_cents") is not None and abs(d["f0_delta_cents"]) >= cfg.F0_JUMP_CENTS_REGISTER:
        f0_cont = "discontinuous"
    if any(m.get("dropout") for m in members):
        f0_cont = "dropout"

    transition_strength = None
    if episode_type == "REGISTER_TRANSITION" or (d.get("f0_delta_cents") is not None):
        cents = abs(d.get("f0_delta_cents") or 0)
        transition_strength = round(min(1.0, cents / 800.0), 3)

    return {
        "source": {
            "contact_firmness": during.get("contact_firmness"),
            "air_leakage": air_leakage,
            "estimated_naq": during.get("naq"),
            "naq_pre": pre.get("naq"),
            "naq_during": during.get("naq"),
            "naq_delta": d.get("naq_delta"),
            "estimated_oq_proxy": during.get("oq"),
            "oq_pre": pre.get("oq"),
            "oq_during": during.get("oq"),
            "oq_delta": d.get("oq_delta"),
            "estimated_mfdr_norm_proxy": during.get("mfdr_norm"),
            "mfdr_norm_delta": d.get("mfdr_norm_delta"),
            "h1_h2_proxy": during.get("h1_h2"),
            "h1_h2_delta": d.get("h1_h2_delta"),
            "source_shift": shifts["source_shift"],
        },
        "effort": {
            "strain_like": during.get("strain_like") or 0.0,
            "intensity_pre_db": pre.get("rms_db"),
            "intensity_during_db": during.get("rms_db"),
            "intensity_delta_db": intensity_delta,
            "intensity_overshoot_proxy": intensity_overshoot_proxy,
            "onset_hardening": during.get("onset_slope"),
            "persistence": float(np.mean([(during.get("strain_like") or 0)] * 2)),
            "effort_shift": shifts["effort_shift"],
            # legacy alias removed as boolean mean — keep numeric overshoot only
            "intensity_overshoot": intensity_overshoot_proxy,
        },
        "regularity": {
            "periodicity": during.get("periodicity"),
            "periodicity_pre": pre.get("periodicity"),
            "periodicity_during": during.get("periodicity"),
            "periodicity_delta": d.get("periodicity_delta"),
            "roughness": rough,
            "dropout": f0_cont == "dropout",
        },
        "register": {
            "transition_strength": transition_strength,
            "source_shift": shifts["source_shift"] if episode_type == "REGISTER_TRANSITION" else shifts["register_shift"],
            "f0_continuity": f0_cont,
            "f0_delta_cents": d.get("f0_delta_cents"),
            "register_shift": shifts["register_shift"],
        },
        "resonance": {
            "brightness_before": pre.get("spectral_centroid_hz"),
            "brightness_during": during.get("spectral_centroid_hz"),
            "mid_presence_before": pre.get("mid_presence"),
            "mid_presence_during": during.get("mid_presence"),
            "energy_2_4k_before": pre.get("energy_2_4k"),
            "energy_2_4k_pre": pre.get("energy_2_4k"),
            "energy_2_4k_during": during.get("energy_2_4k"),
            "energy_2_4k_delta": d.get("energy_2_4k_delta"),
            "brightness_delta": d.get("spectral_centroid_delta"),
            "spectral_centroid_delta": d.get("spectral_centroid_delta"),
            "f1_delta": d.get("f1_delta"),
            "f2_delta": d.get("f2_delta"),
            "formant_confidence": form_conf,
            "resonance_shift": shifts["resonance_shift"],
        },
        "onset": {"abruptness": during.get("onset_slope")},
        "recovery": recovery,
        "validity": {
            "vocal_specific": all(
                (m.get("validity") or {}).get("vocal_specific", True) for m in members
            )
            if members
            else True,
            "n_windows": len(members),
            "pre_n": len(pre_segs),
            "post_n": len(post_segs),
        },
        "shifts": {
            "source_shift": shifts["source_shift"],
            "effort_shift": shifts["effort_shift"],
            "resonance_shift": shifts["resonance_shift"],
            "register_shift": shifts["register_shift"],
        },
        # Public context schema (outside episode)
        "pre_context": pre,
        "during_context": during,
        "post_context": post,
        # deprecated aliases kept for one release (point to real pre/post)
        "before_context": pre,
        "after_context": post,
    }


def _core_evidence_span_from_members(members: list[dict[str, Any]], ep: dict[str, Any]) -> dict[str, Any]:
    """
    Phrase episodes may merge many windows; core span is the strongest/shortest transition.
    Always <= parent phrase duration.
    """
    if not members:
        start = float(ep.get("start_sec") or 0)
        end = float(ep.get("end_sec") or start)
        return {
            "start_sec": start,
            "end_sec": end,
            "duration_sec": max(0.0, end - start),
            "source": "episode",
        }
    scored = []
    for m in members:
        s = float(m.get("start_sec") or 0)
        e = float(m.get("end_sec") or s)
        dur = max(1e-3, e - s)
        jump = abs(float(m.get("f0_jump_cents") or 0))
        # Prefer high F0 jump and short duration
        scored.append((jump, -dur, s, e, m))
    scored.sort(reverse=True)
    _j, _d, s, e, best = scored[0]
    parent_s = float(ep.get("start_sec") or s)
    parent_e = float(ep.get("end_sec") or e)
    # Clamp inside parent
    s = max(parent_s, min(s, parent_e))
    e = max(s, min(e, parent_e))
    return {
        "start_sec": s,
        "end_sec": e,
        "duration_sec": max(0.0, e - s),
        "f0_jump_cents": best.get("f0_jump_cents"),
        "source": "strongest_member",
        "n_core_events": len(members),
    }


def finalize_episode(
    ep: dict[str, Any],
    *,
    all_segments: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    members = ep.get("members") or [ep]
    start = float(ep.get("start_sec") or 0)
    end = float(ep.get("end_sec") or start)
    all_segments = all_segments or []

    pre_segs = select_pre_context(all_segments, episode_start=start) if all_segments else []
    post_segs = select_post_context(all_segments, episode_end=end) if all_segments else []

    acoustic = _acoustic_phases(members, start, end)
    if acoustic:
        phases = acoustic
        phase_method = "ACOUSTIC"
        phase_confidence = acoustic.get("phase_confidence") or "medium"
    else:
        phases = _provisional_phases(start, end)
        phase_method = "PROVISIONAL"
        phase_confidence = "low"

    ep_type = ep.get("type") or "HIGH_NOTE"
    feature_matrix = build_feature_matrix(members, pre_segs, post_segs, episode_type=ep_type)
    e24_d = (feature_matrix.get("resonance") or {}).get("energy_2_4k_delta")
    shifts = feature_matrix.get("shifts") or {}
    cause_hint = classify_cause_hint(shifts, e24_delta=e24_d)
    core = _core_evidence_span_from_members(members, ep)
    core_events = [
        {
            "start_sec": float(m.get("start_sec") or 0),
            "end_sec": float(m.get("end_sec") or 0),
            "f0_jump_cents": m.get("f0_jump_cents"),
            "evidence": m.get("evidence"),
        }
        for m in members
    ]

    return {
        "episode_id": ep.get("episode_id") or f"{ep_type}_{start:.1f}_{end:.1f}",
        "type": ep_type,
        "start_sec": start,
        "end_sec": end,
        "phrase_span": {"start_sec": start, "end_sec": end},
        "core_evidence_span": core,
        "core_events": core_events,
        "phases": {k: v for k, v in phases.items() if k not in ("phase_method", "phase_confidence")},
        "phase_method": phase_method,
        "phase_confidence": phase_confidence,
        "provisional_partition": phase_method == "PROVISIONAL",
        "feature_matrix": feature_matrix,
        "pre_context": feature_matrix.get("pre_context"),
        "during_context": feature_matrix.get("during_context"),
        "post_context": feature_matrix.get("post_context"),
        "context_quality": {
            "pre_available": bool(pre_segs),
            "post_available": bool(post_segs),
            "confidence": (
                "high"
                if pre_segs and post_segs
                else ("medium" if pre_segs or post_segs else "low")
            ),
        },
        "pre_context_segments": [
            {"start_sec": s.get("start_sec"), "end_sec": s.get("end_sec")} for s in pre_segs
        ],
        "during_segments": [
            {"start_sec": m.get("start_sec"), "end_sec": m.get("end_sec")} for m in members
        ],
        "post_context_segments": [
            {"start_sec": s.get("start_sec"), "end_sec": s.get("end_sec")} for s in post_segs
        ],
        "cause_hint": cause_hint,
        "concern": bool(ep.get("concern")),
        "conclusion": ep.get("conclusion")
        or (members[-1].get("conclusion") if members else ""),
        "n_merged_windows": len(members),
        "members": members,
        "validity": ep.get("validity") or (members[0].get("validity") if members else {}),
    }


def build_typed_episodes(
    raw_events: list[dict[str, Any]],
    *,
    episode_type: str,
    all_segments: Optional[list[dict[str, Any]]] = None,
    gap_sec: float = 0.75,
) -> list[dict[str, Any]]:
    tagged = [{**e, "type": episode_type} for e in raw_events]
    merged = merge_overlapping(tagged, gap_sec=gap_sec)
    return [finalize_episode(ep, all_segments=all_segments or []) for ep in merged]


def build_high_note_episodes(
    raw_events: list[dict[str, Any]],
    all_segments: Optional[list[dict[str, Any]]] = None,
) -> list[dict[str, Any]]:
    return build_typed_episodes(
        raw_events, episode_type="HIGH_NOTE", all_segments=all_segments, gap_sec=0.75
    )


def build_register_episodes(
    events: list[dict[str, Any]],
    all_segments: Optional[list[dict[str, Any]]] = None,
) -> list[dict[str, Any]]:
    return build_typed_episodes(
        events, episode_type="REGISTER_TRANSITION", all_segments=all_segments, gap_sec=0.5
    )


def build_generic_episodes_from_segments(
    segments: list[dict[str, Any]],
    *,
    episode_type: str,
    predicate,
    all_segments: Optional[list[dict[str, Any]]] = None,
    gap_sec: float = 0.6,
) -> list[dict[str, Any]]:
    """Turn matching segments into localized episodes for coachable issues."""
    windows = []
    for s in segments:
        if not _episode_segment_ok(s, episode_type):
            continue
        if predicate(s):
            windows.append(
                {
                    "start_sec": s["start_sec"],
                    "end_sec": s["end_sec"],
                    "type": episode_type,
                    "concern": True,
                    "observations": s.get("observations"),
                    "level2_proxies": s.get("level2_proxies"),
                    "periodicity": (s.get("observations") or {}).get("periodicity_primary_db"),
                    "validity": s.get("vocal_evidence"),
                    "leakage_like": episode_type == "AIR_LEAKAGE",
                    "roughness": episode_type == "ROUGHNESS",
                    "effort_during": "elevated" if episode_type == "GENERAL_EFFORT" else None,
                    "contact_profile_during": None,
                }
            )
    return build_typed_episodes(
        windows, episode_type=episode_type, all_segments=all_segments or segments, gap_sec=gap_sec
    )


def pick_focus_episodes(
    episodes: list[dict[str, Any]],
    *,
    best_self: Optional[dict[str, Any]] = None,
    max_primary: int = 2,
    max_secondary: int = 2,
) -> dict[str, Any]:
    primary = [e for e in episodes if e.get("concern")][:max_primary]
    secondary = [e for e in episodes if not e.get("concern")][:max_secondary]
    if not primary and episodes:
        primary = episodes[:1]
        secondary = episodes[1 : 1 + max_secondary]
    return {
        "primary": primary,
        "secondary": secondary,
        "best_self_reference": best_self,
    }


def find_best_self_reference(
    episodes: list[dict[str, Any]],
    *,
    target: Optional[dict[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    """Comparable same-type self-reference with meaningful effort improvement."""
    pool = [e for e in episodes if e.get("type") == ((target or {}).get("type") or "HIGH_NOTE")]
    if len(pool) < 2:
        return None

    def f0_proxy(e: dict[str, Any]) -> Optional[float]:
        ctx = e.get("during_context") or (e.get("feature_matrix") or {}).get("during_context") or {}
        if ctx.get("f0_hz"):
            return float(ctx["f0_hz"])
        f0s = []
        for m in e.get("members") or []:
            obs = m.get("observations") or {}
            if obs.get("f0_hz"):
                f0s.append(float(obs["f0_hz"]))
        return float(np.median(f0s)) if f0s else None

    def effort(e):
        return float(
            (((e.get("feature_matrix") or {}).get("effort") or {}).get("strain_like") or 0)
        )

    def period(e):
        return ((e.get("feature_matrix") or {}).get("regularity") or {}).get("periodicity")

    def rough(e):
        return bool(((e.get("feature_matrix") or {}).get("regularity") or {}).get("roughness"))

    def vocal_ok(e):
        v = (e.get("feature_matrix") or {}).get("validity") or e.get("validity") or {}
        return v.get("vocal_specific", True)

    worst = target or max(pool, key=effort)
    if not worst.get("concern") and effort(worst) < 0.4:
        # pick highest effort as compare target
        worst = max(pool, key=effort)

    candidates = []
    wf0 = f0_proxy(worst)
    for e in pool:
        if e is worst or e.get("episode_id") == worst.get("episode_id"):
            continue
        if not vocal_ok(e):
            continue
        if effort(e) >= effort(worst) - cfg.BEST_SELF_MIN_EFFORT_DELTA:
            continue
        bf0 = f0_proxy(e)
        if bf0 and wf0 and abs(1200 * np.log2(bf0 / wf0)) > 350:
            continue
        bp, wp = period(e), period(worst)
        if bp is not None and wp is not None and bp < wp:
            continue
        if rough(e) and not rough(worst):
            continue
        candidates.append(e)

    if not candidates:
        return None
    best = min(candidates, key=effort)
    if effort(worst) - effort(best) < cfg.BEST_SELF_MIN_EFFORT_DELTA:
        return None

    return {
        **best,
        "role": "BEST_SELF_REFERENCE",
        "compare_against": worst.get("episode_id"),
        "coaching_hint": (
            f"{best['start_sec']:.0f}초 구간의 느낌과 비슷하게 "
            f"{worst['start_sec']:.0f}초 구간을 접근해보세요."
        ),
    }
