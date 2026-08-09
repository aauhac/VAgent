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


SONG_DETAIL_REPORT_VERSION = "song-detail-v1.1"

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
    areas = [_enrich_area(a) for a in raw_areas]

    legacy_timeline = list(analysis.get("timeline") or [])
    focus_segments = build_focus_segments_from_v3(
        score, legacy_timeline=legacy_timeline, max_total=5
    )

    # Attach per-area focus slices
    by_area: dict[str, list] = {}
    for ev in focus_segments:
        by_area.setdefault(ev.get("area_id") or "", []).append(ev)
    for a in areas:
        a["focus_segments"] = by_area.get(a["area_id"], [])[:2]

    overall = build_overall_assessment(score)
    strengths = collect_detail_strengths(areas)
    priorities = collect_detail_priorities(areas)

    # Training plan from priority practices
    training: list[str] = []
    for p in priorities:
        if p.get("practice"):
            training.append(str(p["practice"]))
    for a in areas:
        for item in (a.get("practice") or {}).get("items") or []:
            if item not in training:
                training.append(item)
    training = training[:5]
    if not training:
        training = ["편한 음 하나를 골라 짧게 반복하며, 가장 약한 세부 항목을 의식해 연습해 보세요."]

    limitations = [
        "이 리포트는 일반 노래 녹음의 음향 특성 분석입니다.",
        "표준 Diagnostic Task 기반 정밀 발성 진단이 아닙니다.",
        "성대 구조·질환·근육 상태를 진단하지 않습니다.",
        "점수는 베타 기준이며 개인 간 절대 비교용이 아닙니다.",
    ]
    if quality.get("status") == "warn":
        limitations.append("녹음 품질 경고가 있어 일부 해석은 보수적으로 제한됐어요.")
    if overall["overall_display_state"] == "PARTIAL":
        limitations.append(
            "일부 영역은 판단 보류라서 종합 점수를 부분 분석으로 안내했어요."
        )

    report: dict[str, Any] = {
        "report_kind": "song_detail",
        "report_version": SONG_DETAIL_REPORT_VERSION,
        "analysis_version": analysis.get("analysis_version", ANALYSIS_VERSION),
        "score_version": score.get("version"),
        "analysis_id": analysis_id or analysis.get("recording_id"),
        "tier": "song_detail",
        "summary": {
            "title": "이 노래의 상세 분석",
            "text": overall["text"],
            "overall": overall.get("display_overall"),
            "label": overall.get("label"),
            "available": bool(score.get("available")),
            "overall_display_state": overall["overall_display_state"],
            "reliable_axis_count": overall["reliable_axis_count"],
            "total_axis_count": overall["total_axis_count"],
        },
        "overall_assessment": overall,
        "areas": areas,
        "focus_segments": focus_segments,
        # Back-compat alias used by older UI
        "timeline": [
            {
                "start_sec": e["start_sec"],
                "end_sec": e["end_sec"],
                "user_message": e.get("user_message"),
                "area_id": e.get("area_id"),
                "score": e.get("score"),
                "headline": e.get("headline"),
                "time_label": e.get("time_label"),
                "practice_hint": e.get("practice_hint"),
            }
            for e in focus_segments
        ],
        "strengths": strengths,
        "priority_issues": priorities,
        "vibrato": _vibrato_public(analysis.get("optional_analysis") or {}),
        "training_plan": training,
        "recording_notes": list(analysis.get("analysis_notes") or [])[:8],
        "audio": public_audio(analysis.get("audio") or {}),
        "quality": {
            "status": quality.get("status"),
            "user_message": quality.get("user_message"),
            "confidence": quality.get("confidence"),
        },
        "limitations": limitations,
        "disclaimer": (
            "이 결과는 녹음된 음성의 음향적 특성을 바탕으로 "
            "발성 패턴을 분석한 연습 참고 정보입니다. "
            "성대의 실제 구조나 질환을 진단하는 검사가 아닙니다."
        ),
        "preview_available": bool(
            analysis.get("preview_path")
            or (analysis.get("audio") or {}).get("preview_path")
        ),
        "upgrade": {
            "title": "더 정밀하게 알고 싶나요?",
            "body": (
                "약 1~2분 Diagnostic Task로 발성 패턴·음역 전환·강도 협응·"
                "몸 사용 가이드를 추가로 분석할 수 있어요."
            ),
            "cta": "정밀 발성 진단으로 업그레이드",
        },
    }

    for k in _FORBIDDEN_KEYS:
        report.pop(k, None)
    return report
