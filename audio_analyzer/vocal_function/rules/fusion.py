"""Functional-state fusion rules (LEVEL 3). Firm ≠ strain."""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from audio_analyzer.vocal_function import config as cfg
from audio_analyzer.vocal_function.evidence.families import (
    effort_like,
    firmer_like,
    leakage_like,
    lighter_like,
)
from audio_analyzer.vocal_function.evidence.graph import evidence_node


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


def fuse_contact(segments: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [s for s in segments if s.get("valid")]
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

    light = [s for s in valid if lighter_like(s)]
    firm = [s for s in valid if firmer_like(s)]
    # continuum 0=light .. 1=firm
    score = None
    if light or firm:
        score = float(len(firm) / max(1, len(light) + len(firm)))
    status = "OBSERVED" if score is not None else "UNKNOWN"
    if score is None and len(valid) >= cfg.MIN_SEGMENTS_GLOBAL:
        status = "AMBIGUOUS"

    # GIF invalid majority → cap confidence
    gif_ok = sum(
        1
        for s in valid
        if ((s.get("level2_proxies") or {}).get("glottal_source") or {}).get("valid")
    )
    conf = "medium" if gif_ok >= 2 else "low"
    if gif_ok == 0:
        # harmonic/spectral only — still possible but capped
        if score is not None:
            conf = "low"
        else:
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
                confidence_cap="medium",
                grade="B",
                time_range=(s0["start_sec"], s0["end_sec"]),
                rule_id="CONTACT_FIRM_V2",
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
        prevalence=_prevalence(max(len(light), len(firm)), len(valid)),
        profile={
            "lighter_segments": len(light),
            "firmer_segments": len(firm),
            "continuum_0_light_1_firm": score,
            "good_bad": None,
        },
    )


def fuse_effort(
    segments: list[dict[str, Any]],
    *,
    baseline_obs: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    valid = [s for s in segments if s.get("valid")]
    hits = [s for s in valid if effort_like(s, baseline_obs)]
    firm_only = [s for s in valid if firmer_like(s) and not effort_like(s, baseline_obs)]

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

    # Critical product rule: firm alone != strain
    note_firm = ""
    if firm_only and not hits:
        note_firm = (
            "단단한 발성 상태는 일부 관찰됐지만, 과도한 effort와 일치하는 "
            "복합 증거는 뚜렷하지 않았어요."
        )

    graph = []
    if hits:
        s0 = hits[0]
        graph.append(
            evidence_node(
                observation_ids=[
                    "estimated_naq",
                    "periodicity_primary_db",
                    "onset_slope_db_per_sec",
                    "f0_frame_period_perturbation_proxy_percent",
                ],
                families=["glottal_flow", "periodicity", "temporal", "perturbation"],
                hypothesis="effort_strain_like_pattern",
                alternatives=[
                    "style-intentional intensity",
                    "mic proximity",
                    "register transition transient",
                ],
                confidence_cap="medium",
                grade="C",
                time_range=(s0["start_sec"], s0["end_sec"]),
                rule_id="EFFORT_V2",
            )
        )

    return _dim(
        "vocal_effort_strain",
        status=status,
        continuum=None,
        summary={
            "LOW": "안정",
            "OCCASIONAL": "일부 증가",
            "MODERATE": "중간",
            "REPEATED": "반복적인 과도 증가",
            "UNKNOWN": "UNKNOWN",
        }.get(status, status),
        meaning=note_firm
        or (
            "고음·강한 구간에서 과도한 vocal effort와 일치할 수 있는 "
            "복합 음향 패턴이 관찰됐어요."
            if hits
            else "과도한 effort와 일치하는 복합 패턴은 뚜렷하지 않았어요."
        ),
        cannot="실제 후두 근육 긴장·복압을 측정하지 않습니다.",
        evidence=graph,
        valid=valid,
        prevalence=_prevalence(len(hits), len(valid)),
        profile={
            "effort_hit_segments": len(hits),
            "firm_without_effort_segments": len(firm_only),
            "contact_vs_strain_note": "FIRM_CONTACT != STRAIN",
        },
        focus=[
            {
                "start_sec": s["start_sec"],
                "end_sec": s["end_sec"],
                "state": "effort_like",
                "headline": "힘이 과하게 들어간 소리 경향",
                "user_message": (
                    "접촉 관련 단단함과 함께 주기성·거친 음질·onset 중 "
                    "추가 징후가 동반됐어요."
                ),
                "limitation": "실제 목 근육 긴장을 직접 측정한 것은 아닙니다.",
            }
            for s in hits[:3]
        ],
    )


def fuse_leakage(segments: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [s for s in segments if s.get("valid")]
    hits = [s for s in valid if leakage_like(s)]
    if len(valid) < cfg.MIN_SEGMENTS_GLOBAL:
        status = "UNKNOWN"
    elif not hits:
        status = "LOW"
    elif len(hits) == 1:
        # single family / single segment cannot go HIGH
        status = "OCCASIONAL"
    elif len(hits) / len(valid) >= cfg.PREVALENCE_REPEATED:
        status = "HIGH"
    else:
        status = "MODERATE"

    return _dim(
        "air_leakage_breathiness",
        status=status,
        continuum=None,
        summary={
            "LOW": "낮은 편",
            "OCCASIONAL": "일부",
            "MODERATE": "중간",
            "HIGH": "반복",
            "UNKNOWN": "UNKNOWN",
        }.get(status, status),
        meaning=(
            "기류 누출이 많은 phonation과 일치할 수 있는 특징이 관찰됐어요."
            if hits
            else "기식성·누출 경향은 뚜렷하지 않았어요."
        ),
        cannot="실제 성문 틈·성대 접촉을 측정하지 않습니다.",
        evidence=[],
        valid=valid,
        prevalence=_prevalence(len(hits), len(valid)),
        focus=[
            {
                "start_sec": s["start_sec"],
                "end_sec": s["end_sec"],
                "state": "leakage_like",
                "headline": "기류 누출·기식성 경향",
                "user_message": "주기성·스펙트럼 단서가 함께 약한 구간이에요.",
                "limitation": "성대 접촉을 직접 측정한 것은 아닙니다.",
            }
            for s in hits[:3]
        ],
    )


def fuse_regularity(segments: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [s for s in segments if s.get("valid")]
    rough = []
    for s in valid:
        obs = s.get("observations") or {}
        if (obs.get("periodicity_primary_db") or 99) <= 6 or (
            obs.get("f0_frame_period_perturbation_proxy_percent") or 0
        ) >= 2.5:
            rough.append(s)
    if len(valid) < 2:
        status = "UNKNOWN"
    elif not rough:
        status = "STABLE"
    elif len(rough) == 1:
        status = "INTERMITTENT"
    else:
        status = "REPEATED_IRREGULAR"
    return _dim(
        "phonation_regularity",
        status=status,
        continuum=None,
        summary={
            "STABLE": "비교적 규칙적",
            "INTERMITTENT": "일부 구간 불규칙",
            "REPEATED_IRREGULAR": "반복적 불규칙",
            "UNKNOWN": "UNKNOWN",
        }.get(status, status),
        meaning=(
            "거칠고 불규칙한 음질 패턴이 일부 관찰됐어요. "
            "의도적 distortion일 수도 있어 잘못이라고 단정하지 않아요."
            if rough
            else "진동 규칙성은 비교적 유지되는 편이에요."
        ),
        cannot="병변·성대 상태를 진단하지 않습니다.",
        evidence=[],
        valid=valid,
        prevalence=_prevalence(len(rough), len(valid)),
    )


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
) -> dict[str, Any]:
    hidden = status in ("UNKNOWN", "AMBIGUOUS")
    # Negative/positive conclusions need enough segments to leave "low"
    if (
        confidence_label == "low"
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
