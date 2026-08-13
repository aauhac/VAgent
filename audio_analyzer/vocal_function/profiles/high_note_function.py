"""Derived High-Note Function Profile (v2.11) — not a canonical dimension."""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from audio_analyzer.vocal_evidence.phonation_quality import classify_rough_segment
from audio_analyzer.vocal_function.evidence.effort_contact import effort_like
from audio_analyzer.vocal_function.evidence.families import leakage_like


MIN_HIGH_SEGMENTS = 2
MIN_HIGH_DURATION_SEC = 0.45
MIN_VOICED_RATIO = 0.35
MAX_DROPOUT = 0.55
MAX_OCTAVE_JUMP = 0.25
# Relative high uses +1.5 st above median — span must at least support that contrast.
# Not sample-tuned: mirrors thr_rel construction in partition_pitch_regions.
MIN_SPAN_SEMITONES_FOR_HIGH_COMPARE = 1.5
HIGH_RELATIVE_SEMITONES = 1.5


def _obs(seg: dict[str, Any]) -> dict[str, Any]:
    return seg.get("observations") or {}


def _vocal_ok(seg: dict[str, Any]) -> bool:
    if not seg.get("valid"):
        return False
    ve = seg.get("vocal_evidence") or {}
    if not ve.get("vocal_specific", True):
        return False
    if float(ve.get("accompaniment_match") or 0) >= 0.7:
        return False
    return True


def _f0(seg: dict[str, Any]) -> Optional[float]:
    v = _obs(seg).get("f0_hz")
    return float(v) if v is not None and float(v) > 0 else None


def _seg_dur(seg: dict[str, Any]) -> float:
    return max(0.0, float(seg.get("end_sec") or 0) - float(seg.get("start_sec") or 0))


def _tracker_bad(seg: dict[str, Any]) -> bool:
    obs = _obs(seg)
    art = obs.get("f0_tracker_artifact") or {}
    if art.get("suspect"):
        return True
    if float(obs.get("f0_octave_jump_ratio") or 0) >= MAX_OCTAVE_JUMP:
        return True
    return False


def _reliable_pitch_seg(seg: dict[str, Any]) -> bool:
    if not _vocal_ok(seg):
        return False
    f0 = _f0(seg)
    if f0 is None:
        return False
    obs = _obs(seg)
    voiced = float(seg.get("voiced_ratio") or obs.get("voiced_ratio") or 0)
    dropout = float(obs.get("f0_dropout_ratio") or 1.0)
    if voiced < MIN_VOICED_RATIO:
        return False
    if dropout > MAX_DROPOUT:
        return False
    if _tracker_bad(seg):
        return False
    if _seg_dur(seg) < 0.25:
        return False
    return True


def _hz_to_st(hz: float) -> float:
    return float(12.0 * np.log2(max(hz, 1e-6) / 440.0) + 69.0)


def _span_semitones(lo: Optional[float], hi: Optional[float]) -> Optional[float]:
    if lo is None or hi is None or lo <= 0 or hi <= 0:
        return None
    return round(float(12.0 * np.log2(hi / lo)), 2)


def _med(vals: list[float]) -> Optional[float]:
    if not vals:
        return None
    return float(np.median(np.asarray(vals, dtype=float)))


def _mean(vals: list[float]) -> Optional[float]:
    if not vals:
        return None
    return float(np.mean(np.asarray(vals, dtype=float)))


def _candidate_row(seg: dict[str, Any], *, accepted: bool, rejection_reason: Optional[str]) -> dict[str, Any]:
    obs = _obs(seg)
    ve = seg.get("vocal_evidence") or {}
    art = obs.get("f0_tracker_artifact") or {}
    return {
        "start_sec": seg.get("start_sec"),
        "end_sec": seg.get("end_sec"),
        "duration_sec": round(_seg_dur(seg), 3),
        "f0": _f0(seg),
        "voiced_ratio": float(seg.get("voiced_ratio") or obs.get("voiced_ratio") or 0),
        "dropout_ratio": float(obs.get("f0_dropout_ratio") or 0),
        "octave_jump_ratio": float(obs.get("f0_octave_jump_ratio") or 0),
        "tracker_suspect": bool(art.get("suspect")),
        "vocal_specific": bool(ve.get("vocal_specific", True)),
        "accompaniment_match": float(ve.get("accompaniment_match") or 0),
        "accepted": accepted,
        "rejection_reason": rejection_reason,
    }


def assess_pitch_range_sufficiency(
    *,
    f0s: list[float],
    high_threshold_hz: Optional[float],
) -> dict[str, Any]:
    """STEP 1: can this recording support mid↔high relative comparison?"""
    if len(f0s) < 3:
        return {
            "status": "UNRELIABLE",
            "usable_span_semitones": None,
            "usable_min_f0_hz": None,
            "usable_max_f0_hz": None,
            "distribution": {},
            "reason": "INSUFFICIENT_USABLE_F0",
        }
    arr = np.asarray(f0s, dtype=float)
    usable_min = float(np.min(arr))
    usable_max = float(np.max(arr))
    span = _span_semitones(usable_min, usable_max)
    dist = {
        "p35": round(float(np.percentile(arr, 35)), 2),
        "p50": round(float(np.percentile(arr, 50)), 2),
        "p65": round(float(np.percentile(arr, 65)), 2),
        "p75": round(float(np.percentile(arr, 75)), 2),
        "p90": round(float(np.percentile(arr, 90)), 2),
    }
    thr_outside = (
        high_threshold_hz is not None
        and usable_max > 0
        and float(high_threshold_hz) > float(usable_max) + 1e-6
    )
    span_too_narrow = span is None or float(span) < float(MIN_SPAN_SEMITONES_FOR_HIGH_COMPARE)
    if thr_outside or span_too_narrow:
        return {
            "status": "INSUFFICIENT",
            "usable_span_semitones": span,
            "usable_min_f0_hz": round(usable_min, 2),
            "usable_max_f0_hz": round(usable_max, 2),
            "distribution": dist,
            "reason": "INSUFFICIENT_PITCH_RANGE",
            "threshold_outside_observed_support": bool(thr_outside),
        }
    return {
        "status": "SUFFICIENT",
        "usable_span_semitones": span,
        "usable_min_f0_hz": round(usable_min, 2),
        "usable_max_f0_hz": round(usable_max, 2),
        "distribution": dist,
        "reason": None,
        "threshold_outside_observed_support": False,
    }


def partition_pitch_regions(
    segments: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Relative mid vs high regions from within-recording F0 distribution.

    STEP 1 — pitch range sufficiency (mid↔high contrast possible?)
    STEP 2 — only then form upper-range candidates (never clamp thr into max).
    """
    usable = [s for s in segments if _reliable_pitch_seg(s)]
    f0s = [_f0(s) for s in usable]
    f0s = [f for f in f0s if f is not None]
    context: dict[str, Any] = {
        "median_f0_hz": None,
        "p75_f0_hz": None,
        "p90_f0_hz": None,
        "highest_observed_f0_hz": None,
        "highest_reliable_f0_hz": None,
        "range_span_semitones": None,
        "n_usable_segments": len(usable),
        "n_total_segments": len(segments),
        "n_reliable_pitch_segments": len(usable),
        "candidate_table": [],
        "pitch_range_sufficiency": {
            "status": "UNRELIABLE",
            "usable_span_semitones": None,
            "usable_min_f0_hz": None,
            "usable_max_f0_hz": None,
            "distribution": {},
            "reason": "INSUFFICIENT_USABLE_F0",
        },
    }
    if len(f0s) < 3:
        return [], [], context

    arr = np.asarray(f0s, dtype=float)
    p50 = float(np.percentile(arr, 50))
    p75 = float(np.percentile(arr, 75))
    p90 = float(np.percentile(arr, 90))
    observed_max = float(np.max(arr))
    observed_min = float(np.min(arr))
    # High region: at/above the greater of p75 and HIGH_RELATIVE_SEMITONES above median
    thr_rel = p50 * (2.0 ** (HIGH_RELATIVE_SEMITONES / 12.0))
    high_thr = max(p75, thr_rel)
    # NEVER clamp high_thr into observed_max — that invents a high region.

    sufficiency = assess_pitch_range_sufficiency(f0s=f0s, high_threshold_hz=high_thr)
    context["pitch_range_sufficiency"] = sufficiency
    context.update(
        {
            "median_f0_hz": round(p50, 2),
            "p35_f0_hz": round(float(np.percentile(arr, 35)), 2),
            "p65_f0_hz": round(float(np.percentile(arr, 65)), 2),
            "p75_f0_hz": round(p75, 2),
            "p90_f0_hz": round(p90, 2),
            "highest_observed_f0_hz": round(observed_max, 2),
            "range_span_semitones": sufficiency.get("usable_span_semitones")
            or _span_semitones(observed_min, observed_max),
            "high_threshold_hz": round(high_thr, 2),
            "n_high_segments": 0,
            "n_reliable_high_segments": 0,
            "n_mid_segments": 0,
            "highest_reliable_f0_hz": None,
        }
    )

    if sufficiency.get("status") != "SUFFICIENT":
        # Range problem — not "user cannot sing high"
        context["partition_gate"] = "RANGE_INSUFFICIENT"
        return [], [], context

    # Mid / comfort: around median band (p35–p65), excluding high
    mid_lo = float(np.percentile(arr, 35))
    mid_hi = float(np.percentile(arr, 65))

    high: list[dict[str, Any]] = []
    mid: list[dict[str, Any]] = []
    candidate_table: list[dict[str, Any]] = []
    for s in usable:
        f0 = _f0(s)
        if f0 is None:
            continue
        if f0 >= high_thr:
            # Upper-range candidate — apply reliability gates with traceable reasons
            reason = None
            if _seg_dur(s) < MIN_HIGH_DURATION_SEC:
                reason = "DURATION"
            elif float(_obs(s).get("f0_dropout_ratio") or 1) > 0.45:
                reason = "DROPOUT"
            elif _tracker_bad(s):
                reason = "TRACKER_ARTIFACT"
            if reason is None:
                high.append(s)
                candidate_table.append(_candidate_row(s, accepted=True, rejection_reason=None))
            else:
                candidate_table.append(_candidate_row(s, accepted=False, rejection_reason=reason))
        elif mid_lo <= f0 <= mid_hi:
            mid.append(s)

    reliable_high = list(high)  # already duration/dropout filtered above
    reliable_f0s = [_f0(s) for s in reliable_high]
    reliable_f0s = [f for f in reliable_f0s if f is not None]
    if reliable_f0s:
        hi_rel = float(np.max(reliable_f0s))
    else:
        hi_rel = None
        soft = [_f0(s) for s in high if not _tracker_bad(s)]
        soft = [f for f in soft if f is not None]
        if len(soft) >= MIN_HIGH_SEGMENTS:
            hi_rel = float(np.percentile(soft, 90))

    context.update(
        {
            "highest_reliable_f0_hz": round(hi_rel, 2) if hi_rel is not None else None,
            "n_high_segments": len(high),
            "n_reliable_high_segments": len(reliable_high),
            "n_mid_segments": len(mid),
            "candidate_table": candidate_table,
            "partition_gate": "UPPER_REGION_BUILT",
        }
    )
    return mid, high, context


def _region_metric(segs: list[dict[str, Any]], key: str) -> Optional[float]:
    vals = []
    for s in segs:
        v = _obs(s).get(key)
        if v is not None:
            try:
                vals.append(float(v))
            except (TypeError, ValueError):
                pass
    return _med(vals)


def _effort_rate(segs: list[dict[str, Any]], baseline: dict[str, Any]) -> Optional[float]:
    if not segs:
        return None
    hits = 0
    for i, s in enumerate(segs):
        pre = segs[i - 1] if i > 0 else None
        post = segs[i + 1] if i + 1 < len(segs) else None
        if effort_like(s, baseline, pre=pre, post=post):
            hits += 1
    return float(hits / len(segs))


def _breath_rate(segs: list[dict[str, Any]]) -> Optional[float]:
    if not segs:
        return None
    hits = sum(1 for s in segs if leakage_like(s))
    return float(hits / len(segs))


def _rough_rate(segs: list[dict[str, Any]]) -> Optional[float]:
    if not segs:
        return None
    hits = 0
    n = 0
    for s in segs:
        # Skip when vibrato-like periodicity is strong (mask normal vibrato)
        vib = float(_obs(s).get("vibrato_rate_hz") or 0)
        if 4.0 <= vib <= 8.0 and float(_obs(s).get("periodicity_primary_db") or 0) >= 10:
            continue
        n += 1
        verdict = classify_rough_segment(s).get("verdict")
        if verdict == "POSITIVE":
            hits += 1
    if n <= 0:
        return None
    return float(hits / n)


def _dropout_mean(segs: list[dict[str, Any]]) -> Optional[float]:
    return _region_metric(segs, "f0_dropout_ratio")


def _axis(
    *,
    status: str,
    continuum: Optional[float] = None,
    delta_from_mid: Optional[float] = None,
    confidence_label: str = "low",
    summary: Optional[str] = None,
    provenance: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    out = {
        "status": status,
        "continuum": continuum,
        "delta_from_mid": delta_from_mid,
        "confidence_label": confidence_label,
        "summary": summary,
    }
    if provenance:
        out["provenance"] = provenance
    return out


def _conf_from_n(n_mid: int, n_high: int, *, mixed: bool) -> str:
    if n_high < MIN_HIGH_SEGMENTS or n_mid < 1:
        return "low"
    if mixed:
        return "low" if n_high < 4 else "medium"
    if n_high >= 4 and n_mid >= 2:
        return "high"
    return "medium"


def build_high_note_function_profile(
    *,
    segments: list[dict[str, Any]],
    dimensions: dict[str, Any],
    baseline: Optional[dict[str, Any]] = None,
    episodes: Optional[list[dict[str, Any]]] = None,
    input_mode: str = "AUTO",
    functional_quality: str = "FULL",
) -> dict[str, Any]:
    """
    Derived profile: how phonation changes in the singer's own high region.
    Does NOT invent a single high-note score.
    """
    baseline = baseline or {}
    episodes = episodes or []
    mixed = (input_mode or "").upper() == "MIXED" or functional_quality == "LIMITED"

    mid, high, pitch_context = partition_pitch_regions(segments)
    n_high = int(pitch_context.get("n_reliable_high_segments") or pitch_context.get("n_high_segments") or 0)
    n_high_raw = int(pitch_context.get("n_high_segments") or 0)
    n_mid = int(pitch_context.get("n_mid_segments") or 0)
    sufficiency = pitch_context.get("pitch_range_sufficiency") or {}
    range_status = str(sufficiency.get("status") or "").upper()

    if n_high < MIN_HIGH_SEGMENTS or pitch_context.get("highest_reliable_f0_hz") is None:
        # Classify why — never invent high-note axis values; never imply absolute inability
        if range_status in ("INSUFFICIENT", "UNRELIABLE") or sufficiency.get(
            "threshold_outside_observed_support"
        ):
            reject = "INSUFFICIENT_PITCH_RANGE"
            # Alias for older reports / tests
            reject_alias = "RELATIVE_HIGH_PARTITION"
            reason_copy = (
                "이번 노래에서는 중간 음역과 높은 음역을 "
                "안정적으로 비교할 만큼 음역 변화가 충분하지 않았어요."
            )
        elif n_mid < 1 and n_high_raw >= 1:
            reject = "INSUFFICIENT_MID_REFERENCE"
            reject_alias = reject
            reason_copy = (
                "높은 음 구간은 일부 확인됐지만, "
                "비교 기준이 되는 중간 음역 구간이 충분하지 않았어요."
            )
        elif n_high_raw == 0:
            reject = "NO_RELIABLE_HIGH_REGION"
            reject_alias = "NO_HIGH_CANDIDATES"
            reason_copy = (
                "이번 녹음에서는 비교에 쓸 수 있는 높은 음 구간을 "
                "안정적으로 나누지 못했어요."
            )
        elif n_high > 0:
            reject = "INSUFFICIENT_HIGH_COVERAGE"
            reject_alias = "INSUFFICIENT_RELIABLE_HIGH_DURATION"
            reason_copy = (
                "높은 음 구간은 확인됐지만, "
                "비교에 사용할 수 있는 구간이 충분하지 않았어요."
            )
        else:
            reject = "INSUFFICIENT_HIGH_COVERAGE"
            reject_alias = "INSUFFICIENT_HIGH_NOTE_COVERAGE"
            reason_copy = (
                "높은 음 구간은 확인됐지만, "
                "비교에 사용할 수 있는 구간이 충분하지 않았어요."
            )

        if mixed and reject not in ("INSUFFICIENT_PITCH_RANGE",):
            # Contamination can compound coverage failure; keep primary reason, note limitation
            pass

        # PARTIAL: at least one reliable high segment — expose observed high F0 only (no invented axes)
        partial_axes: dict[str, Any] = {}
        availability = "UNAVAILABLE"
        if (
            n_high >= 1
            and pitch_context.get("highest_reliable_f0_hz") is not None
            and reject != "INSUFFICIENT_PITCH_RANGE"
        ):
            availability = "PARTIAL"
            reason_copy = "고음 구간에서 일부 특징은 확인됐어요."
            partial_axes = {
                "observed_high_pitch": {
                    "status": "OBSERVED",
                    "summary": (
                        "이번 녹음에서 신뢰 가능하게 확인된 최고 음높이 "
                        f"{round(float(pitch_context['highest_reliable_f0_hz']))} Hz"
                    ),
                    "confidence_label": "low",
                }
            }
        pitch_context = {
            **pitch_context,
            "rejection_class": reject,
            "rejection_class_alias": reject_alias,
            "availability_level": availability,
        }
        return {
            "available": availability == "PARTIAL",
            "availability": availability,
            "reason": reject,
            "reason_alias": reject_alias,
            "reason_user": reason_copy,
            "pitch_context": pitch_context,
            "axes": partial_axes,
            "summary": [reason_copy] if availability == "PARTIAL" else [],
            "confidence_label": "low",
            "limitations": [
                "고음 구간 비교는 동일 녹음 내부 상대 비교이며 절대 음역 능력이 아니에요.",
            ],
        }

    conf = _conf_from_n(len(mid), len(high), mixed=mixed)
    limitations: list[str] = []
    if mixed:
        limitations.append("반주가 섞인 입력에서는 고음·음색 해석 신뢰도를 보수적으로 제한했어요.")
        if conf == "high":
            conf = "medium"
    limitations.append("고음 구간 비교는 동일 녹음 내부 상대 비교이며 절대 실력 점수가 아니에요.")

    # --- stability ---
    mid_drop = _dropout_mean(mid)
    high_drop = _dropout_mean(high)
    mid_rough = _rough_rate(mid)
    high_rough = _rough_rate(high)
    drop_delta = None
    if mid_drop is not None and high_drop is not None:
        drop_delta = float(high_drop - mid_drop)
    rough_delta = None
    if mid_rough is not None and high_rough is not None:
        rough_delta = float(high_rough - mid_rough)
    stab_status = "UNCERTAIN"
    stab_cont = None
    if drop_delta is not None or rough_delta is not None:
        degraded = (drop_delta or 0) > 0.12 or (rough_delta or 0) > 0.15
        preserved = (drop_delta or 0) <= 0.08 and (rough_delta or 0) <= 0.1
        if degraded:
            stab_status = "DEGRADED"
            stab_cont = 0.35
        elif preserved:
            stab_status = "PRESERVED"
            stab_cont = 0.72
        else:
            stab_status = "PRESERVED" if (drop_delta or 0) <= 0.1 else "DEGRADED"
            stab_cont = 0.55
    stability = _axis(
        status=stab_status,
        continuum=stab_cont,
        delta_from_mid=drop_delta,
        confidence_label=conf,
        summary=(
            "고음에서도 음높이와 진동이 비교적 안정적으로 유지됐어요."
            if stab_status == "PRESERVED"
            else (
                "고음으로 올라갈수록 음높이 연결과 진동 안정성이 일부 떨어졌어요."
                if stab_status == "DEGRADED"
                else "고음 안정성을 충분히 비교하지 못했어요."
            )
        ),
        provenance={
            "axis": "high_note_stability",
            "source_dimensions": ["phonation_regularity", "vibrato_control"],
            "evidence_families": ["dropout", "roughness_masked", "periodicity"],
        },
    )

    # --- transition continuity (register) ---
    reg = dimensions.get("register_configuration") or {}
    reg_status = (reg.get("status") or "UNKNOWN").upper()
    trans_eps = [
        e
        for e in episodes
        if (e.get("type") or e.get("episode_type") or "") == "REGISTER_TRANSITION"
    ]
    disc = 0
    for e in trans_eps:
        fm = e.get("feature_matrix") or {}
        cont = ((fm.get("register") or {}).get("f0_continuity") or "").lower()
        if cont in ("discontinuous", "dropout"):
            disc += 1
    if reg_status in ("UNKNOWN", "AMBIGUOUS") and not trans_eps:
        transition = _axis(
            status="UNCERTAIN",
            confidence_label="low",
            summary="성구 연결 연속성을 이번 녹음만으로 충분히 판단하지 못했어요.",
            provenance={
                "axis": "transition_continuity",
                "source_dimensions": ["register_configuration"],
                "evidence_families": ["f0_continuity", "register_shift"],
            },
        )
    elif disc >= 2 or reg_status in ("REPEATED_BREAK", "DISCONTINUOUS"):
        transition = _axis(
            status="DISCONTINUOUS",
            continuum=0.3,
            confidence_label=conf if conf != "high" else "medium",
            summary="성구가 바뀌는 구간에서 연결이 급해지는 패턴이 관찰됐어요.",
            provenance={
                "axis": "transition_continuity",
                "source_dimensions": ["register_configuration"],
                "evidence_families": ["f0_continuity", "register_shift"],
            },
        )
    else:
        transition = _axis(
            status="CONTINUOUS",
            continuum=0.7,
            confidence_label=conf,
            summary="성구 연결은 비교적 자연스러운 편으로 보여요.",
            provenance={
                "axis": "transition_continuity",
                "source_dimensions": ["register_configuration"],
                "evidence_families": ["f0_continuity", "register_shift"],
            },
        )

    # --- effort cost (reuse effort_like; LOUD != EFFORT already in engine) ---
    mid_eff = _effort_rate(mid, baseline)
    high_eff = _effort_rate(high, baseline)
    eff_delta = None
    if mid_eff is not None and high_eff is not None:
        eff_delta = float(high_eff - mid_eff)
    if high_eff is None:
        effort_axis = _axis(
            status="UNCERTAIN",
            confidence_label="low",
            summary="고음 effort 변화를 신뢰도 있게 비교하지 못했어요.",
        )
    elif eff_delta is not None and eff_delta >= 0.2:
        effort_axis = _axis(
            status="INCREASED",
            continuum=high_eff,
            delta_from_mid=eff_delta,
            confidence_label=conf,
            summary="고음으로 갈수록 힘이 더 증가하는 경향이 있어요.",
            provenance={
                "axis": "high_note_effort_cost",
                "source_dimensions": ["vocal_effort_strain"],
                "evidence_families": [
                    "intensity_trajectory",
                    "temporal_attack",
                    "recovery_persistence",
                ],
            },
        )
    elif eff_delta is not None and eff_delta <= -0.1:
        effort_axis = _axis(
            status="DECREASED",
            continuum=high_eff,
            delta_from_mid=eff_delta,
            confidence_label=conf,
            summary="고음에서 오히려 힘 증가가 두드러지지 않았어요.",
            provenance={
                "axis": "high_note_effort_cost",
                "source_dimensions": ["vocal_effort_strain"],
                "evidence_families": ["intensity_trajectory"],
            },
        )
    else:
        effort_axis = _axis(
            status="STABLE",
            continuum=high_eff,
            delta_from_mid=eff_delta,
            confidence_label=conf,
            summary="고음에서도 힘의 증가가 크지 않은 편이에요.",
            provenance={
                "axis": "high_note_effort_cost",
                "source_dimensions": ["vocal_effort_strain"],
                "evidence_families": ["intensity_trajectory"],
            },
        )
    effort_axis["mid_effort"] = mid_eff
    effort_axis["high_effort"] = high_eff
    effort_axis["delta"] = eff_delta

    # --- breathiness shift ---
    mid_br = _breath_rate(mid)
    high_br = _breath_rate(high)
    br_delta = None
    if mid_br is not None and high_br is not None:
        br_delta = float(high_br - mid_br)
    if high_br is None:
        breath_axis = _axis(status="UNCERTAIN", confidence_label="low", summary="고음 숨 섞임 변화를 판단하지 못했어요.")
    elif br_delta is not None and br_delta >= 0.18:
        breath_axis = _axis(
            status="INCREASED",
            continuum=high_br,
            delta_from_mid=br_delta,
            confidence_label=conf,
            summary="고음에서 숨이 섞이는 음질이 더 나타났어요.",
            provenance={
                "axis": "high_note_breathiness_shift",
                "source_dimensions": ["air_leakage_breathiness"],
                "evidence_families": ["h1h2_proxy", "tilt", "leakage_like"],
            },
        )
    elif br_delta is not None and br_delta <= -0.15:
        breath_axis = _axis(
            status="DECREASED",
            continuum=high_br,
            delta_from_mid=br_delta,
            confidence_label=conf,
            summary="고음에서 숨 섞임이 오히려 줄어드는 경향이 있어요.",
            provenance={
                "axis": "high_note_breathiness_shift",
                "source_dimensions": ["air_leakage_breathiness"],
                "evidence_families": ["leakage_like"],
            },
        )
    else:
        breath_axis = _axis(
            status="STABLE",
            continuum=high_br,
            delta_from_mid=br_delta,
            confidence_label=conf,
            summary="고음에서도 숨 섞임 변화는 크지 않았어요.",
            provenance={
                "axis": "high_note_breathiness_shift",
                "source_dimensions": ["air_leakage_breathiness"],
                "evidence_families": ["leakage_like"],
            },
        )
    breath_axis["delta"] = br_delta

    # --- regularity cost ---
    if high_rough is None:
        reg_cost = _axis(status="UNCERTAIN", confidence_label="low", summary="고음 규칙성 변화를 판단하지 못했어요.")
    elif rough_delta is not None and rough_delta >= 0.15:
        reg_cost = _axis(
            status="INCREASED",
            continuum=high_rough,
            delta_from_mid=rough_delta,
            confidence_label=conf,
            summary="고음에서 거칠거나 불규칙한 음질이 일부 증가했어요.",
            provenance={
                "axis": "high_note_regularity_cost",
                "source_dimensions": ["phonation_regularity"],
                "evidence_families": ["roughness", "periodicity", "dropout"],
            },
        )
    else:
        reg_cost = _axis(
            status="STABLE",
            continuum=high_rough,
            delta_from_mid=rough_delta,
            confidence_label=conf,
            summary="고음에서도 거칠거나 불규칙한 음질의 증가는 뚜렷하지 않았어요.",
            provenance={
                "axis": "high_note_regularity_cost",
                "source_dimensions": ["phonation_regularity"],
                "evidence_families": ["roughness", "periodicity"],
            },
        )

    # --- resonance preservation (multi-family) ---
    mid_e24 = _region_metric(mid, "energy_2_4k")
    high_e24 = _region_metric(high, "energy_2_4k")
    mid_e48 = _region_metric(mid, "energy_4_8k")
    high_e48 = _region_metric(high, "energy_4_8k")
    mid_cent = _region_metric(mid, "spectral_centroid_hz")
    high_cent = _region_metric(high, "spectral_centroid_hz")
    mid_tilt = _region_metric(mid, "spectral_tilt_db_per_oct")
    high_tilt = _region_metric(high, "spectral_tilt_db_per_oct")

    # Formant caution: only use if confidence ok
    formant_ok = 0
    formant_n = 0
    for s in high:
        fc = ((s.get("level2_proxies") or {}).get("formants") or {}).get("confidence")
        formant_n += 1
        if fc is not None and float(fc) >= 0.4:
            formant_ok += 1
    use_formant = formant_n > 0 and (formant_ok / formant_n) >= 0.4

    e24_d = (high_e24 - mid_e24) if mid_e24 is not None and high_e24 is not None else None
    e48_d = (high_e48 - mid_e48) if mid_e48 is not None and high_e48 is not None else None
    cent_d = (high_cent - mid_cent) if mid_cent is not None and high_cent is not None else None
    tilt_d = (high_tilt - mid_tilt) if mid_tilt is not None and high_tilt is not None else None

    families_agree_loss = 0
    families_agree_bright = 0
    fam_n = 0
    if e24_d is not None:
        fam_n += 1
        if e24_d <= -0.04:
            families_agree_loss += 1
        if e24_d >= 0.04:
            families_agree_bright += 1
    if e48_d is not None:
        fam_n += 1
        if e48_d <= -0.03:
            families_agree_loss += 1
        if e48_d >= 0.04:
            families_agree_bright += 1
    if cent_d is not None:
        fam_n += 1
        if cent_d >= 150:
            families_agree_bright += 1
        if cent_d <= -150:
            families_agree_loss += 1
    if tilt_d is not None:
        fam_n += 1
        # more negative tilt often darker / less bright presence
        if tilt_d <= -2.0:
            families_agree_loss += 1
        if tilt_d >= 2.0:
            families_agree_bright += 1

    if fam_n == 0:
        res_status = "UNCERTAIN"
        res_summary = "고음 공명·존재감 변화를 충분히 비교하지 못했어요."
    elif families_agree_loss >= 2 and e24_d is not None and e24_d <= -0.04:
        res_status = "PRESENCE_LOSS"
        res_summary = "고음에서 중역 존재감이 줄어드는 경향이 있어요."
    elif families_agree_bright >= 2 and (cent_d or 0) >= 200 and (e24_d or 0) >= 0.05:
        res_status = "EXCESS_BRIGHTENING_CANDIDATE"
        res_summary = "고음에서 밝기/고역 에너지가 상대적으로 커지는 경향이 있어요."
    elif families_agree_bright >= 1 and families_agree_loss == 0:
        res_status = "BRIGHTNESS_SHIFT"
        res_summary = "고음에서 밝기 쪽으로 음색이 일부 이동했어요."
    else:
        res_status = "PRESERVED"
        res_summary = "고음에서도 중역 존재감과 음색 균형이 비교적 유지됐어요."

    if not use_formant:
        limitations.append("고음에서는 formant 추정이 불안정할 수 있어 spectral-band 중심 비교를 우선했어요.")

    resonance = _axis(
        status=res_status,
        continuum=None if e24_d is None else max(0.0, min(1.0, 0.5 + float(e24_d) * 2)),
        delta_from_mid=e24_d,
        confidence_label="low" if fam_n < 2 else conf,
        summary=res_summary,
        provenance={
            "axis": "resonance_preservation",
            "source_dimensions": ["resonance_formant_strategy"],
            "evidence_families": [
                "energy_2_4k",
                "energy_4_8k",
                "spectral_centroid",
                "spectral_tilt",
            ]
            + (["formants"] if use_formant else []),
            "formant_used": use_formant,
        },
    )
    resonance["deltas"] = {
        "energy_2_4k": e24_d,
        "energy_4_8k": e48_d,
        "spectral_centroid_hz": cent_d,
        "spectral_tilt_db_per_oct": tilt_d,
    }

    axes = {
        "high_note_stability": stability,
        "transition_continuity": transition,
        "high_note_effort_cost": effort_axis,
        "high_note_breathiness_shift": breath_axis,
        "high_note_regularity_cost": reg_cost,
        "resonance_preservation": resonance,
    }

    summary = _compose_summaries(axes)
    return {
        "available": True,
        "availability": "FULL",
        "reason": None,
        "reason_user": None,
        "pitch_context": {**pitch_context, "availability_level": "FULL"},
        "axes": axes,
        "summary": summary,
        "confidence_label": conf,
        "limitations": limitations,
        "descriptive_only": True,
        "what_it_is_not": "고음 실력 점수 / 해부학 진단이 아닙니다.",
    }


def _compose_summaries(axes: dict[str, Any]) -> list[str]:
    eff = (axes.get("high_note_effort_cost") or {}).get("status")
    br = (axes.get("high_note_breathiness_shift") or {}).get("status")
    stab = (axes.get("high_note_stability") or {}).get("status")
    res = (axes.get("resonance_preservation") or {}).get("status")
    out: list[str] = []

    if stab == "PRESERVED" and eff == "INCREASED" and br in ("STABLE", None):
        out.append("고음 자체의 안정성은 유지되지만, 높은 음에서 힘이 더 증가하는 경향이 있어요.")
    elif eff in ("STABLE", "DECREASED") and br == "INCREASED":
        out.append("고음에서 힘이 크게 늘지는 않지만 숨이 섞이는 음질이 증가해요.")
    elif eff in ("STABLE", "DECREASED") and stab == "PRESERVED" and res == "PRESERVED":
        out.append("높은 음에서도 발성 상태와 음색이 비교적 안정적으로 유지돼요.")
    elif eff == "INCREASED" and res == "PRESENCE_LOSS":
        out.append("고음에서 힘이 증가하면서 중역 존재감이 함께 줄어드는 경향이 있어요.")
    else:
        for key in (
            "high_note_effort_cost",
            "high_note_stability",
            "high_note_breathiness_shift",
            "resonance_preservation",
        ):
            s = (axes.get(key) or {}).get("summary")
            if s:
                out.append(s)
            if len(out) >= 2:
                break
    return out[:3]
