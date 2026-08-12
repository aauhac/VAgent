"""
vocal_quality/rules.py
----------------------
Dimension fusion rules. No single-metric HIGH conclusions.
"""

from __future__ import annotations

from typing import Any, Optional

from . import config as cfg
from .evidence import count_true_families, prevalence_label, segment_evidence_flags


def _conf_label(n_valid: int, n_hit: int, n_fam_med: float) -> str:
    if n_valid < cfg.MIN_SEGMENTS_FOR_GLOBAL:
        return "low"
    if n_hit >= cfg.MIN_SEGMENTS_FOR_HIGH and n_fam_med >= cfg.MIN_FAMILIES_FOR_HIGH:
        return "high" if n_valid >= 8 else "medium"
    if n_hit >= 2:
        return "medium"
    return "low"


def fuse_breathy(segments: list[dict[str, Any]]) -> dict[str, Any]:
    """Shared breathy families; ZERO positive ≠ LOW (needs negative coverage)."""
    from audio_analyzer.vocal_evidence.phonation_quality import classify_breathy_segment

    evaluable = []
    positives, negatives, insufficient = [], [], []
    for s in segments:
        c = classify_breathy_segment(s)
        if c["verdict"] == "INSUFFICIENT" and c.get("reason") == "no_vocal_presence":
            continue
        evaluable.append(s)
        if c["verdict"] == "POSITIVE":
            positives.append({**s, "families": (c.get("families") or {}).get("n_positive", 2), "flags": c})
        elif c["verdict"] == "NEGATIVE":
            negatives.append(s)
        else:
            insufficient.append(s)

    n_eval = len(evaluable)
    n_pos, n_neg = len(positives), len(negatives)
    ratio = n_pos / n_eval if n_eval else 0.0
    prev = prevalence_label(ratio, any_hit=bool(positives))

    if n_eval < cfg.MIN_SEGMENTS_FOR_GLOBAL:
        status = "UNKNOWN"
    elif n_pos >= cfg.MIN_SEGMENTS_FOR_HIGH and ratio >= cfg.PREVALENCE_REPEATED:
        status = "HIGH"
    elif n_pos >= 2 and ratio >= cfg.PREVALENCE_OCCASIONAL:
        status = "MODERATE"
    elif n_pos == 1:
        status = "INTERMITTENT"
    elif n_neg >= max(cfg.MIN_SEGMENTS_FOR_GLOBAL, int(0.5 * n_eval)) and n_pos == 0:
        status = "LOW"
    else:
        status = "UNKNOWN"

    fam_med = float(np_mean([h["families"] for h in positives])) if positives else 0.0
    meaning = (
        "숨이 섞이는 음질과 일치할 수 있는 음향 패턴이 관찰됐어요."
        if status in ("MODERATE", "HIGH", "INTERMITTENT")
        else (
            "숨이 섞이는 음질 경향은 뚜렷하지 않았어요."
            if status == "LOW"
            else "이번 녹음에서는 기식성 경향을 충분히 판단하지 못했어요."
        )
    )
    return _dim(
        "breathy_like",
        status,
        prev,
        evaluable,
        positives,
        fam_med,
        summary=_breathy_summary(status, prev, n_pos, n_eval),
        meaning=meaning,
        cannot="실제 성대 접촉·성문 상태를 직접 측정한 것은 아닙니다.",
        practice=[],  # observation provider — no corrective training authority
    )


def fuse_pressed(segments: list[dict[str, Any]], breathy_hits: int) -> dict[str, Any]:
    valid = [s for s in segments if s.get("valid")]
    hits = []
    for s in valid:
        flags = segment_evidence_flags(s)["pressed"]
        # Need spectral/harmonic + (periodicity OR temporal) — still ≥2 families
        n_fam = count_true_families(flags)
        spectral = flags.get("spectral_or_harmonic")
        other = flags.get("periodicity") or flags.get("temporal_or_onset")
        if spectral and other and n_fam >= 2:
            hits.append({**s, "families": n_fam, "flags": flags})
        elif n_fam >= 2 and spectral:
            hits.append({**s, "families": n_fam, "flags": flags})

    # Contradiction with strong breathy
    breathy_ratio = breathy_hits / len(valid) if valid else 0.0
    pressed_ratio = len(hits) / len(valid) if valid else 0.0
    if (
        breathy_ratio >= cfg.PREVALENCE_OCCASIONAL
        and pressed_ratio >= cfg.PREVALENCE_OCCASIONAL
        and len(hits) >= 2
        and breathy_hits >= 2
    ):
        return _dim(
            "pressed_like",
            "AMBIGUOUS",
            "unknown",
            valid,
            hits,
            0.0,
            summary=(
                "숨 섞임 경향과 단단한 음질 경향 증거가 함께 나타나 이번 녹음에서는 "
                "단단하고 강한 음질을 확정하지 않았어요."
            ),
            meaning="상충하는 음질 단서가 있어 보수적으로 보류했어요.",
            cannot="목 근육 긴장이나 후두 상태를 측정한 것은 아닙니다.",
            practice=[],
        )

    ratio = pressed_ratio
    prev = prevalence_label(ratio, any_hit=bool(hits))
    if len(valid) < cfg.MIN_SEGMENTS_FOR_GLOBAL:
        status = "UNKNOWN"
    elif not hits:
        status = "LOW"
    elif len(hits) == 1:
        status = "INTERMITTENT"
    elif ratio >= cfg.PREVALENCE_REPEATED and len(hits) >= cfg.MIN_SEGMENTS_FOR_HIGH:
        status = "HIGH"
    elif ratio >= cfg.PREVALENCE_OCCASIONAL:
        status = "MODERATE"
    else:
        status = "INTERMITTENT"
    fam_med = float(np_mean([h["families"] for h in hits])) if hits else 0.0
    return _dim(
        "pressed_like",
        status,
        prev,
        valid,
        hits,
        fam_med,
        summary=_pressed_summary(status, prev, len(hits), len(valid)),
        meaning=(
            "일부 구간에서 단단하고 강한 음질과 일치할 수 있는 "
            "음향 패턴이 관찰됐어요."
            if status in ("MODERATE", "HIGH", "INTERMITTENT")
            else "단단하고 강한 음질 경향은 뚜렷하지 않았어요."
        ),
        cannot="실제 목 근육 긴장이나 후두 상태를 측정한 것은 아닙니다.",
        practice=[],
    )


def fuse_rough(segments: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [s for s in segments if s.get("valid")]
    hits = []
    for s in valid:
        flags = segment_evidence_flags(s)["rough"]
        # Require irregularity-specific evidence — CPP/periodicity alone rejected
        if flags.get("irregularity") and (
            flags.get("periodicity_loss") or flags.get("periodicity")
        ):
            hits.append({**s, "families": 2, "flags": flags})
        elif flags.get("irregularity") and flags.get("temporal"):
            hits.append({**s, "families": 1, "flags": flags})
    ratio = len(hits) / len(valid) if valid else 0.0
    prev = prevalence_label(ratio, any_hit=bool(hits))
    if len(valid) < cfg.MIN_SEGMENTS_FOR_GLOBAL:
        status = "UNKNOWN"
    elif not hits:
        status = "LOW"
    elif len(hits) == 1:
        status = "INTERMITTENT"
    elif ratio >= cfg.PREVALENCE_REPEATED and len(hits) >= 3:
        status = "HIGH"
    elif len(hits) >= 2:
        status = "MODERATE"
    else:
        status = "INTERMITTENT"
    return _dim(
        "rough_like",
        status,
        prev,
        valid,
        hits,
        1.0 if hits else 0.0,
        summary=_rough_summary(status, len(hits), len(valid)),
        meaning=(
            "일부 구간에서 불규칙한 진동과 일치할 수 있는 패턴이 관찰됐어요."
            if hits
            else "거칠고 불규칙한 음질 경향은 뚜렷하지 않았어요."
        ),
        cannot="성대 병변 여부를 판단하지 않습니다.",
        # Observation-only — not corrective coaching authority
        practice=[],
    )


def fuse_resonance(segments: list[dict[str, Any]], acoustic: dict[str, Any]) -> dict[str, Any]:
    valid = [s for s in segments if s.get("valid")]
    cents = [
        float((s.get("observations") or {}).get("spectral_centroid_hz"))
        for s in valid
        if (s.get("observations") or {}).get("spectral_centroid_hz") is not None
    ]
    tilts = [
        float((s.get("observations") or {}).get("spectral_tilt_db_per_oct"))
        for s in valid
        if (s.get("observations") or {}).get("spectral_tilt_db_per_oct") is not None
    ]
    if len(valid) < 2 or (not cents and not tilts):
        return _dim(
            "resonance_timbre",
            "UNKNOWN",
            "unknown",
            valid,
            [],
            0.0,
            summary="이번 녹음에서는 공명·음색 프로필을 신뢰도 있게 만들지 못했어요.",
            meaning="",
            cannot="인두·비강·후두 위치 같은 해부학적 상태를 측정하지 않습니다.",
            practice=[],
            extra={"profile": {}},
        )
    med_c = float(np_mean(cents)) if cents else None
    med_t = float(np_mean(tilts)) if tilts else None
    if med_c is not None:
        if med_c >= cfg.CENTROID_BRIGHT:
            brightness = "밝은 편"
        elif med_c <= cfg.CENTROID_DARK:
            brightness = "어두운 편"
        else:
            brightness = "중간"
    else:
        brightness = "판단 어려움"
    mid_presence = "보통"
    wg = acoustic.get("weight_gap_db")
    if wg is not None:
        if float(wg) > 10:
            mid_presence = "낮은 편"
        elif float(wg) < 2:
            mid_presence = "높은 편"
    upper = "보통"
    if med_t is not None:
        if float(med_t) <= -16:
            upper = "낮은 편"
        elif float(med_t) >= -8:
            upper = "유지되는 편"
    consistency = "중간"
    if cents and len(cents) >= 3:
        cv = float(np_std(cents) / (abs(med_c) + 1e-6)) if med_c else 0
        consistency = "낮은 편" if cv > 0.25 else ("높은 편" if cv < 0.12 else "중간")
    profile = {
        "brightness": brightness,
        "mid_presence": mid_presence,
        "upper_harmonic_presence": upper,
        "spectral_tilt_label": upper,
        "resonance_consistency": consistency,
        "note": "음색 특성 설명이며 좋고 나쁨을 의미하지 않습니다.",
    }
    summary = (
        f"밝기: {brightness}. 중역 존재감: {mid_presence}. "
        f"고역 배음: {upper}. 구간 일관성: {consistency}."
    )
    return _dim(
        "resonance_timbre",
        "MODERATE",
        "repeated" if len(valid) >= 4 else "occasional",
        valid,
        valid[:3],
        2.0,
        summary=summary,
        meaning="공명·음색 프로필은 음색 특성 설명이며 실력 점수가 아닙니다.",
        cannot="인두 공간·비강 공명·후두 위치를 측정하지 않습니다.",
        practice=[],
        extra={"profile": profile},
        status_is_profile=True,
    )


def fuse_onset(segments: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [s for s in segments if s.get("valid")]
    slopes = []
    ests = []
    for s in valid:
        o = s.get("observations") or {}
        if o.get("onset_slope_db_per_sec") is not None:
            slopes.append(float(o["onset_slope_db_per_sec"]))
        if o.get("periodicity_establishment_ratio") is not None:
            ests.append(float(o["periodicity_establishment_ratio"]))
    if len(slopes) < 2:
        return _dim(
            "onset_behavior",
            "UNKNOWN",
            "unknown",
            valid,
            [],
            0.0,
            summary="발성 시작 특성을 충분히 관찰하지 못했어요.",
            meaning="",
            cannot="성대 접촉 시작(glottal attack)을 직접 측정하지 않습니다.",
            practice=[],
        )
    med = float(np_mean(slopes))
    # Require slope + establishment agreement for ABRUPT
    abrupt_votes = sum(1 for x in slopes if x >= cfg.PRESSED_ONSET_ABRUPT)
    soft_votes = sum(1 for x in slopes if x < 40.0)
    est_med = float(np_mean(ests)) if ests else None
    if abrupt_votes >= 2 and (est_med is None or est_med < 0.55):
        # establishment alone insufficient; need slope repetition
        status = "ABRUPT_LIKE"
        summary = "일부 시작이 급하게 형성되는 음향 패턴이 반복됐어요."
    elif soft_votes >= max(2, len(slopes) // 2):
        status = "SOFT_LIKE"
        summary = "발성 시작이 대체로 부드럽게 형성되는 편이었어요."
    else:
        status = "BALANCED_LIKE"
        summary = "발성 시작 특성은 전반적으로 균형에 가까웠어요."
    # single metric guard: if only one abrupt slope → not ABRUPT_LIKE
    if abrupt_votes == 1 and status == "ABRUPT_LIKE":
        status = "BALANCED_LIKE"
        summary = "급격한 시작이 한 번만 관찰되어 확정하지 않았어요."
    hits = [s for s in valid if (s.get("observations") or {}).get("onset_slope_db_per_sec", 0) >= cfg.PRESSED_ONSET_ABRUPT]
    return _dim(
        "onset_behavior",
        status,
        prevalence_label(abrupt_votes / len(slopes), any_hit=abrupt_votes > 0),
        valid,
        hits,
        1.5 if ests else 1.0,
        summary=summary,
        meaning="소리 시작이 급하게 또는 부드럽게 형성되는 음향 패턴 설명입니다.",
        cannot="성대 접촉 시작을 직접 측정한 것은 아닙니다.",
        practice=[],
    )


def fuse_transition(segments: list[dict[str, Any]], pitch: dict[str, Any]) -> dict[str, Any]:
    """Detect large F0 jumps with periodicity/spectral disruption."""
    frames = pitch.get("frame_f0") or []
    events = []
    prev_hz = None
    prev_t = None
    for fr in frames:
        t = fr.get("time_sec")
        hz = fr.get("f0_hz")
        if t is None:
            continue
        t = float(t)
        if hz is None:
            if prev_t is not None and (t - prev_t) >= cfg.TRANSITION_DROPOUT_GAP_SEC:
                events.append({"start_sec": prev_t, "end_sec": t, "kind": "dropout"})
            prev_hz = None
            prev_t = t
            continue
        hz = float(hz)
        if prev_hz and prev_hz > 0:
            cents = abs(1200.0 * np_log2(hz / prev_hz))
            if cents >= cfg.TRANSITION_F0_JUMP_CENTS:
                # find overlapping segment validity
                events.append(
                    {
                        "start_sec": prev_t if prev_t is not None else t,
                        "end_sec": min(t + 0.5, t + 1.0),
                        "kind": "jump",
                        "cents": cents,
                    }
                )
        prev_hz = hz
        prev_t = t

    valid = [s for s in segments if s.get("valid")]
    # Attach disruption if nearby segment has low periodicity
    disrupted = []
    for ev in events:
        for s in valid:
            if s["start_sec"] <= ev["start_sec"] <= s["end_sec"] or s["start_sec"] <= ev["end_sec"] <= s["end_sec"]:
                per = (s.get("observations") or {}).get("periodicity_primary_db")
                if per is not None and float(per) < cfg.BREATHY_CPP_LOW + 2:
                    disrupted.append({**s, "event": ev})
                    break
                if ev.get("kind") == "dropout":
                    disrupted.append({**s, "event": ev})
                    break

    if len(valid) < 2 or not frames:
        status = "UNKNOWN"
        summary = "음역 전환 특성을 충분히 관찰하지 못했어요."
    elif not events:
        status = "SMOOTH"
        summary = "큰 음역 전환에서 뚜렷한 붕괴 패턴은 관찰되지 않았어요."
    elif len(disrupted) == 0:
        status = "SMOOTH"
        summary = "음역 변화는 있었지만 주기성 붕괴는 뚜렷하지 않았어요."
    elif len(disrupted) == 1:
        status = "MILD_DISRUPTION"
        summary = "음역 전환 1개 구간에서 주기성·스펙트럼 변화가 크게 나타났어요."
    else:
        status = "BREAK_LIKE"
        summary = (
            f"음역 전환 {len(disrupted)}개 구간에서 "
            "주기성이 잠시 떨어지거나 소리가 흔들리는 패턴이 관찰됐어요."
        )
    return _dim(
        "register_transition",
        status,
        prevalence_label(len(disrupted) / max(1, len(valid)), any_hit=bool(disrupted)),
        valid,
        disrupted,
        2.0 if disrupted else 1.0,
        summary=summary,
        meaning="음역이 바뀌는 구간의 음향 변화 설명이며 pitch accuracy 평가가 아닙니다.",
        cannot="TA/CT 전환이나 레지스터 생리를 직접 측정하지 않습니다.",
        practice=[],
    )


def _breathy_summary(status, prev, n_hit, n_valid):
    if status == "UNKNOWN":
        return "이번 녹음에서는 숨 섞임 경향을 신뢰도 있게 판단하지 못했어요."
    if status == "LOW":
        return "숨이 섞이는 음질 경향은 낮게 관찰됐어요."
    return (
        f"{cfg.PREVALENCE_LABELS.get(prev, prev)} — "
        f"{n_hit}/{n_valid}개 구간에서 주기성이 약해지고 "
        "노이즈 성분이 상대적으로 증가하는 패턴이 반복됐어요."
    )


def _pressed_summary(status, prev, n_hit, n_valid):
    if status == "UNKNOWN":
        return "이번 녹음에서는 단단하고 강한 음질 경향을 신뢰도 있게 판단하지 못했어요."
    if status == "AMBIGUOUS":
        return "상충하는 단서로 단단하고 강한 음질 경향을 확정하지 않았어요."
    if status == "LOW":
        return "단단하고 강한 음질 경향은 뚜렷하지 않았어요."
    return (
        f"{cfg.PREVALENCE_LABELS.get(prev, prev)} — "
        f"{n_hit}/{n_valid}개 강한 음 구간에서 고역 배음·에너지와 "
        "단단한 시작 패턴이 함께 관찰됐어요."
    )


def _rough_summary(status, n_hit, n_valid):
    if status == "UNKNOWN":
        return "거친 음질 경향을 판단하기 어려웠어요."
    if status == "LOW":
        return "거칠고 불규칙한 음질 경향은 뚜렷하지 않았어요."
    if status == "INTERMITTENT":
        return f"일부 구간({n_hit}/{n_valid})에서만 주기성이 일시적으로 크게 떨어졌어요."
    return f"{n_hit}/{n_valid}개 구간에서 불규칙한 주기성 패턴이 반복됐어요."


def _dim(
    dimension_id: str,
    status: str,
    prevalence: str,
    valid: list,
    hits: list,
    fam_med: float,
    *,
    summary: str,
    meaning: str,
    cannot: str,
    practice: list,
    extra: Optional[dict] = None,
    status_is_profile: bool = False,
) -> dict[str, Any]:
    conf = _conf_label(len(valid), len(hits), fam_med)
    focus = []
    for h in hits[:3]:
        focus.append(
            {
                "area_id": dimension_id,
                "start_sec": h.get("start_sec"),
                "end_sec": h.get("end_sec"),
                "state": status,
                "headline": cfg.DIMENSION_DISPLAY.get(dimension_id, dimension_id),
                "user_message": summary,
                "evidence_summary": f"families≈{h.get('families', fam_med)}",
                "confidence_label": conf,
                "what_user_may_hear": meaning,
                "limitation": cannot,
                "practice_hint": practice[0] if practice else None,
                "time_label": _mmss(h.get("start_sec"), h.get("end_sec")),
            }
        )
    out = {
        "dimension_id": dimension_id,
        "display_name": cfg.DIMENSION_DISPLAY.get(dimension_id, dimension_id),
        "status": status,
        "status_label": cfg.STATUS_LABELS.get(status, status),
        "prevalence": prevalence,
        "prevalence_label": cfg.PREVALENCE_LABELS.get(prevalence, prevalence),
        "confidence_label": conf,
        "coverage": round(len(valid) / max(1, len(valid) or 1), 3),
        "valid_segment_count": len(valid),
        "hit_segment_count": len(hits),
        "summary": summary,
        "observations": [
            f"valid_segments={len(valid)}",
            f"hit_segments={len(hits)}",
        ],
        "focus_segments": focus,
        "what_it_may_mean": meaning,
        "what_we_cannot_know": cannot,
        "practice": practice,
        "hidden": status in ("UNKNOWN", "AMBIGUOUS") and not status_is_profile,
    }
    if extra:
        out.update(extra)
    return out


def np_mean(xs):
    import numpy as np

    return float(np.mean(xs)) if xs else 0.0


def np_std(xs):
    import numpy as np

    return float(np.std(xs)) if xs else 0.0


def np_log2(x):
    import numpy as np

    return float(np.log2(x))


def _mmss(a, b):
    def f(x):
        if x is None:
            return "—"
        s = max(0, int(float(x)))
        return f"{s // 60:02d}:{s % 60:02d}"

    return f"{f(a)}–{f(b)}"
