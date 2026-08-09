"""
feedback/formatter.py
---------------------
Compress analysis result into LLM-safe payload (no raw DSP dump).
"""

from __future__ import annotations

from typing import Any


def format_for_llm(analysis: dict[str, Any]) -> dict[str, Any]:
    score = analysis.get("score") or {}
    quality = analysis.get("quality") or {}

    areas = []
    for a in score.get("areas") or []:
        if a.get("status") == "unknown":
            continue
        areas.append(
            {
                "name": a.get("display_name"),
                "area_id": a.get("area_id"),
                "score": a.get("score"),
                "confidence": a.get("confidence"),
                "status": a.get("status"),
            }
        )

    strengths = [
        {"name": s.get("display_name"), "score": s.get("score"), "status": s.get("status")}
        for s in (score.get("strengths") or [])
    ]
    priority_issues = [
        {"name": p.get("display_name"), "score": p.get("score"), "status": p.get("status")}
        for p in (score.get("priority_issues") or [])
    ]

    timeline = [
        {
            "type": e.get("type"),
            "start_sec": e.get("start_sec"),
            "end_sec": e.get("end_sec"),
            "severity": e.get("severity"),
            "user_message": e.get("user_message"),
        }
        for e in (analysis.get("timeline") or [])[:8]
    ]

    unknown_notes = [
        f"{a.get('display_name')} 측정 신뢰도 부족 (unknown)"
        for a in score.get("areas") or []
        if a.get("status") == "unknown"
    ]

    return {
        "overall_score": score.get("overall"),
        "score_available": score.get("available", False),
        "score_label": score.get("label"),
        "score_version": score.get("version"),
        "calibration_status": score.get("calibration_status"),
        "areas": areas,
        "priority_issues": priority_issues,
        "strengths": strengths,
        "timeline": timeline,
        "quality_notes": {
            "status": quality.get("status"),
            "reasons": quality.get("reasons") or [],
            "user_message": quality.get("user_message"),
        },
        "analysis_notes": (analysis.get("analysis_notes") or []) + unknown_notes,
        "optional_vibrato": (analysis.get("optional_analysis") or {}).get("vibrato"),
    }
