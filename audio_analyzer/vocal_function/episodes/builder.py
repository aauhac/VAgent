"""Episode builder — merge windows, acoustic/provisional phases, feature matrix."""

from __future__ import annotations

from typing import Any, Optional

import numpy as np


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
            episodes.append(_finalize(cur))
            cur = dict(w)
            cur["members"] = [w]
    episodes.append(_finalize(cur))
    return episodes


def _provisional_phases(start: float, end: float) -> dict[str, Any]:
    dur = max(1e-6, end - start)
    return {
        "ENTRY": {"start_sec": start, "end_sec": start + 0.2 * dur},
        "PEAK": {"start_sec": start + 0.2 * dur, "end_sec": start + 0.45 * dur},
        "SUSTAIN": {"start_sec": start + 0.45 * dur, "end_sec": start + 0.75 * dur},
        "EXIT": {"start_sec": start + 0.75 * dur, "end_sec": start + 0.9 * dur},
        "RECOVERY": {"start_sec": start + 0.9 * dur, "end_sec": end},
        "phase_method": "PROVISIONAL",
    }


def _acoustic_phases(members: list[dict[str, Any]], start: float, end: float) -> Optional[dict[str, Any]]:
    """Detect ENTRY/PEAK/SUSTAIN/EXIT/RECOVERY from member F0/intensity when possible."""
    if len(members) < 3:
        return None
    f0s = []
    rmss = []
    mids = []
    for m in members:
        obs = m.get("observations") or {}
        f0 = obs.get("f0_hz") or m.get("f0_hz")
        rms = obs.get("rms") if obs.get("rms") is not None else m.get("rms")
        mid = (float(m.get("start_sec") or 0) + float(m.get("end_sec") or 0)) / 2.0
        if f0:
            f0s.append(float(f0))
            mids.append(mid)
            rmss.append(float(rms) if rms is not None else 0.0)
    if len(f0s) < 3:
        return None
    peak_i = int(np.argmax(f0s))
    # ENTRY: from start to peak
    # SUSTAIN: near peak where |df0| small
    entry_end = mids[peak_i]
    # Find sustain: consecutive near peak_f0
    peak_f0 = f0s[peak_i]
    sustain_idxs = [i for i, f in enumerate(f0s) if abs(f - peak_f0) / peak_f0 < 0.03]
    if not sustain_idxs:
        return None
    sustain_start = mids[min(sustain_idxs)]
    sustain_end = mids[max(sustain_idxs)]
    # EXIT: after sustain to near end
    # RECOVERY: last member
    recovery_start = float(members[-1].get("start_sec") or end)
    phases = {
        "ENTRY": {"start_sec": start, "end_sec": min(entry_end, end)},
        "PEAK": {"start_sec": mids[peak_i], "end_sec": min(mids[peak_i] + 0.15, end)},
        "SUSTAIN": {"start_sec": sustain_start, "end_sec": sustain_end},
        "EXIT": {"start_sec": sustain_end, "end_sec": recovery_start},
        "RECOVERY": {"start_sec": recovery_start, "end_sec": end},
        "phase_method": "ACOUSTIC",
    }
    return phases


def _aggregate_features(members: list[dict[str, Any]]) -> dict[str, Any]:
    def _vals(path: list[str]):
        out = []
        for m in members:
            cur: Any = m
            for p in path:
                if not isinstance(cur, dict):
                    cur = None
                    break
                cur = cur.get(p)
            if cur is not None:
                try:
                    out.append(float(cur))
                except (TypeError, ValueError):
                    pass
        return out

    def _med(path: list[str]):
        v = _vals(path)
        return float(np.median(v)) if v else None

    firms = [1 if m.get("contact_profile_during") == "firmer_like" else 0 for m in members]
    efforts = [1 if m.get("effort_during") == "elevated" or m.get("concern") else 0 for m in members]
    periods = _vals(["periodicity"]) or _vals(["observations", "periodicity_primary_db"])
    naqs = _vals(["observations", "level2"])  # fallback below
    naqs = []
    oqs = []
    mfdrn = []
    h1s = []
    e24s = []
    cents = []
    onset_slopes = []
    for m in members:
        obs = m.get("observations") or {}
        src = ((m.get("level2_proxies") or {}).get("glottal_source") or {})
        if src.get("estimated_naq") is not None:
            naqs.append(float(src["estimated_naq"]))
        if src.get("estimated_oq_proxy") is not None:
            oqs.append(float(src["estimated_oq_proxy"]))
        if src.get("estimated_mfdr_norm_proxy") is not None:
            mfdrn.append(float(src["estimated_mfdr_norm_proxy"]))
        if obs.get("raw_h1_h2_proxy_db") is not None:
            h1s.append(float(obs["raw_h1_h2_proxy_db"]))
        if obs.get("energy_2_4k") is not None:
            e24s.append(float(obs["energy_2_4k"]))
        if obs.get("spectral_centroid_hz") is not None:
            cents.append(float(obs["spectral_centroid_hz"]))
        if obs.get("onset_slope_db_per_sec") is not None:
            onset_slopes.append(float(obs["onset_slope_db_per_sec"]))
        # also from window event fields
        if m.get("periodicity") is not None:
            periods.append(float(m["periodicity"]))

    n = max(1, len(members))
    mid = n // 2
    before_m = members[: max(1, mid)]
    during_m = members[max(0, mid - 1) : mid + 2] or members
    after_m = members[mid:]

    def _ctx(ms: list[dict[str, Any]]) -> dict[str, Any]:
        e24 = []
        bright = []
        period = []
        for m in ms:
            obs = m.get("observations") or {}
            if obs.get("energy_2_4k") is not None:
                e24.append(float(obs["energy_2_4k"]))
            if obs.get("spectral_centroid_hz") is not None:
                bright.append(float(obs["spectral_centroid_hz"]))
            p = m.get("periodicity")
            if p is None:
                p = obs.get("periodicity_primary_db")
            if p is not None:
                period.append(float(p))
        return {
            "energy_2_4k": float(np.median(e24)) if e24 else None,
            "spectral_centroid_hz": float(np.median(bright)) if bright else None,
            "periodicity": float(np.median(period)) if period else None,
            "mid_presence": (
                "낮은 편"
                if e24 and float(np.median(e24)) < 0.12
                else ("높은 편" if e24 and float(np.median(e24)) > 0.2 else "보통")
            )
            if e24
            else None,
        }

    before = _ctx(before_m)
    during = _ctx(during_m)
    after = _ctx(after_m)

    def _delta(a, b):
        if a is None or b is None:
            return None
        return float(b - a)

    return {
        "source": {
            "contact_firmness": float(np.mean(firms)) if firms else None,
            "air_leakage": None,
            "estimated_naq": float(np.median(naqs)) if naqs else None,
            "estimated_oq_proxy": float(np.median(oqs)) if oqs else None,
            "estimated_mfdr_norm_proxy": float(np.median(mfdrn)) if mfdrn else None,
            "h1_h2_proxy": float(np.median(h1s)) if h1s else None,
        },
        "effort": {
            "strain_like": float(np.mean(efforts)) if efforts else 0.0,
            "intensity_overshoot": float(np.mean(efforts)) if efforts else 0.0,
            "onset_hardening": float(np.median(onset_slopes)) if onset_slopes else None,
            "source_compression": float(np.mean(firms)) if firms else None,
            "persistence": float(np.mean(efforts[-2:]))
            if len(efforts) >= 2
            else float(np.mean(efforts) if efforts else 0),
        },
        "regularity": {
            "periodicity": float(np.median(periods)) if periods else None,
            "roughness": any(m.get("roughness") for m in members),
            "dropout": False,
        },
        "register": {
            "transition_strength": None,
            "source_shift": None,
            "f0_continuity": None,
        },
        "resonance": {
            "brightness_before": before.get("spectral_centroid_hz"),
            "brightness_during": during.get("spectral_centroid_hz"),
            "mid_presence_before": before.get("mid_presence"),
            "mid_presence_during": during.get("mid_presence"),
            "energy_2_4k_before": before.get("energy_2_4k"),
            "energy_2_4k_during": during.get("energy_2_4k"),
            "energy_2_4k_delta": _delta(before.get("energy_2_4k"), during.get("energy_2_4k")),
            "brightness_delta": _delta(
                before.get("spectral_centroid_hz"), during.get("spectral_centroid_hz")
            ),
            "spectral_centroid_delta": _delta(
                before.get("spectral_centroid_hz"), during.get("spectral_centroid_hz")
            ),
            "formant_confidence": None,
        },
        "onset": {
            "abruptness": float(np.median(onset_slopes)) if onset_slopes else None,
        },
        "recovery": {
            "fast": all(m.get("recovery_fast", True) for m in members),
            "returned_to_baseline": all(m.get("recovery_fast", True) for m in members),
        },
        "validity": {
            "vocal_specific": all(
                (m.get("validity") or {}).get("vocal_specific", True) for m in members
            ),
            "n_windows": len(members),
        },
        "before_context": before,
        "during_context": during,
        "after_context": after,
    }


def _finalize(ep: dict[str, Any]) -> dict[str, Any]:
    members = ep.get("members") or [ep]
    start = float(ep.get("start_sec") or 0)
    end = float(ep.get("end_sec") or start)
    acoustic = _acoustic_phases(members, start, end)
    if acoustic:
        phases = acoustic
        phase_method = "ACOUSTIC"
    else:
        phases = _provisional_phases(start, end)
        phase_method = "PROVISIONAL"
    feature_matrix = _aggregate_features(members)
    # source vs resonance disambiguation hint
    src_shift = (
        (feature_matrix.get("source") or {}).get("estimated_naq") is not None
        or (feature_matrix.get("source") or {}).get("h1_h2_proxy") is not None
    )
    res_delta = (feature_matrix.get("resonance") or {}).get("energy_2_4k_delta")
    res_change = res_delta is not None and abs(res_delta) >= 0.05
    effort_high = ((feature_matrix.get("effort") or {}).get("strain_like") or 0) >= 0.5
    if effort_high and not res_change:
        cause_hint = "SOURCE_EFFORT"
    elif res_change and not effort_high:
        cause_hint = "RESONANCE"
    elif res_change and effort_high:
        cause_hint = "MIXED"
    else:
        cause_hint = "UNCLEAR"

    return {
        "episode_id": f"{ep.get('type', 'EP')}_{start:.1f}_{end:.1f}",
        "type": ep.get("type") or "HIGH_NOTE",
        "start_sec": start,
        "end_sec": end,
        "phases": {k: v for k, v in phases.items() if k != "phase_method"},
        "phase_method": phase_method,
        "provisional_partition": phase_method == "PROVISIONAL",
        "feature_matrix": feature_matrix,
        "cause_hint": cause_hint,
        "concern": bool(ep.get("concern")),
        "conclusion": ep.get("conclusion")
        or (members[-1].get("conclusion") if members else ""),
        "n_merged_windows": len(members),
        "members": [
            {
                "start_sec": m.get("start_sec"),
                "end_sec": m.get("end_sec"),
                "observations": m.get("observations"),
                "level2_proxies": m.get("level2_proxies"),
                "periodicity": m.get("periodicity"),
                "contact_profile_during": m.get("contact_profile_during"),
                "effort_during": m.get("effort_during"),
                "roughness": m.get("roughness"),
                "recovery_fast": m.get("recovery_fast"),
                "validity": m.get("validity"),
            }
            for m in members
        ],
    }


def build_high_note_episodes(raw_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tagged = [{**e, "type": "HIGH_NOTE"} for e in raw_events]
    return merge_overlapping(tagged, gap_sec=0.75)


def build_register_episodes(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tagged = [{**e, "type": "REGISTER_TRANSITION"} for e in events]
    return merge_overlapping(tagged, gap_sec=0.5)


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
) -> Optional[dict[str, Any]]:
    """Comparable high-note self-reference (similar F0 band, better effort/periodicity)."""
    if len(episodes) < 2:
        return None
    high = [e for e in episodes if e.get("type") == "HIGH_NOTE"]
    if len(high) < 2:
        return None

    def f0_proxy(e: dict[str, Any]) -> Optional[float]:
        # use member median f0 if present
        f0s = []
        for m in e.get("members") or []:
            obs = m.get("observations") or {}
            if obs.get("f0_hz"):
                f0s.append(float(obs["f0_hz"]))
        return float(np.median(f0s)) if f0s else None

    scored = []
    for e in high:
        fm = e.get("feature_matrix") or {}
        effort = ((fm.get("effort") or {}).get("strain_like") or 0)
        period = ((fm.get("regularity") or {}).get("periodicity") or 0) or 0
        rough = bool((fm.get("regularity") or {}).get("roughness"))
        scored.append((effort, -period, rough, e))
    # worst = highest effort
    scored.sort(key=lambda t: (t[0], t[1]))
    best = scored[0][3]
    worst = scored[-1][3]
    if best is worst or not worst.get("concern"):
        # still allow if best clearly better effort
        if scored[0][0] >= scored[-1][0]:
            return None
    bf0, wf0 = f0_proxy(best), f0_proxy(worst)
    if bf0 and wf0:
        # reject mid vs high mismatch (~> 3 semitones)
        if abs(1200 * np.log2(bf0 / wf0)) > 350:
            return None
    bfm = best.get("feature_matrix") or {}
    wfm = worst.get("feature_matrix") or {}
    b_period = ((bfm.get("regularity") or {}).get("periodicity") or 0) or 0
    w_period = ((wfm.get("regularity") or {}).get("periodicity") or 0) or 0
    if b_period < w_period:
        return None
    if (bfm.get("regularity") or {}).get("roughness") and not (
        wfm.get("regularity") or {}
    ).get("roughness"):
        return None
    return {
        **best,
        "role": "BEST_SELF_REFERENCE",
        "compare_against": worst.get("episode_id"),
        "coaching_hint": (
            f"{best['start_sec']:.0f}초 구간의 느낌과 비슷하게 "
            f"{worst['start_sec']:.0f}초 고음을 접근해보세요."
        ),
    }
