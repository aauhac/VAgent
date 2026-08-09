"""
Deterministic Song Detailed Report — NOT physiology diagnostic.
Reuses existing analysis.json fields; no re-DSP.
"""

from __future__ import annotations

from typing import Any, Optional

from audio_analyzer.feedback.templates import build_template_feedback
from audio_analyzer.feedback.user_text import AREA_COPY
from audio_analyzer.models import ANALYSIS_VERSION, public_audio


SONG_DETAIL_REPORT_VERSION = "song-detail-v1.0"

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


def _area_wording(area: dict[str, Any]) -> tuple[str, str]:
    area_id = area.get("area_id") or ""
    copy = AREA_COPY.get(area_id, {})
    status = area.get("status")
    score = area.get("score")
    worst = (area.get("temporal") or {}).get("worst")
    if status == "unknown" or score is None:
        interpretation = "이번 녹음에서는 전체 점수를 확정하기 어려워요."
        practice = "조금 더 또렷한 녹음으로 다시 확인해 보세요."
        return interpretation, practice
    if score >= 95:
        interpretation = "이번 녹음에서 매우 안정적으로 측정됐어요."
    elif score >= 85:
        interpretation = (
            "대부분 안정적이지만 일부 구간에서 차이가 있었어요."
            if worst is not None and worst < 80
            else (copy.get("strength_feedback") or "비교적 좋은 편으로 측정됐어요.")
        )
    elif status in ("excellent", "good"):
        interpretation = copy.get("strength_feedback") or "비교적 좋은 편으로 측정됐어요."
    elif status == "needs_work":
        interpretation = copy.get("what_user_hears") or "개선 여지가 있어요."
    else:
        interpretation = copy.get("what_user_hears") or "보통 수준으로 측정됐어요."
    if status in ("excellent", "good") and score >= 78:
        practice = copy.get("keep_advice") or copy.get("practice") or ""
    else:
        practice = copy.get("practice") or ""
    return interpretation, practice


def _area_detail(area: dict[str, Any]) -> dict[str, Any]:
    interpretation, practice = _area_wording(area)
    submetrics = []
    for s in area.get("submetrics") or []:
        submetrics.append(
            {
                "submetric_id": s.get("submetric_id"),
                "display_name": s.get("display_name"),
                "score": s.get("score"),
                "status": s.get("status"),
            }
        )
    return {
        "area_id": area.get("area_id"),
        "display_name": area.get("display_name"),
        "score": area.get("score"),
        "status": area.get("status"),
        "status_label": area.get("status_label")
        or ("판단 어려움" if area.get("status") == "unknown" else area.get("status")),
        "confidence": area.get("confidence"),
        "coverage": area.get("coverage"),
        "interpretation": interpretation,
        "practice": practice,
        "submetrics": submetrics,
        "temporal_summary": {
            "worst": (area.get("temporal") or {}).get("worst"),
            "bad_segment_ratio": (area.get("temporal") or {}).get("bad_segment_ratio"),
        },
    }


def _timeline_public(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for ev in events[:12]:
        out.append(
            {
                "start_sec": ev.get("start_sec"),
                "end_sec": ev.get("end_sec"),
                "severity": ev.get("severity"),
                "user_message": ev.get("user_message") or ev.get("message"),
                "area_id": ev.get("area_id"),
            }
        )
    return out


def _vibrato_public(optional: dict[str, Any]) -> dict[str, Any]:
    vib = (optional or {}).get("vibrato") or {}
    if not vib.get("available"):
        return {
            "available": False,
            "note": "이번 녹음에서는 참고용 비브라토 분석을 충분히 얻지 못했어요.",
        }
    return {
        "available": True,
        "rate_hz": vib.get("rate_hz"),
        "extent_cents": vib.get("extent_cents"),
        "note": "참고용 관측이며 실력 점수에 포함되지 않아요.",
    }


def build_song_detailed_report(
    analysis: dict[str, Any],
    *,
    analysis_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Build song detailed report from stored analysis result.
    Must not include physiology / diagnostic inference.
    """
    score = analysis.get("score") or {}
    quality = analysis.get("quality") or {}
    feedback = build_template_feedback(analysis)

    areas = [_area_detail(a) for a in (score.get("areas") or [])]
    strengths = list(score.get("strengths") or analysis.get("strengths") or [])[:5]
    priority = list(score.get("priority_issues") or [])[:5]
    timeline = _timeline_public(list(analysis.get("timeline") or []))

    training = list(feedback.get("practice_plan") or [])[:5]
    limitations = [
        "이 리포트는 일반 노래 녹음의 음향 특성 분석입니다.",
        "표준 Diagnostic Task(아/이/사이렌/스웰) 기반 정밀 발성 진단이 아닙니다.",
        "성대 구조·질환·근육 상태를 진단하지 않습니다.",
        "점수는 베타 기준이며 개인 간 절대 비교용이 아닙니다.",
    ]
    if quality.get("status") == "warn":
        limitations.append("녹음 품질 경고가 있어 일부 해석은 보수적으로 제한됐어요.")

    report = {
        "report_kind": "song_detail",
        "report_version": SONG_DETAIL_REPORT_VERSION,
        "analysis_version": analysis.get("analysis_version", ANALYSIS_VERSION),
        "analysis_id": analysis_id or analysis.get("recording_id"),
        "tier": "song_detail",
        "summary": {
            "title": "이 노래의 상세 분석",
            "text": feedback.get("overall_summary")
            or analysis.get("short_summary")
            or "노래 발성 특성 상세 결과예요.",
            "overall": score.get("overall"),
            "label": score.get("label"),
            "available": bool(score.get("available")),
        },
        "areas": areas,
        "strengths": [
            {
                "area_id": s.get("area_id"),
                "display_name": s.get("display_name"),
                "score": s.get("score"),
                "status": s.get("status"),
                "note": (AREA_COPY.get(s.get("area_id") or {}) or {}).get(
                    "strength_feedback"
                ),
            }
            for s in strengths
        ],
        "priority_issues": [
            {
                "area_id": p.get("area_id"),
                "display_name": p.get("display_name"),
                "score": p.get("score"),
                "status": p.get("status"),
                "what_user_hears": (AREA_COPY.get(p.get("area_id") or {}) or {}).get(
                    "what_user_hears"
                ),
                "practice": (AREA_COPY.get(p.get("area_id") or {}) or {}).get("practice"),
            }
            for p in priority
        ],
        "timeline": timeline,
        "segment_feedback": feedback.get("segment_feedback") or [],
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

    # Hard strip any physiology keys if somehow present in source
    for k in _FORBIDDEN_KEYS:
        report.pop(k, None)

    return report
