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
        "version": "vocal-score-v3.0",
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
            "status_label": a.get("status_label"),
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
        "products_available": {
            "song_detail": True,
            "diagnostic": True,
        },
        # Back-compat field — prefer products_available / ProductCatalog
        "premium_cta": {
            "title": "정밀 발성 진단",
            "body": (
                "추가 Diagnostic Task로 발성 패턴을 더 정밀하게 분석할 수 있어요. "
                "노래 상세 리포트는 별도 상품입니다."
            ),
        },
        "song_detail_cta": {
            "title": "이 노래를 더 자세히 알고 싶나요?",
            "body": (
                "4개 영역 상세, 잘한 부분, 개선 우선순위, 구간 다시 듣기, "
                "맞춤 연습을 추가 녹음 없이 확인할 수 있어요."
            ),
        },
        "diagnostic_cta": {
            "title": "내 발성 자체를 더 정밀하게 알고 싶나요?",
            "body": (
                "아/이 지속음·사이렌·강약 변화 Task로 발성 패턴·음역 전환·"
                "강도 협응·몸 사용 가이드를 분석해요. 상세 리포트 포함."
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
