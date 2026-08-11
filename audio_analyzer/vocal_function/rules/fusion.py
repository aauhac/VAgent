"""Functional-state fusion rules (LEVEL 3). Firm ≠ strain."""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from audio_analyzer.vocal_function import config as cfg
from audio_analyzer.vocal_function.evidence.families import (
    contact_direction_score,
    contact_evidence_packet,
    firmer_like,
    gif_usable,
    leakage_like,
    lighter_like,
)
from audio_analyzer.vocal_function.evidence.graph import evidence_node
from audio_analyzer.vocal_function.validity import dim_valid


def _prevalence(n_hit: int, n_valid: int) -> str:
    if n_valid <= 0 or n_hit <= 0:
        return "not_observed"
    r = n_hit / n_valid
    if r < 0.1:
        return "rare"
    if r < cfg.PREVALENCE_OCCASIONAL:
        return "occasional"
    if r < cfg.PREVALENCE_REPEATED:
        return "repeated"
    return "dominant"


def _contact_evaluable(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [s for s in segments if dim_valid(s, "glottal_contact")]


def _effort_evaluable(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [s for s in segments if dim_valid(s, "effort")]


def fuse_contact(
    segments: list[dict[str, Any]],
    *,
    baseline_obs: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Contact continuum using dimension-specific validity.

    GIF is strong evidence, not an absolute gate. Multi-family fallback
    (harmonic + spectral/temporal) may yield an estimate with capped confidence.
    No fake midpoint when directional evidence is absent.
    """
    valid = _contact_evaluable(segments)
    if len(valid) < cfg.MIN_SEGMENTS_GLOBAL:
        return _dim(
            "glottal_contact_profile",
            status="UNKNOWN",
            continuum=None,
            summary="성대 접촉 관련 경향을 신뢰도 있게 추정하지 못했어요.",
            meaning="",
            cannot="실제 성문 폐쇄·해부학적 접촉을 측정하지 않습니다.",
            evidence=[],
            valid=valid,
        )

    packets = [contact_evidence_packet(s, baseline_obs) for s in valid]
    scored = [
        (s, p, contact_direction_score(s, baseline_obs))
        for s, p in zip(valid, packets)
    ]
    scored = [(s, p, sc) for s, p, sc in scored if sc is not None]
    light = [s for s, _p, sc in scored if sc is not None and sc < 0.4]
    firm = [s for s, _p, sc in scored if sc is not None and sc > 0.6]
    # Prefer mean of segment scores when available; else firm/(light+firm)
    score = None
    if scored:
        score = float(np.mean([sc for _s, _p, sc in scored]))
    elif light or firm:
        score = float(len(firm) / max(1, len(light) + len(firm)))

    status = "OBSERVED" if score is not None else "UNKNOWN"
    if score is None and len(valid) >= cfg.MIN_SEGMENTS_GLOBAL:
        status = "AMBIGUOUS"

    gif_ok = sum(1 for s in valid if gif_usable(s))
    fallback_n = sum(1 for p in packets if p.get("fallback_supported"))
    family_counts = [int(p.get("family_count") or 0) for p in packets]
    evidence_mass = float(np.mean([float(p.get("evidence_mass") or 0) for p in packets])) if packets else 0.0
    agreements = [p.get("family_agreement") for p in packets if p.get("family_agreement") is not None]
    family_agreement = (
        (sum(1 for a in agreements if a) / len(agreements)) if agreements else None
    )

    # Confidence: GIF + families → medium; fallback-only → low (never inflate)
    conf = "low"
    lock_conf = False
    if score is not None and gif_ok >= 2 and (np.mean(family_counts) if family_counts else 0) >= 2:
        conf = "medium"
    elif score is not None and gif_ok >= 1:
        conf = "medium"
    elif score is not None and fallback_n >= cfg.MIN_SEGMENTS_GLOBAL:
        conf = "low"
        lock_conf = True
    elif score is None and gif_ok == 0:
        status = "UNKNOWN"

    graph = []
    if firm:
        s0 = firm[0]
        graph.append(
            evidence_node(
                observation_ids=["estimated_naq", "raw_h1_h2_proxy_db", "energy_2_4k"],
                families=["glottal_flow", "harmonic", "spectral"],
                hypothesis="firmer_contact_related_source_pattern",
                alternatives=[
                    "vowel/formant alignment boosting upper harmonics",
                    "microphone EQ / mastering",
                    "separation artifact",
                ],
                confidence_cap=conf,
                grade="B",
                time_range=(s0["start_sec"], s0["end_sec"]),
                rule_id="CONTACT_FIRM_V27",
            )
        )

    label = "중간"
    if score is not None:
        if score < 0.35:
            label = "가벼움 쪽"
        elif score > 0.65:
            label = "단단함 쪽"

    return _dim(
        "glottal_contact_profile",
        status=status,
        continuum=score,
        continuum_label=label,
        summary=f"접촉 관련 경향: {label}" if score is not None else "판단 어려움",
        meaning=(
            "상대적으로 더 단단한 접촉과 일치할 수 있는 source pattern이 관찰됐어요."
            if score and score > 0.65
            else (
                "상대적으로 가벼운 성대 접촉과 일치할 수 있는 source pattern이 관찰됐어요."
                if score is not None and score < 0.35
                else "중간 정도의 접촉 관련 경향으로 해석될 수 있어요."
            )
        ),
        cannot="실제 성대 두께·성문 폐쇄 기하학을 측정하지 않습니다.",
        evidence=graph,
        valid=valid,
        confidence_label=conf,
        lock_confidence=lock_conf,
        prevalence=_prevalence(max(len(light), len(firm)), len(valid)),
        profile={
            "lighter_segments": len(light),
            "firmer_segments": len(firm),
            "continuum_0_light_1_firm": score,
            "evidence_mass": round(evidence_mass, 3),
            "family_count": int(round(float(np.mean(family_counts)))) if family_counts else 0,
            "family_agreement": None if family_agreement is None else round(family_agreement, 3),
            "gif_supported": gif_ok > 0,
            "fallback_supported": fallback_n > 0,
            "gif_valid_segments": gif_ok,
            "fallback_segments": fallback_n,
            "good_bad": None,
        },
    )


def fuse_effort(
    segments: list[dict[str, Any]],
    *,
    baseline_obs: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Effort fusion (v2.8) — trajectory PRE→DURING→POST, not absolute loudness.

    Support-only (regularity + spectral) cannot produce moderate/high effort.
    """
    from audio_analyzer.vocal_function.evidence.effort_trajectory import (
        compute_effort_event_context,
    )

    valid = _effort_evaluable(segments)
    hits: list[dict[str, Any]] = []
    hit_packets: list[dict[str, Any]] = []
    contexts: list[dict[str, Any]] = []
    all_scores: list[float] = []

    for i, s in enumerate(valid):
        pre = valid[i - 1] if i > 0 else None
        post = valid[i + 1] if i + 1 < len(valid) else None
        ctx = compute_effort_event_context(
            s, pre=pre, post=post, baseline=baseline_obs
        )
        contexts.append(ctx)
        all_scores.append(float(ctx.get("final_score") or 0))
        if ctx.get("elevated"):
            hits.append(s)
            hit_packets.append(
                {
                    "effort_score": ctx.get("final_score"),
                    "families": {
                        **(ctx.get("core_families") or {}),
                        **(ctx.get("support_families") or {}),
                    },
                    "trajectory": ctx,
                }
            )

    firm_only = [
        s
        for i, s in enumerate(valid)
        if firmer_like(s, baseline_obs)
        and not (contexts[i].get("elevated") if i < len(contexts) else False)
    ]

    if len(valid) < cfg.MIN_SEGMENTS_GLOBAL:
        status = "UNKNOWN"
    elif not hits:
        status = "LOW"
    elif len(hits) == 1:
        status = "OCCASIONAL"
    elif len(hits) / len(valid) >= cfg.PREVALENCE_REPEATED:
        status = "REPEATED"
    else:
        status = "MODERATE"

    note_firm = ""
    if firm_only and not hits:
        note_firm = (
            "단단한 발성 상태는 일부 관찰됐지만, 과도한 effort와 일치하는 "
            "복합 증거는 뚜렷하지 않았어요."
        )

    mean_score = float(np.mean(all_scores)) if all_scores else 0.0
    hit_scores = [float(p.get("effort_score") or 0) for p in hit_packets]
    effort_score_out = float(max(hit_scores)) if hit_scores else mean_score

    fam_agg = {
        "intensity_trajectory": 0,
        "temporal_attack": 0,
        "recovery_persistence": 0,
        "regularity_cost": 0,
        "spectral_residual": 0,
        "contact_shift": 0,
        "intensity": 0,
        "temporal": 0,
        "regularity": 0,
        "spectral": 0,
        "recovery": 0,
        "contact": 0,
    }
    for p in hit_packets:
        fams = p.get("families") or {}
        for k, v in fams.items():
            if v and k in fam_agg:
                fam_agg[k] += 1
        if fams.get("intensity_trajectory"):
            fam_agg["intensity"] += 1
        if fams.get("temporal_attack"):
            fam_agg["temporal"] += 1
        if fams.get("regularity_cost"):
            fam_agg["regularity"] += 1
        if fams.get("spectral_residual"):
            fam_agg["spectral"] += 1
        if fams.get("recovery_persistence"):
            fam_agg["recovery"] += 1
        if fams.get("contact_shift"):
            fam_agg["contact"] += 1

    core_count = sum(
        1
        for k in ("intensity_trajectory", "temporal_attack", "recovery_persistence")
        if fam_agg.get(k)
    )
    support_count = sum(
        1
        for k in ("regularity_cost", "spectral_residual", "contact_shift")
        if fam_agg.get(k)
    )

    loud_levels = [
        (c.get("intensity") or {}).get("loudness_level")
        for c in contexts
        if c.get("intensity")
    ]
    rising_n = sum(1 for c in contexts if (c.get("intensity") or {}).get("positive"))
    static_loud_n = sum(
        1 for c in contexts if (c.get("intensity") or {}).get("status") == "STATIC_LOUD"
    )

    graph = []
    if hits:
        s0 = hits[0]
        graph.append(
            evidence_node(
                observation_ids=[
                    "intensity_db",
                    "onset_slope_db_per_sec",
                    "f0_frame_period_perturbation_proxy_percent",
                    "energy_2_4k",
                ],
                families=[
                    "intensity_trajectory",
                    "temporal_attack",
                    "recovery_persistence",
                    "regularity_cost",
                ],
                hypothesis="effort_like_acoustic_escalation",
                alternatives=[
                    "style-intentional intensity",
                    "controlled crescendo",
                    "mic proximity",
                ],
                confidence_cap="medium",
                grade="C",
                time_range=(s0["start_sec"], s0["end_sec"]),
                rule_id="EFFORT_V28",
            )
        )

    conf = "low"
    if status == "LOW" and len(valid) >= cfg.MIN_SEGMENTS_GLOBAL:
        conf = "medium"
    elif hits and core_count >= 1 and (core_count + support_count) >= 2:
        conf = "medium"
    elif hits:
        conf = "low"

    return _dim(
        "vocal_effort_strain",
        status=status,
        continuum=effort_score_out if hits or status == "LOW" else None,
        summary={
            "LOW": "안정",
            "OCCASIONAL": "일부 증가",
            "MODERATE": "중간",
            "REPEATED": "반복적인 과도 증가",
            "UNKNOWN": "UNKNOWN",
        }.get(status, status),
        meaning=note_firm
        or (
            "시간에 따라 힘이 증가하는 발성 경향과 일치할 수 있는 "
            "복합 음향 패턴이 관찰됐어요."
            if hits
            else "과도한 effort와 일치하는 복합 패턴은 뚜렷하지 않았어요."
        ),
        cannot="실제 후두 근육 긴장·복압을 측정하지 않습니다.",
        evidence=graph,
        valid=valid,
        confidence_label=conf,
        prevalence=_prevalence(len(hits), len(valid)),
        profile={
            "effort_score": round(effort_score_out, 3),
            "evidence_mass": round(float(np.mean(hit_scores)) if hit_scores else 0.0, 3),
            "family_count": core_count + support_count,
            "core_family_count": core_count,
            "support_family_count": support_count,
            "family_agreement": None,
            "family_hits": fam_agg,
            "hit_segments": len(hits),
            "effort_hit_segments": len(hits),
            "persistent_segments": fam_agg["recovery_persistence"],
            "recovery_cost": fam_agg["recovery_persistence"],
            "firm_without_effort_segments": len(firm_only),
            "contact_vs_strain_note": "FIRM_CONTACT != STRAIN",
            "mean_segment_effort_score": round(mean_score, 3),
            "loudness_level": max(set(loud_levels), key=loud_levels.count) if loud_levels else None,
            "rising_intensity_segments": rising_n,
            "static_loud_segments": static_loud_n,
            "trajectory_priority": True,
        },
        focus=[
            {
                "start_sec": s["start_sec"],
                "end_sec": s["end_sec"],
                "state": "effort_like",
                "headline": "힘이 증가하는 발성 경향",
                "user_message": (
                    "강도 상승·onset·회복 비용 중 복수 family가 동반된 "
                    "effort-like 패턴이 관찰됐어요."
                ),
                "limitation": "실제 목 근육 긴장을 직접 측정한 것은 아닙니다.",
                "effort_score": (hit_packets[i].get("effort_score") if i < len(hit_packets) else None),
                "family_ids": [
                    k for k, v in (hit_packets[i].get("families") or {}).items() if v
                ]
                if i < len(hit_packets)
                else [],
                "why": (hit_packets[i].get("trajectory") or {}).get("why")
                if i < len(hit_packets)
                else None,
            }
            for i, s in enumerate(hits[:3])
        ],
    )


def fuse_leakage(segments: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Breathiness / leakage fusion with coverage semantics (v2.3).

    LOW requires sufficient negative coverage — zero positive ≠ LOW.
    Uses dimension-specific breathiness validity (GIF not required).
    """
    from audio_analyzer.vocal_evidence.phonation_quality import classify_breathy_segment
    from audio_analyzer.vocal_function.validity import dim_valid

    evaluable = [s for s in segments if dim_valid(s, "breathiness")]
    positives, negatives, insufficient = [], [], []
    for s in evaluable:
        c = classify_breathy_segment(s)
        s = {**s, "breathy_classification": c}
        if c["verdict"] == "POSITIVE":
            positives.append(s)
        elif c["verdict"] == "NEGATIVE":
            negatives.append(s)
        else:
            insufficient.append(s)

    n_eval = len(evaluable)
    n_pos, n_neg, n_ins = len(positives), len(negatives), len(insufficient)
    pos_ratio = n_pos / n_eval if n_eval else 0.0
    neg_ratio = n_neg / n_eval if n_eval else 0.0

    coverage = {
        "n_total_segments": len(segments),
        "n_evaluable_segments": n_eval,
        "n_positive_segments": n_pos,
        "n_negative_segments": n_neg,
        "n_insufficient_segments": n_ins + (len(segments) - n_eval),
        "positive_ratio": round(pos_ratio, 3),
        "negative_ratio": round(neg_ratio, 3),
        "evaluable": n_eval,
        "positive": n_pos,
        "negative": n_neg,
        "insufficient": n_ins + (len(segments) - n_eval),
    }

    if n_eval < cfg.MIN_SEGMENTS_GLOBAL:
        status = "UNKNOWN"
        meaning = "이번 녹음에서는 기식성 경향을 충분히 판단하지 못했어요."
        summary = "판단 부족"
    elif n_pos >= cfg.MIN_SEGMENTS_GLOBAL and pos_ratio >= cfg.PREVALENCE_REPEATED:
        status = "HIGH"
        meaning = "기류 누출이 많은 발성과 일치할 수 있는 음향 패턴이 여러 구간에서 관찰됐어요."
        summary = "반복"
    elif n_pos >= 2 and pos_ratio >= cfg.PREVALENCE_OCCASIONAL:
        status = "MODERATE"
        meaning = "숨이 섞이는 음질과 일치할 수 있는 음향 패턴이 여러 구간에서 관찰됐어요."
        summary = "중간"
    elif n_pos == 1:
        status = "OCCASIONAL"
        meaning = "일부 구간에서 기식성·누출과 일치할 수 있는 단서가 있어요."
        summary = "일부"
    elif n_neg >= max(cfg.MIN_SEGMENTS_GLOBAL, int(0.5 * n_eval)) and n_pos == 0:
        status = "LOW"
        meaning = "기식성·누출 경향은 뚜렷하지 않았어요."
        summary = "낮은 편"
    else:
        status = "UNKNOWN"
        meaning = "이번 녹음에서는 기식성 경향을 충분히 판단하지 못했어요."
        summary = "판단 부족"

    conf = "low"
    if status == "UNKNOWN":
        conf = "low"
    elif n_eval >= 8 and status in ("LOW", "MODERATE", "HIGH"):
        conf = "medium"
    elif n_eval >= cfg.MIN_SEGMENTS_GLOBAL:
        conf = "medium" if status != "OCCASIONAL" else "low"

    out = _dim(
        "air_leakage_breathiness",
        status=status,
        continuum=None,
        summary=summary,
        meaning=meaning,
        cannot="실제 성문 틈·성대 접촉을 측정하지 않습니다.",
        evidence=[],
        valid=evaluable,
        confidence_label=conf,
        prevalence=_prevalence(n_pos, n_eval) if n_eval else "unknown",
        focus=[
            {
                "start_sec": s["start_sec"],
                "end_sec": s["end_sec"],
                "state": "leakage_like",
                "headline": "기류 누출·기식성 경향",
                "user_message": "주기성·스펙트럼 단서가 함께 약한 구간이에요.",
                "limitation": "성대 접촉을 직접 측정한 것은 아닙니다.",
                "role": "OBSERVATION",
            }
            for s in positives[:3]
        ],
        profile=coverage,
    )
    out["breathiness_coverage"] = coverage
    return out


def _rough_events(positives: list[dict[str, Any]], *, gap_sec: float = 1.25) -> list[dict[str, Any]]:
    """Merge temporally adjacent rough hits into events (persistence)."""
    if not positives:
        return []
    ordered = sorted(
        positives,
        key=lambda s: float(s.get("start") if s.get("start") is not None else s.get("t0") or 0.0),
    )
    events: list[dict[str, Any]] = []
    cur: list[dict[str, Any]] = [ordered[0]]

    def _end(s: dict[str, Any]) -> float:
        if s.get("end") is not None:
            return float(s["end"])
        t0 = float(s.get("start") if s.get("start") is not None else s.get("t0") or 0.0)
        return t0 + float(s.get("duration") or 0.0)

    def _start(s: dict[str, Any]) -> float:
        return float(s.get("start") if s.get("start") is not None else s.get("t0") or 0.0)

    for s in ordered[1:]:
        if _start(s) - _end(cur[-1]) <= gap_sec:
            cur.append(s)
        else:
            events.append(
                {
                    "n_hits": len(cur),
                    "start": _start(cur[0]),
                    "end": _end(cur[-1]),
                    "duration": max(0.0, _end(cur[-1]) - _start(cur[0])),
                    "adjacent_run_length": len(cur),
                }
            )
            cur = [s]
    events.append(
        {
            "n_hits": len(cur),
            "start": _start(cur[0]),
            "end": _end(cur[-1]),
            "duration": max(0.0, _end(cur[-1]) - _start(cur[0])),
            "adjacent_run_length": len(cur),
        }
    )
    return events


def fuse_regularity(segments: list[dict[str, Any]]) -> dict[str, Any]:
    """Roughness requires irregularity-specific evidence — CPP alone is not enough.

    v2.9: segment hits are merged into temporal events; isolated singles stay
    INTERMITTENT; REPEATED_IRREGULAR needs persistence (adjacent run or multiple events).
    """
    from audio_analyzer.vocal_evidence.phonation_quality import classify_rough_segment
    from audio_analyzer.vocal_function.validity import dim_valid

    evaluable = [s for s in segments if dim_valid(s, "roughness") or s.get("valid")]
    rough = []
    rejected_period_only = []
    rejected_artifact = []
    scores: list[float] = []
    for s in evaluable:
        c = classify_rough_segment(s)
        if c["verdict"] == "POSITIVE":
            rough.append({**s, "rough_classification": c})
            scores.append(float(c.get("roughness_score") or 0.6))
        elif c.get("reason") == "periodicity_loss_without_irregularity":
            rejected_period_only.append(s)
        elif c.get("reason") in (
            "tracker_artifact",
            "tracker_artifact_irregularity",
            "clean_phonation_tracker_noise",
            "breathy_contamination",
            "insufficient_voiced_frames",
        ):
            rejected_artifact.append(s)

    events = _rough_events(rough)
    max_run = max((e["adjacent_run_length"] for e in events), default=0)
    total_duration = sum(float(e["duration"]) for e in events)
    persistence = {
        "positive_microframes": len(rough),
        "n_events": len(events),
        "positive_duration": round(total_duration, 3),
        "adjacent_run_length": max_run,
        "event_density": round(len(events) / max(len(evaluable), 1), 4),
        "events": events,
    }

    coverage = {
        "evaluable": len(evaluable),
        "positive": len(rough),
        "rejected_periodicity_only": len(rejected_period_only),
        "rejected_tracker_artifact": len(rejected_artifact),
        "n_events": len(events),
        "max_adjacent_run": max_run,
    }

    # Strong repeated roughness requires temporal persistence, not raw hit count.
    if len(evaluable) < 2:
        status = "UNKNOWN"
    elif not rough:
        status = "STABLE"
    elif max_run >= 2:
        # Adjacent cluster of irregularity = repeated/persistent
        status = "REPEATED_IRREGULAR"
    elif len(events) >= 3 and (len(rough) / max(len(evaluable), 1)) >= 0.2:
        # Multiple separated events with meaningful prevalence
        status = "REPEATED_IRREGULAR"
    elif rough:
        status = "INTERMITTENT"
    else:
        status = "STABLE"

    mean_score = sum(scores) / len(scores) if scores else 0.0
    if status == "REPEATED_IRREGULAR":
        conf = "high" if max_run >= 3 or mean_score >= 0.7 else "medium"
    elif status == "INTERMITTENT":
        conf = "medium" if mean_score >= 0.6 else "low"
    else:
        conf = "medium"

    meaning = (
        "거칠고 불규칙한 음질 패턴이 일부 관찰됐어요. "
        "의도적 distortion일 수도 있어 잘못이라고 단정하지 않아요."
        if rough
        else "진동 규칙성은 비교적 유지되는 편이에요."
    )
    if not rough and rejected_period_only:
        meaning = (
            "주기성 저하만으로는 거친 음질로 보지 않았어요. "
            "불규칙 진동 특성이 뚜렷하지 않았어요."
        )
    if not rough and rejected_artifact:
        meaning = (
            "피치 추적 아티팩트로 보이는 순간 점프는 "
            "거친 음질로 세지 않았어요."
        )

    out = _dim(
        "phonation_regularity",
        status=status,
        continuum=None,
        summary={
            "STABLE": "비교적 규칙적",
            "INTERMITTENT": "일부 구간 불규칙",
            "REPEATED_IRREGULAR": "반복적 불규칙",
            "UNKNOWN": "UNKNOWN",
        }.get(status, status),
        meaning=meaning,
        cannot="병변·성대 상태를 진단하지 않습니다.",
        evidence=[],
        valid=evaluable,
        prevalence=_prevalence(len(rough), len(evaluable)) if evaluable else "unknown",
    )
    out["roughness_coverage"] = coverage
    out["roughness_persistence"] = persistence
    out["roughness_score"] = round(mean_score, 3)
    out["roughness_confidence"] = conf
    return out


def fuse_register(
    segments: list[dict[str, Any]],
    pitch: dict[str, Any],
    *,
    vibrato: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Register transitions require vocal-specific verified activity + F0 + source change.
    Spectral / accompaniment-only changes are rejected.
    """
    valid = [s for s in segments if s.get("valid")]
    vibrato = vibrato or {}
    vibrato_mask = bool(
        vibrato.get("available")
        and (vibrato.get("regularity") or 0) >= 0.45
        and (vibrato.get("depth_cents") or vibrato.get("extent_cents") or 0) >= 20
    )

    events = []
    rejected = []
    for i in range(len(valid) - 1):
        a, b = valid[i], valid[i + 1]
        va = (a.get("vocal_evidence") or {})
        vb = (b.get("vocal_evidence") or {})
        fa = (a.get("observations") or {}).get("f0_hz")
        fb = (b.get("observations") or {}).get("f0_hz")
        if not fa or not fb or fa <= 0:
            continue
        cents = 1200 * np.log2(fb / fa)
        if abs(cents) < 350:
            continue

        # Vibrato-regular modulation must not become register events
        if vibrato_mask and abs(cents) < 600:
            rejected.append(
                {
                    "start_sec": a["start_sec"],
                    "end_sec": b["end_sec"],
                    "reason_code": "REGISTER_EVENT_REJECTED",
                    "detail": "vibrato_mask",
                    "rejected": True,
                }
            )
            continue

        # Vocal-specific gate
        if not va.get("vocal_specific", False) or not vb.get("vocal_specific", False):
            rejected.append(
                {
                    "start_sec": a["start_sec"],
                    "end_sec": b["end_sec"],
                    "reason_code": "REGISTER_EVENT_REJECTED",
                    "detail": "not_vocal_specific",
                    "accompaniment_match": max(
                        va.get("accompaniment_match") or 0,
                        vb.get("accompaniment_match") or 0,
                    ),
                    "rejected": True,
                }
            )
            continue

        if max(va.get("accompaniment_match") or 0, vb.get("accompaniment_match") or 0) >= 0.7:
            rejected.append(
                {
                    "start_sec": a["start_sec"],
                    "end_sec": b["end_sec"],
                    "reason_code": "REGISTER_EVENT_REJECTED",
                    "detail": "accompaniment_contamination",
                    "rejected": True,
                }
            )
            continue

        # Require time-local SOURCE change (not spectral alone)
        src_change = lighter_like(a) != lighter_like(b) or firmer_like(a) != firmer_like(b)
        naq_a = ((a.get("level2_proxies") or {}).get("glottal_source") or {}).get("estimated_naq")
        naq_b = ((b.get("level2_proxies") or {}).get("glottal_source") or {}).get("estimated_naq")
        naq_change = (
            naq_a is not None
            and naq_b is not None
            and abs(float(naq_a) - float(naq_b)) >= 0.03
        )
        h1_a = (a.get("observations") or {}).get("raw_h1_h2_proxy_db")
        h1_b = (b.get("observations") or {}).get("raw_h1_h2_proxy_db")
        h1_change = (
            h1_a is not None
            and h1_b is not None
            and abs(float(h1_a) - float(h1_b)) >= 3.0
        )
        period_change = abs(
            ((a.get("observations") or {}).get("periodicity_primary_db") or 0)
            - ((b.get("observations") or {}).get("periodicity_primary_db") or 0)
        ) >= 4
        intensity_change = abs(
            ((a.get("observations") or {}).get("rms") or 0)
            - ((b.get("observations") or {}).get("rms") or 0)
        ) >= 0.02

        source_family = src_change or naq_change or h1_change
        support_family = period_change or intensity_change
        # Must have source change + at least one supporting family
        if not (source_family and support_family):
            rejected.append(
                {
                    "start_sec": a["start_sec"],
                    "end_sec": b["end_sec"],
                    "reason_code": "REGISTER_EVENT_REJECTED",
                    "detail": "insufficient_source_evidence",
                    "rejected": True,
                }
            )
            continue

        events.append(
            {
                "start_sec": a["start_sec"],
                "end_sec": b["end_sec"],
                "f0_jump_cents": float(cents),
                "state": "transition_like",
                "validity": {
                    "vocal_specific": True,
                    "vocal_confidence": min(
                        va.get("vocal_confidence") or 0,
                        vb.get("vocal_confidence") or 0,
                    ),
                },
                "evidence": {
                    "source_change": src_change,
                    "naq_change": naq_change,
                    "h1h2_change": h1_change,
                    "periodicity_change": period_change,
                    "intensity_change": intensity_change,
                },
                "rejected": False,
            }
        )

    status = "UNKNOWN" if len(valid) < 2 else ("TRANSITION_EVENTS" if events else "STABLE_LIKE")
    return _dim(
        "register_configuration",
        status=status,
        continuum=None,
        summary="전환 구간 관찰" if events else "뚜렷한 전환 이슈 제한적",
        meaning=(
            "음역 전환에서 source configuration 변화가 크게 나타났어요."
            if events
            else "큰 음역 전환에서의 source 변화는 제한적이었어요."
        ),
        cannot="실제 laryngeal mechanism(M1/M2)을 Audio-only로 확정하지 않습니다.",
        evidence=[],
        valid=valid,
        profile={
            "events": events[:5],
            "rejected_events": rejected[:8],
            "labels": "M1-like/M2-like are hypotheses only",
        },
        focus=[
            {
                "start_sec": e["start_sec"],
                "end_sec": e["end_sec"],
                "state": "transition_like",
                "headline": "성구·음역 전환",
                "user_message": "검증된 보컬 구간에서 음높이·source 패턴이 바뀌었어요.",
                "limitation": "실제 후두 메커니즘을 확정하지 않습니다.",
            }
            for e in events[:2]
        ],
        confidence_label="medium" if events else "low",
    )


def fuse_onset_offset(segments: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [s for s in segments if s.get("valid")]
    abrupt = soft = airy = 0
    for s in valid:
        obs = s.get("observations") or {}
        slope = obs.get("onset_slope_db_per_sec")
        rise = obs.get("onset_rise_sec")
        fam = 0
        if slope is not None and slope >= 80:
            fam += 1
        if rise is not None and rise < 0.03:
            fam += 1
        if fam >= 2:
            abrupt += 1
        elif leakage_like(s) and (rise or 1) > 0.08:
            airy += 1
        elif slope is not None and slope < 40:
            soft += 1
    if len(valid) < 2:
        status = "UNKNOWN"
    elif abrupt >= 2:
        status = "ABRUPT_LIKE"
    elif airy >= 2:
        status = "AIRY_LIKE"
    elif soft >= 2:
        status = "BALANCED_LIKE"
    else:
        status = "MIXED"
    return _dim(
        "onset_offset_coordination",
        status=status,
        continuum=None,
        summary={
            "ABRUPT_LIKE": "일부 시작이 급하게 형성됨",
            "AIRY_LIKE": "숨이 섞인 시작이 일부 관찰됨",
            "BALANCED_LIKE": "대체로 부드럽게 시작",
            "MIXED": "혼합",
            "UNKNOWN": "UNKNOWN",
        }.get(status, status),
        meaning="소리 시작·마무리 특성을 음향적으로 관찰한 결과예요.",
        cannot="glottal attack을 생리적 사실로 확정하지 않습니다.",
        evidence=[],
        valid=valid,
    )


def fuse_vibrato(optional: dict[str, Any]) -> dict[str, Any]:
    vib = (optional or {}).get("vibrato") or {}
    if not vib.get("available"):
        return _dim(
            "vibrato_control",
            status="UNKNOWN",
            continuum=None,
            summary="이번 녹음에서 비브라토를 충분히 관찰하지 못했어요.",
            meaning="",
            cannot="",
            evidence=[],
            valid=[],
            profile={},
        )
    return _dim(
        "vibrato_control",
        status="OBSERVED",
        continuum=None,
        summary="비브라토 프로필",
        meaning="규칙적 비브라토는 불안정성으로 취급하지 않아요.",
        cannot="",
        evidence=[],
        valid=[],
        profile={
            "rate_hz": vib.get("rate_hz"),
            "extent_cents": vib.get("depth_cents") or vib.get("extent_cents"),
            "regularity": vib.get("regularity"),
            "descriptive_only": True,
        },
    )


def fuse_resonance(segments: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [s for s in segments if s.get("valid")]
    profiles = [
        ((s.get("level2_proxies") or {}).get("timbre") or {})
        for s in valid
        if not ((s.get("level2_proxies") or {}).get("timbre") or {}).get("restricted")
    ]
    formant_ok = sum(
        1
        for s in valid
        if ((s.get("level2_proxies") or {}).get("formants") or {}).get("valid")
    )
    if len(valid) < 2 or (formant_ok == 0 and not profiles):
        return _dim(
            "resonance_formant_strategy",
            status="UNKNOWN",
            continuum=None,
            summary="공명·음색을 제한적으로만 관찰했어요.",
            meaning="",
            cannot="인두·비강 해부를 측정하지 않습니다.",
            evidence=[],
            valid=valid,
            restricted=True,
        )
    # Aggregate modal labels
    bright = [p.get("brightness") for p in profiles if p.get("brightness")]
    mid = [p.get("mid_presence") for p in profiles if p.get("mid_presence")]
    profile = {
        "brightness": max(set(bright), key=bright.count) if bright else "UNKNOWN",
        "mid_presence": max(set(mid), key=mid.count) if mid else "UNKNOWN",
        "upper_harmonic_presence": "보통",
        "descriptive_only": True,
        "no_universal_target": True,
    }
    return _dim(
        "resonance_formant_strategy",
        status="OBSERVED",
        continuum=None,
        summary=f"밝기 {profile['brightness']} · 중역 {profile['mid_presence']}",
        meaning="음색·공명 전략 설명이며 좋고 나쁨을 의미하지 않습니다.",
        cannot="인두 공간·비강 공명을 측정하지 않습니다.",
        evidence=[],
        valid=valid,
        profile=profile,
    )


def fuse_respiratory(segments: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [s for s in segments if s.get("valid")]
    # Phrase-end instability proxy only
    endish = valid[-3:] if len(valid) >= 3 else valid
    drops = 0
    for s in endish:
        obs = s.get("observations") or {}
        if (obs.get("periodicity_primary_db") or 99) < 7 and (obs.get("rms") or 1) < 0.02:
            drops += 1
    status = "UNKNOWN" if len(valid) < 3 else ("END_PHRASE_DROP" if drops >= 2 else "STABLE_LIKE")
    return _dim(
        "respiratory_phonatory_coordination",
        status=status,
        continuum=None,
        summary=(
            "구절 끝에서 음량·주기성이 함께 떨어지는 패턴이 일부 있어요."
            if status == "END_PHRASE_DROP"
            else "호흡-발성 협응 proxy는 비교적 안정적이에요."
        ),
        meaning="Audio-only respiratory_phonatory_coordination_proxy입니다.",
        cannot="복압·횡격막·폐용적·subglottal pressure를 측정하지 않습니다.",
        evidence=[],
        valid=valid,
        profile={"proxy_only": True, "never_outputs_actual_pressure": True},
    )


def fuse_economy(segments: list[dict[str, Any]], effort: dict[str, Any]) -> dict[str, Any]:
    # Very restricted proxy
    if effort.get("status") in ("REPEATED", "MODERATE"):
        status = "REDUCED_PROXY"
        summary = "같은 맥락에서 effort proxy가 높아 효율 경향이 낮게 추정돼요."
    elif effort.get("status") == "LOW":
        status = "OK_PROXY"
        summary = "뚜렷한 비효율 proxy는 제한적이에요."
    else:
        status = "UNKNOWN"
        summary = "발성 효율 proxy를 확정하지 않았어요."
    return _dim(
        "phonatory_economy_proxy",
        status=status,
        continuum=None,
        summary=summary,
        meaning="physiological efficiency가 아닌 audio proxy입니다.",
        cannot="실제 laryngeal efficiency를 측정하지 않습니다.",
        evidence=[],
        valid=[s for s in segments if s.get("valid")],
        restricted=True,
    )


def _dim(
    dimension_id: str,
    *,
    status: str,
    continuum,
    summary: str,
    meaning: str,
    cannot: str,
    evidence: list,
    valid: list,
    confidence_label: str = "low",
    prevalence: str = "unknown",
    profile: Optional[dict] = None,
    focus: Optional[list] = None,
    continuum_label: Optional[str] = None,
    restricted: bool = False,
    lock_confidence: bool = False,
) -> dict[str, Any]:
    hidden = status in ("UNKNOWN", "AMBIGUOUS")
    # Negative/positive conclusions need enough segments to leave "low"
    if (
        not lock_confidence
        and confidence_label == "low"
        and not restricted
        and status not in ("UNKNOWN", "AMBIGUOUS", None)
        and len(valid) >= cfg.MIN_SEGMENTS_GLOBAL
    ):
        confidence_label = "medium"
    # Still hide low-confidence from main (including weak negatives)
    if confidence_label == "low":
        hidden = True
    return {
        "dimension_id": dimension_id,
        "display_name": cfg.DIMENSION_DISPLAY.get(dimension_id, dimension_id),
        "status": status,
        "status_label": summary if isinstance(summary, str) else status,
        "continuum_0_to_1": continuum,
        "continuum_label": continuum_label,
        "prevalence": prevalence,
        "confidence_label": confidence_label,
        "summary": summary,
        "what_it_may_mean": meaning,
        "what_we_cannot_know": "",  # card-level medical disclaimer removed; footer only
        "limitation_short": cannot if status in ("MODERATE", "HIGH", "REPEATED", "TRANSITION_EVENTS") else "",
        "observations": [],
        "evidence_graph": evidence,
        "focus_segments": focus or [],
        "profile": profile or {},
        "practice": [],
        "hidden": hidden,
        "restricted": restricted,
        "layer": "LEVEL_3_FUNCTIONAL_STATE_ESTIMATE",
        "valid_segment_count": len(valid),
        "hit_segment_count": len(focus or []),
    }
