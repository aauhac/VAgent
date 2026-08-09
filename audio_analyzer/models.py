"""
models.py
---------
VAgent analysis result schema helpers (v2).
"""

from __future__ import annotations

from typing import Any, Optional


ANALYSIS_VERSION = "2.0"


def empty_score_unavailable(reason: str = "quality_gate_failed") -> dict[str, Any]:
    return {
        "available": False,
        "version": "vocal-score-v2.0",
        "calibration_status": "uncalibrated",
        "overall": None,
        "label": None,
        "areas": [],
        "reason": reason,
    }


def public_result(result: dict[str, Any]) -> dict[str, Any]:
    """
    Strip internal-only raw feature dumps for API / miniapp responses.
    """
    score = result.get("score") or {}
    quality = result.get("quality") or {}
    optional = result.get("optional_analysis") or {}
    feedback = result.get("feedback")

    return {
        "analysis_version": result.get("analysis_version", ANALYSIS_VERSION),
        "recording_id": result.get("recording_id"),
        "analysis_status": result.get("analysis_status", "completed"),
        "feedback_status": result.get("feedback_status", "skipped"),
        "audio": result.get("audio", {}),
        "quality": {
            "status": quality.get("status"),
            "confidence": quality.get("confidence"),
            "reasons": quality.get("reasons", []),
            "metrics": quality.get("metrics", {}),
            "user_message": quality.get("user_message"),
        },
        "score": {
            "available": score.get("available", False),
            "version": score.get("version"),
            "calibration_status": score.get("calibration_status"),
            "overall": score.get("overall"),
            "label": score.get("label"),
            "areas": score.get("areas", []),
            "reason": score.get("reason"),
        },
        "optional_analysis": {
            "vibrato": optional.get("vibrato", {"available": False}),
        },
        "issues": result.get("issues", []),
        "timeline": result.get("timeline", []),
        "strengths": result.get("strengths", []),
        "analysis_notes": result.get("analysis_notes", []),
        "feedback": feedback,
        "preview_available": bool(result.get("preview_path")),
    }


def safe_float(value: Any, digits: int = 3) -> Optional[float]:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return round(f, digits)
