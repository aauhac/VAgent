"""Passaggio / bridge — global continuity vs local register events (v1.2)."""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from . import config as cfg


def _continuity(vals: list[Optional[float]], *, relative: bool = False) -> Optional[float]:
    clean = [float(v) for v in vals if v is not None]
    if len(clean) < 2:
        return None
    diffs = np.abs(np.diff(clean))
    if relative:
        scale = max(abs(float(np.median(clean))), 1e-6)
        diffs = diffs / scale
    return float(np.clip(1.0 - float(np.median(diffs)), 0.0, 1.0))


def _register_sufficiency(
    register_dim: dict[str, Any],
    criteria_matrix: Optional[list[dict[str, Any]]],
) -> str:
    if criteria_matrix:
        for row in criteria_matrix:
            if row.get("dimension_id") == "register_configuration":
                return (row.get("measurement_sufficiency") or "UNAVAILABLE").upper()
    conf = (register_dim.get("confidence_label") or "").lower()
    status = (register_dim.get("status") or "").upper()
    if status in ("UNKNOWN", "UNAVAILABLE") or conf == "low":
        return "INSUFFICIENT"
    if conf == "medium":
        return "PARTIAL"
    if conf == "high":
        return "SUFFICIENT"
    return "PARTIAL"


def detect_transition_opportunities(
    segments: list[dict[str, Any]],
    hc_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Candidate passaggio opportunities from F0 / source movement — not every high note.
    """
    by_t = sorted(
        [
            (float(r.get("start_sec") or 0), r, s)
            for r, s in zip(hc_rows, segments)
            if r.get("start_sec") is not None
        ],
        key=lambda x: x[0],
    )
    opps: list[dict[str, Any]] = []
    for i in range(1, len(by_t)):
        t0, r0, s0 = by_t[i - 1]
        t1, r1, s1 = by_t[i]
        f0_0 = r0.get("f0_hz") or (s0.get("observations") or {}).get("f0_hz")
        f0_1 = r1.get("f0_hz") or (s1.get("observations") or {}).get("f0_hz")
        if not f0_0 or not f0_1:
            continue
        cents = abs(1200.0 * np.log2(max(float(f0_1), 1.0) / max(float(f0_0), 1.0)))
        idx0 = r0.get("head_chest_index")
        idx1 = r1.get("head_chest_index")
        idx_jump = (
            abs(float(idx1) - float(idx0)) if idx0 is not None and idx1 is not None else None
        )
        band_cross = (r0.get("pitch_band") != r1.get("pitch_band")) and r0.get(
            "pitch_band"
        ) in (
            "low",
            "mid",
            "high",
        )
        # Opportunity: meaningful F0 move or band cross with source movement
        if cents < 180 and not band_cross:
            continue
        if cents < 350 and (idx_jump is None or idx_jump < 0.12) and not band_cross:
            continue
        opps.append(
            {
                "start_sec": t0,
                "end_sec": float(r1.get("end_sec") or t1),
                "f0_jump_cents": round(float(cents), 1),
                "index_jump": round(float(idx_jump), 3) if idx_jump is not None else None,
                "band_cross": bool(band_cross),
            }
        )
    return opps


def classify_local_events(
    *,
    hc_rows: list[dict[str, Any]],
    bridge_score: Optional[float],
    register_dim: dict[str, Any],
    episodes: list[dict[str, Any]],
    opportunities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    usable = [r for r in hc_rows if r.get("head_chest_index") is not None]
    usable.sort(key=lambda r: float(r.get("start_sec") or 0))

    # Local chest-pull: high-band chest-like streak
    high = [r for r in usable if r.get("pitch_band") == "high"]
    if high:
        chestish = [r for r in high if float(r["head_chest_index"]) <= 0.40]
        if len(chestish) >= 1 and len(chestish) <= max(1, len(high) // 2 + 1):
            # Local only if not dominating all high notes
            r = chestish[0]
            events.append(
                {
                    "type": "LOCAL_CHEST_PULL",
                    "start_sec": r.get("start_sec"),
                    "end_sec": r.get("end_sec"),
                    "severity": "medium" if len(chestish) == 1 else "high",
                    "confidence": "medium",
                }
            )
        elif len(chestish) > len(high) * 0.6 and high:
            # Widespread high chest — still emit local markers per cluster
            r0, r1 = high[0], high[-1]
            events.append(
                {
                    "type": "LOCAL_CHEST_PULL",
                    "start_sec": r0.get("start_sec"),
                    "end_sec": r1.get("end_sec"),
                    "severity": "high",
                    "confidence": "medium",
                    "prevalence_note": "high_band_chest_persistent",
                }
            )

    # Timeline block chest spike (one bucket much chestier)
    if usable:
        t0 = float(usable[0].get("start_sec") or 0)
        t1 = max(float(r.get("end_sec") or 0) for r in usable)
        if t1 > t0:
            bucket_stats = []
            for i in range(4):
                a = t0 + (t1 - t0) * i / 4
                b = t0 + (t1 - t0) * (i + 1) / 4
                bucket = [
                    r
                    for r in usable
                    if a <= float(r.get("start_sec") or 0) < b
                    or (i == 3 and float(r.get("start_sec") or 0) <= b)
                ]
                if not bucket:
                    continue
                med = float(np.median([r["head_chest_index"] for r in bucket]))
                bucket_stats.append((a, b, med, len(bucket)))
            if len(bucket_stats) >= 3:
                meds = [m for _, _, m, _ in bucket_stats]
                global_med = float(np.median(meds))
                for a, b, m, n in bucket_stats:
                    if m <= global_med - 0.12 and m <= 0.40 and n >= 2:
                        events.append(
                            {
                                "type": "LOCAL_CHEST_PULL",
                                "start_sec": round(a, 2),
                                "end_sec": round(b, 2),
                                "severity": "medium",
                                "confidence": "medium",
                                "source": "timeline_spike",
                            }
                        )

    mid = [r for r in usable if r.get("pitch_band") == "mid"]
    if mid:
        mid_idx = float(np.median([r["head_chest_index"] for r in mid]))
        if mid_idx >= 0.62:
            events.append(
                {
                    "type": "LOCAL_EARLY_HEAD_SHIFT",
                    "start_sec": mid[0].get("start_sec"),
                    "end_sec": mid[-1].get("end_sec"),
                    "severity": "medium",
                    "confidence": "medium",
                }
            )

    concern = [e for e in episodes if e.get("type") == "REGISTER_TRANSITION" and e.get("concern")]
    for ep in concern:
        core = ep.get("core_evidence_span") or {
            "start_sec": ep.get("start_sec"),
            "end_sec": ep.get("end_sec"),
        }
        events.append(
            {
                "type": "LOCAL_ABRUPT_BREAK",
                "start_sec": core.get("start_sec"),
                "end_sec": core.get("end_sec"),
                "severity": "high" if ep.get("concern") else "medium",
                "confidence": "medium",
            }
        )

    # Effort spikes from episodes
    for ep in episodes:
        if ep.get("type") in ("HIGH_NOTE", "GENERAL_EFFORT") and ep.get("concern"):
            events.append(
                {
                    "type": "LOCAL_EFFORT_SPIKE",
                    "start_sec": ep.get("start_sec"),
                    "end_sec": ep.get("end_sec"),
                    "severity": "medium",
                    "confidence": "medium",
                }
            )

    # Deduplicate overlapping same-type
    deduped: list[dict[str, Any]] = []
    for ev in events:
        overlap = False
        for d in deduped:
            if d["type"] != ev["type"]:
                continue
            if d.get("start_sec") is None or ev.get("start_sec") is None:
                continue
            if abs(float(d["start_sec"]) - float(ev["start_sec"])) < 2.0:
                overlap = True
                break
        if not overlap:
            deduped.append(ev)
    return deduped


def register_split_global_eligibility(
    *,
    bridge_score: Optional[float],
    register_dim: dict[str, Any],
    criteria_matrix: Optional[list[dict[str, Any]]],
    transition_events: list[dict[str, Any]],
    concern_episodes: list[dict[str, Any]],
    opportunities: list[dict[str, Any]],
    local_events: list[dict[str, Any]],
    components: dict[str, Any],
    vocal_specific_ok: bool,
    roughness_dominant: bool,
    breathiness_dominant: bool,
) -> dict[str, Any]:
    sufficiency = _register_sufficiency(register_dim, criteria_matrix)
    allowed_suf = sufficiency in ("SUFFICIENT", "PARTIAL")
    n_opp = len(opportunities)
    n_breaks = sum(1 for e in local_events if e.get("type") == "LOCAL_ABRUPT_BREAK")
    n_unstable = sum(1 for e in local_events if e.get("type") == "LOCAL_UNSTABLE_BRIDGE")
    n_pull = sum(1 for e in local_events if e.get("type") == "LOCAL_CHEST_PULL")
    break_like = n_breaks + n_unstable
    # Chest pulls alone do NOT count as register splits
    prevalence = break_like / max(n_opp, 1) if n_opp else 0.0

    f0_cont = components.get("f0_continuity")
    idx_cont = components.get("index_continuity")
    f0_disrupted = f0_cont is not None and float(f0_cont) < 0.55
    source_disrupted = idx_cont is not None and float(idx_cont) < 0.55
    score_poor = bridge_score is not None and float(bridge_score) <= cfg.BRIDGE_POOR_MAX
    repeated = break_like >= cfg.REGISTER_SPLIT_MIN_EVENTS
    enough_opp = n_opp >= cfg.REGISTER_SPLIT_MIN_OPPORTUNITIES
    prev_ok = prevalence >= cfg.REGISTER_SPLIT_MIN_PREVALENCE

    contamination_ok = (
        vocal_specific_ok and not roughness_dominant and not breathiness_dominant
    )
    eligible = bool(
        allowed_suf
        and enough_opp
        and repeated
        and prev_ok
        and f0_disrupted
        and source_disrupted
        and contamination_ok
        and score_poor
    )

    reasons = []
    if not allowed_suf:
        reasons.append("register_measurement_insufficient")
    if not enough_opp:
        reasons.append("insufficient_transition_opportunities")
    if not repeated:
        reasons.append("insufficient_repeated_breaks")
    if not prev_ok:
        reasons.append("break_prevalence_too_low")
    if not f0_disrupted:
        reasons.append("f0_continuity_not_disrupted")
    if not source_disrupted:
        reasons.append("source_continuity_not_disrupted")
    if roughness_dominant:
        reasons.append("explained_by_roughness")
    if breathiness_dominant:
        reasons.append("explained_by_breathiness")
    if not vocal_specific_ok:
        reasons.append("vocal_specificity_weak")
    if not score_poor:
        reasons.append("bridge_score_not_poor")
    if n_pull >= 1 and break_like == 0:
        reasons.append("chest_pull_only_not_split")

    return {
        "eligible": eligible,
        "sufficiency": sufficiency,
        "n_transition_events": len(transition_events),
        "n_concern_episodes": len(concern_episodes),
        "n_opportunities": n_opp,
        "n_local_breaks": n_breaks,
        "n_local_chest_pulls": n_pull,
        "break_prevalence": round(prevalence, 3),
        "isolated_event_only": break_like == 1,
        "f0_disrupted": f0_disrupted,
        "source_disrupted": source_disrupted,
        "reasons_blocked": reasons,
    }


def compute_bridge(
    *,
    segments: list[dict[str, Any]],
    hc_rows: list[dict[str, Any]],
    register_dim: Optional[dict[str, Any]] = None,
    episodes: Optional[list[dict[str, Any]]] = None,
    criteria_matrix: Optional[list[dict[str, Any]]] = None,
    dimensions: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    register_dim = register_dim or {}
    episodes = episodes or []
    dimensions = dimensions or {}
    events = (register_dim.get("profile") or {}).get("events") or []
    reg_eps = [e for e in episodes if e.get("type") == "REGISTER_TRANSITION"]
    concern_reg = [e for e in reg_eps if e.get("concern")]

    usable = [r for r in hc_rows if r.get("head_chest_index") is not None]
    usable.sort(key=lambda r: float(r.get("start_sec") or 0))

    idx_cont = _continuity([r.get("head_chest_index") for r in usable], relative=False)
    if idx_cont is not None and len(usable) >= 2:
        idxs = [float(r["head_chest_index"]) for r in usable]
        jump = float(np.max(np.abs(np.diff(idxs))))
        idx_cont = float(np.clip(1.0 - jump / 0.55, 0.0, 1.0))

    f0s, periods, rmses = [], [], []
    vocal_ok = vocal_n = 0
    for s in segments:
        ve = s.get("vocal_evidence") or {}
        vocal_n += 1
        if ve.get("vocal_specific") or s.get("valid"):
            vocal_ok += 1
        if not s.get("valid") and not ve.get("vocal_specific"):
            continue
        obs = s.get("observations") or {}
        if obs.get("f0_hz"):
            f0s.append(float(obs["f0_hz"]))
        if obs.get("periodicity_primary_db") is not None:
            periods.append(float(obs["periodicity_primary_db"]))
        if obs.get("rms") is not None:
            rmses.append(float(obs["rms"]))

    f0_cont = None
    if len(f0s) >= 3:
        logf = np.log2(np.maximum(f0s, 1.0))
        jump = float(np.max(np.abs(np.diff(logf))) * 1200)
        f0_cont = float(np.clip(1.0 - jump / 800.0, 0.0, 1.0))

    per_cont = _continuity(periods, relative=True)
    rms_cont = _continuity(rmses, relative=True)
    abrupt = 0.0
    if events:
        abrupt = min(1.0, 0.15 * len(events))
    if concern_reg:
        abrupt = max(abrupt, min(1.0, 0.25 * len(concern_reg)))

    parts = [x for x in (idx_cont, f0_cont, per_cont, rms_cont) if x is not None]
    sufficiency = _register_sufficiency(register_dim, criteria_matrix)
    opportunities = detect_transition_opportunities(segments, hc_rows)

    if not parts:
        return {
            "type": "UNDETERMINED",
            "score": None,
            "available": False,
            "passaggio_time": None,
            "core_span": None,
            "register_sufficiency": sufficiency,
            "split_eligibility": {"eligible": False, "reasons_blocked": ["no_continuity_parts"]},
            "local_register_events": [],
            "transition_opportunities": opportunities,
            "global_vs_local": {"global_type_hint": None, "isolated_breaks": []},
        }

    score = float(np.clip(float(np.mean(parts)) * (1.0 - 0.35 * abrupt), 0.0, 1.0))
    core = None
    passaggio_time = None
    for ep in concern_reg or reg_eps:
        c = ep.get("core_evidence_span") or {
            "start_sec": ep.get("start_sec"),
            "end_sec": ep.get("end_sec"),
        }
        if c.get("start_sec") is not None:
            core = c
            passaggio_time = float(c["start_sec"])
            break

    components = {
        "index_continuity": idx_cont,
        "f0_continuity": f0_cont,
        "periodicity_continuity": per_cont,
        "intensity_continuity": rms_cont,
        "abruptness": abrupt,
    }

    local_events = classify_local_events(
        hc_rows=hc_rows,
        bridge_score=score,
        register_dim=register_dim,
        episodes=episodes,
        opportunities=opportunities,
    )

    # Roughness / breathiness dominant flags from dimensions
    rough_st = ((dimensions.get("phonation_regularity") or {}).get("status") or "").upper()
    leak_st = ((dimensions.get("air_leakage_breathiness") or {}).get("status") or "").upper()
    roughness_dominant = rough_st in ("REPEATED_IRREGULAR",)
    breathiness_dominant = leak_st in ("HIGH", "MODERATE") and not any(
        family_ok
        for family_ok in [True]  # placeholder — breathiness alone shouldn't block if source ok
    )
    # Only treat as "explained by breathiness" when breathiness high AND register events weak
    breathiness_dominant = leak_st == "HIGH" and len(concern_reg) == 0

    vocal_specific_ok = (vocal_ok / max(vocal_n, 1)) >= 0.35
    split_gate = register_split_global_eligibility(
        bridge_score=score,
        register_dim=register_dim,
        criteria_matrix=criteria_matrix,
        transition_events=list(events),
        concern_episodes=concern_reg,
        opportunities=opportunities,
        local_events=local_events,
        components=components,
        vocal_specific_ok=vocal_specific_ok,
        roughness_dominant=roughness_dominant,
        breathiness_dominant=breathiness_dominant,
    )

    confident_ok = sufficiency in ("SUFFICIENT", "PARTIAL")
    high_rows = [r for r in usable if r.get("pitch_band") == "high"]
    high_idx = (
        float(np.median([r["head_chest_index"] for r in high_rows])) if high_rows else None
    )
    mid_rows = [r for r in usable if r.get("pitch_band") == "mid"]
    mid_idx = (
        float(np.median([r["head_chest_index"] for r in mid_rows])) if mid_rows else None
    )

    # Global bridge type — CHEST_PULL is NOT a global type; use local events
    btype = "UNDETERMINED"
    if not confident_ok:
        btype = "UNDETERMINED"
    elif score >= cfg.BRIDGE_SMOOTH_MIN:
        btype = "SMOOTH_BRIDGE"
    elif split_gate["eligible"]:
        btype = "ABRUPT_REGISTER_BREAK"
    elif score <= cfg.BRIDGE_POOR_MAX:
        btype = "UNSTABLE_BRIDGE" if sufficiency == "SUFFICIENT" else "UNDETERMINED"
    else:
        btype = "UNSTABLE_BRIDGE"

    # If mostly smooth opportunities with few breaks → prefer SMOOTH/UNSTABLE not ABRUPT
    n_opp = len(opportunities)
    n_break = split_gate.get("n_local_breaks") or 0
    if n_opp >= 3 and n_break <= 1 and score >= 0.45:
        if btype == "ABRUPT_REGISTER_BREAK":
            btype = "UNSTABLE_BRIDGE"
        elif score >= cfg.BRIDGE_SMOOTH_MIN * 0.9:
            btype = "SMOOTH_BRIDGE"

    # Annotate local unstable if mid global score
    if btype == "UNSTABLE_BRIDGE" and not any(
        e["type"] == "LOCAL_UNSTABLE_BRIDGE" for e in local_events
    ):
        if core:
            local_events.append(
                {
                    "type": "LOCAL_UNSTABLE_BRIDGE",
                    "start_sec": core.get("start_sec"),
                    "end_sec": core.get("end_sec"),
                    "severity": "low",
                    "confidence": "low",
                }
            )

    return {
        "type": btype,
        "score": round(score, 3),
        "available": True,
        "passaggio_time": passaggio_time,
        "core_span": core,
        "components": components,
        "high_band_index": high_idx,
        "mid_band_index": mid_idx,
        "register_sufficiency": sufficiency,
        "split_eligibility": split_gate,
        "local_register_events": local_events,
        "transition_opportunities": opportunities,
        "n_transition_opportunities": n_opp,
        "break_prevalence": split_gate.get("break_prevalence"),
        "global_vs_local": {
            "global_type_hint": btype,
            "local_events": local_events,
            "isolated_breaks": [
                e for e in local_events if e.get("type") == "LOCAL_ABRUPT_BREAK"
            ][:3],
        },
    }
