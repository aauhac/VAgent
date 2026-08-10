"""
song_detail/report.py
---------------------
Assemble V3 Evidence-aware Song Detailed Report.
Does NOT change score math — only explanation / segments / UX payload.
"""

from __future__ import annotations

from typing import Any, Optional

from audio_analyzer.models import ANALYSIS_VERSION, public_audio

from .copy import (
    AREA_DISPLAY,
    confidence_state,
    coverage_state,
    submetric_display_name,
)
from .explain_v3 import (
    build_overall_assessment,
    build_submetric_views,
    collect_detail_priorities,
    collect_detail_strengths,
    explain_area,
)
from .segments import build_focus_segments_from_v3
from audio_analyzer.vocal_quality.report import build_vocal_quality_public
from audio_analyzer.vocal_function.report import build_vocal_function_public


SONG_DETAIL_REPORT_VERSION = "vocal-coach-report-v2.0"

_FORBIDDEN_KEYS = (
    "physiology_assessments",
    "diagnostic_metrics",
    "coaching_recommendations",
    "premium_report",
    "scientific_debug",
    "reliable_findings",
    "uncertain_findings",
    "evidence_families",
    "phonation_contact_pattern",
)


def _vibrato_public(optional: dict[str, Any]) -> dict[str, Any]:
    vib = (optional or {}).get("vibrato") or {}
    if not vib.get("available"):
        return {
            "available": False,
            "note": "이번 녹음에서는 참고용 비브라토 분석을 충분히 얻지 못했어요.",
        }
    # Normalize depth_cents (engine) vs legacy extent_cents
    depth = vib.get("depth_cents")
    if depth is None:
        depth = vib.get("extent_cents")
    rate = vib.get("rate_hz")
    out: dict[str, Any] = {
        "available": True,
        "note": "참고용 관측이며 실력 점수에 포함되지 않아요.",
        "depth_cents": depth,
        "rate_hz": rate,
    }
    lines = []
    if rate is not None:
        lines.append({"label": "비브라토 속도", "value": f"약 {float(rate):.1f} Hz"})
    if depth is not None:
        lines.append({"label": "깊이", "value": f"약 {float(depth):.1f} cents"})
    else:
        lines.append({"label": "깊이", "value": "측정 신뢰도가 충분하지 않음"})
    out["lines"] = lines
    # Do not expose blank extent placeholders
    return out


def _enrich_area(area: dict[str, Any]) -> dict[str, Any]:
    explained = explain_area(area)
    sub_views = build_submetric_views(area)
    # attach focus segments belonging to this area later in report assembly
    return {
        "area_id": area.get("area_id"),
        "display_name": area.get("display_name")
        or AREA_DISPLAY.get(area.get("area_id") or "", area.get("area_id")),
        "score": area.get("score"),
        "status": area.get("status"),
        "status_label": area.get("status_label")
        or ("판단 어려움" if area.get("status") == "unknown" else area.get("status")),
        "confidence": area.get("confidence"),
        "coverage": area.get("coverage"),
        "confidence_state": confidence_state(area.get("confidence")),
        "coverage_state": coverage_state(area.get("coverage")),
        "score_ceiling": area.get("score_ceiling"),
        "ceiling_reasons": area.get("ceiling_reasons") or [],
        "headline": explained["headline"],
        "interpretation": explained["interpretation"],
        "why_this_score": explained.get("why_this_score") or [],
        "strength_points": explained.get("strength_points") or [],
        "improvement_points": explained.get("improvement_points") or [],
        "submetrics": sub_views,
        "focus_segments": [],
        "practice": explained.get("practice") or {},
        "limitations": explained.get("limitations") or [],
        "temporal_summary": {
            "worst": (area.get("temporal") or {}).get("worst"),
            "bad_segment_ratio": (area.get("temporal") or {}).get("bad_segment_ratio"),
            "median": (area.get("temporal") or {}).get("median"),
        },
    }


def build_song_detailed_report(
    analysis: dict[str, Any],
    *,
    analysis_id: Optional[str] = None,
) -> dict[str, Any]:
    score = analysis.get("score") or {}
    quality = analysis.get("quality") or {}

    raw_areas = list(score.get("areas") or [])
    enriched_all = [_enrich_area(a) for a in raw_areas]
    # Main body: hide UNKNOWN axes (Z.1). Keep excluded note for footer.
    areas = [
        a
        for a in enriched_all
        if a.get("status") != "unknown" and a.get("score") is not None
    ]
    excluded_unknown = [
        {
            "area_id": a.get("area_id"),
            "display_name": a.get("display_name"),
            "reason": (a.get("interpretation") or "신뢰도 부족"),
        }
        for a in enriched_all
        if a.get("status") == "unknown" or a.get("score") is None
    ]
    # Debug-only: full area payload including unknown submetrics
    areas_debug = enriched_all

    legacy_timeline = list(analysis.get("timeline") or [])
    focus_segments = build_focus_segments_from_v3(
        score, legacy_timeline=legacy_timeline, max_total=5
    )
    # Focus segments only for reliable axes
    reliable_ids = {a.get("area_id") for a in areas}
    focus_segments = [e for e in focus_segments if e.get("area_id") in reliable_ids]

    # Attach per-area focus slices
    by_area: dict[str, list] = {}
    for ev in focus_segments:
        by_area.setdefault(ev.get("area_id") or "", []).append(ev)
    for a in areas:
        a["focus_segments"] = by_area.get(a["area_id"], [])[:2]

    overall = build_overall_assessment(score)
    strengths = collect_detail_strengths(areas)
    priorities = collect_detail_priorities(areas)

    # MAIN: Vocal Function Profile v2
    vf_raw = analysis.get("vocal_function_profile") or {}
    vocal_function = build_vocal_function_public(vf_raw)

    # Quality layer (v1) kept as secondary observations
    vq_raw = analysis.get("vocal_quality_profile") or {}
    vocal_quality = build_vocal_quality_public(vq_raw)

    # Merge focus: function segments first, then quality, then performance
    vf_focus = list(vocal_function.get("focus_segments") or [])
    vq_focus = list(vocal_quality.get("focus_segments") or [])
    perf_focus = focus_segments
    merged_focus = []
    seen_spans = set()
    for ev in vf_focus + vq_focus + perf_focus:
        key = (round(float(ev.get("start_sec") or 0), 1), round(float(ev.get("end_sec") or 0), 1))
        if key in seen_spans:
            continue
        seen_spans.add(key)
        merged_focus.append(ev)
        if len(merged_focus) >= 8:
            break

    # Performance supplement: only stability + dynamic_control
    performance_areas = [
        a
        for a in areas
        if a.get("area_id") in ("stability", "dynamic_control")
    ]

    headline_bits = list(
        (vocal_function.get("coaching_decision") or {}).get("headline")
        and [(vocal_function.get("coaching_decision") or {}).get("headline")]
        or vocal_function.get("headline")
        or vocal_quality.get("headline")
        or []
    )
    summary_text = (
        "오늘의 기능적 발성 코칭 요약이에요."
        if headline_bits
        else overall["text"]
    )
    if headline_bits:
        summary_text = summary_text + " " + " · ".join(str(h) for h in headline_bits[:2] if h)

    # Training from coaching decision first
    training: list[str] = list(vocal_function.get("training_plan") or [])
    for d in vocal_quality.get("dimensions") or []:
        for item in d.get("practice") or []:
            if item not in training:
                training.append(item)
    for p in priorities:
        if p.get("practice") and p["practice"] not in training:
            training.append(str(p["practice"]))
    training = training[:5]
    if not training:
        training = [
            "가벼운 SOVT로 편한 음을 짧게 유지해보세요.",
            "문제 구간을 낮은 음량으로 부드럽게 시작해 반복해보세요.",
        ]

    decision = vocal_function.get("coaching_decision") or {}
    unknown_footer = vocal_function.get("unknown_footer")

    limitations = [
        "이 분석은 음향 기반 기능 추정이며 해부학적/의학적 진단이 아닙니다.",
        "단단한 접촉 ≠ 잘못된 발성; effort/strain은 별도 축입니다.",
        "가창 참고 점수는 보조 정보입니다.",
    ]
    if quality.get("status") == "warn":
        limitations.append("녹음 품질 경고가 있어 일부 해석은 보수적으로 제한됐어요.")
    if unknown_footer:
        limitations.append(unknown_footer)
    if excluded_unknown:
        names = ", ".join(x.get("display_name") or x.get("area_id") for x in excluded_unknown)
        limitations.append(f"보조 가창 분석 중 {names}은(는) 제외했어요.")

    report: dict[str, Any] = {
        "report_kind": "song_detail",
        "report_version": SONG_DETAIL_REPORT_VERSION,
        "analysis_version": analysis.get("analysis_version", ANALYSIS_VERSION),
        "score_version": score.get("version"),
        "function_engine_version": vocal_function.get("engine_version"),
        "analysis_id": analysis_id or analysis.get("recording_id"),
        "tier": "song_detail",
        "summary": {
            "title": "오늘의 핵심",
            "text": summary_text,
            "overall": None,
            "label": None,
            "available": bool(
                vocal_function.get("available")
                or vocal_quality.get("available")
                or score.get("available")
            ),
            "overall_display_state": "SECONDARY",
            "reliable_axis_count": overall["reliable_axis_count"],
            "total_axis_count": overall["total_axis_count"],
        },
        "coaching_decision": decision,
        "vocal_function_profile": vocal_function,
        "vocal_quality_profile": vocal_quality,
        "high_note_events": vocal_function.get("high_note_events") or [],
        "coaching": vocal_function.get("coaching") or {},
        "additional_measurements": (vocal_function.get("coaching") or {}).get(
            "additional_measurement_suggestions"
        )
        or [],
        "performance_supplement": {
            "title": "보조 가창 분석",
            "note": "가창 참고 정보이며 메인 기능 코칭이 아닙니다.",
            "areas": performance_areas,
            "overall_reference": overall.get("internal_overall") or overall.get("display_overall"),
            "overall_display_state": overall["overall_display_state"],
        },
        "overall_assessment": overall,
        "areas": performance_areas,
        "excluded_unknown_areas": excluded_unknown,
        "areas_debug": areas_debug,
        "focus_segments": merged_focus,
        "timeline": [
            {
                "start_sec": e["start_sec"],
                "end_sec": e["end_sec"],
                "user_message": e.get("user_message") or e.get("headline"),
                "area_id": e.get("area_id"),
                "score": e.get("score"),
                "headline": e.get("headline"),
                "time_label": e.get("time_label"),
                "practice_hint": e.get("practice_hint"),
                "role": e.get("role"),
            }
            for e in merged_focus
        ],
        "strengths": strengths,
        "priority_issues": priorities,
        "vibrato": _vibrato_public(analysis.get("optional_analysis") or {}),
        "training_plan": training,
        "unknown_footer": unknown_footer,
        "recording_notes": list(analysis.get("analysis_notes") or [])[:8],
        "audio": public_audio(analysis.get("audio") or {}),
        "quality": {
            "status": quality.get("status"),
            "user_message": quality.get("user_message"),
            "confidence": quality.get("confidence"),
        },
        "limitations": limitations,
        "disclaimer": (
            "이 분석은 음향 기반 기능 추정이며 해부학적/의학적 진단이 아닙니다."
        ),
        "preview_available": bool(
            analysis.get("preview_path")
            or (analysis.get("audio") or {}).get("preview_path")
        ),
        "upgrade": {
            "title": "이 발성 경향을 더 신뢰도 있게 확인해 볼까요?",
            "body": (
                "짧은 표준 과제(아/이 지속음·사이렌·강약)로 "
                "노래에서 관찰된 발성 경향을 다시 검증할 수 있어요."
            ),
            "cta": "정밀 발성 진단으로 확인",
        },
    }

    for k in _FORBIDDEN_KEYS:
        report.pop(k, None)
    return report
