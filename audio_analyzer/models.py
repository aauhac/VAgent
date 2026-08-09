"""
models.py
---------
VAgent analysis result schema helpers (v2) + FREE/PREMIUM separation.
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


def public_audio(audio: dict[str, Any] | None) -> dict[str, Any]:
    audio = audio or {}
    sep = audio.get("separation") or {}
    return {
        "duration_sec": audio.get("duration_sec"),
        "sample_rate": audio.get("sample_rate"),
        "source_mode": audio.get("source_mode"),
        "separation": {"used": bool(sep.get("used", False))},
    }


def free_public_result(result: dict[str, Any]) -> dict[str, Any]:
    """
    FREE Song Analysis payload.

    Must NOT include physiology, diagnostic metrics, detailed coaching,
    detailed timeline, or premium evidence.
    """
    score = result.get("score") or {}
    quality = result.get("quality") or {}
    areas = list(score.get("areas") or [])
    strengths = list(score.get("strengths") or [])[:1]
    priority = list(score.get("priority_issues") or [])[:1]

    # Compact area summary only (scores/status) — no deep evidence dumps required
    area_summary = [
        {
            "area_id": a.get("area_id"),
            "display_name": a.get("display_name"),
            "score": a.get("score"),
            "status": a.get("status"),
            "confidence": a.get("confidence"),
        }
        for a in areas
    ]

    short_summary = None
    if score.get("available"):
        best = strengths[0]["display_name"] if strengths else None
        focus = priority[0]["display_name"] if priority else None
        parts = [f"종합 {score.get('overall')}점, {score.get('label')}이에요."]
        if best:
            parts.append(f"특히 {best}이(가) 좋아요.")
        if focus:
            parts.append(f"먼저 보면 좋은 영역은 {focus}이에요.")
        parts.append("베타 분석 점수이며, 상세 발성 진단은 별도 표준화 Task로 진행해요.")
        short_summary = " ".join(parts)
    else:
        short_summary = quality.get("user_message") or "정확한 분석이 어려운 녹음이에요."

    return {
        "analysis_version": result.get("analysis_version", ANALYSIS_VERSION),
        "analysis_mode": "song",
        "recording_id": result.get("recording_id"),
        "analysis_status": result.get("analysis_status", "completed"),
        "feedback_status": "skipped",
        "tier": "free",
        "audio": public_audio(result.get("audio") or {}),
        "quality": {
            "status": quality.get("status"),
            "confidence": quality.get("confidence"),
            "reasons": quality.get("reasons", []),
            "codes": quality.get("codes", []),
            "metrics": {
                k: (quality.get("metrics") or {}).get(k)
                for k in (
                    "duration_sec",
                    "rms_dbfs",
                    "silent_ratio",
                    "voiced_ratio",
                    "voiced_duration_sec",
                    "clipping_ratio",
                )
            },
            "user_message": quality.get("user_message"),
        },
        "score": {
            "available": score.get("available", False),
            "version": score.get("version"),
            "calibration_status": score.get("calibration_status"),
            "overall": score.get("overall"),
            "label": score.get("label"),
            "areas": area_summary,
            "best_area": strengths[0] if strengths else None,
            "focus_area": priority[0] if priority else None,
            "reason": score.get("reason"),
        },
        "short_summary": short_summary,
        "premium_available": True,
        "premium_cta": {
            "title": "상세 발성 진단 영구 해제",
            "body": (
                "표준화된 짧은 Diagnostic Task로 발성 메커니즘 경향을 추정하고 "
                "실제 몸 사용 코칭을 제공해요. 한 번 완료한 상세 리포트는 계속 확인할 수 있어요."
            ),
        },
        "disclaimer": (
            "이 결과는 녹음된 음성의 음향적 특성을 바탕으로 "
            "발성 패턴을 분석한 연습 참고 정보입니다. "
            "성대의 실제 구조나 질환을 진단하는 검사가 아닙니다."
        ),
        "preview_available": bool(
            result.get("preview_path") or (result.get("audio") or {}).get("preview_path")
        ),
    }


def public_result(result: dict[str, Any]) -> dict[str, Any]:
    """Default public API for song analyses = FREE payload."""
    return free_public_result(result)


def safe_float(value: Any, digits: int = 3) -> Optional[float]:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f:
        return None
    return round(f, digits)
