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

    reliable_axes = [
        a
        for a in areas
        if a.get("score") is not None and a.get("status") != "unknown"
    ]
    n_reliable = len(reliable_axes)
    show_overall = bool(score.get("available")) and n_reliable >= 3
    public_overall = score.get("overall") if show_overall else None
    public_label = score.get("label") if show_overall else None

    from audio_analyzer.vocal_quality.report import free_vocal_quality_teaser
    from audio_analyzer.vocal_function.report import free_function_teaser

    vf_profile = result.get("vocal_function_profile") or {}
    vf_teaser = free_function_teaser(vf_profile)
    vq_teaser = free_vocal_quality_teaser(result.get("vocal_quality_profile") or {})
    teaser = vf_teaser or vq_teaser

    short_summary = None
    if score.get("available") or teaser:
        parts = ["오늘의 발성 요약."]
        parts.extend(teaser)
        parts.append("자세한 발성 상태 프로필은 노래 상세 리포트에서 확인할 수 있어요.")
        short_summary = " ".join(parts)
    else:
        short_summary = quality.get("user_message") or "이번 녹음은 안정적으로 분석하기 어려워요."

    diagnostic_offer = None
    try:
        from audio_analyzer.diagnostic.planner import plan_from_song_analysis

        plan = plan_from_song_analysis({"vocal_function_profile": vf_profile})
        diagnostic_offer = plan.get("diagnostic_offer")
    except Exception:
        diagnostic_offer = None

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
            "overall": public_overall,
            "label": public_label,
            "overall_display_state": (
                "FULL"
                if show_overall
                else ("PARTIAL" if n_reliable == 2 else "UNAVAILABLE")
            ),
            "reliable_axis_count": n_reliable,
            "areas": area_summary,
            "best_area": strengths[0] if strengths else None,
            "focus_area": priority[0] if priority else None,
            "reason": score.get("reason"),
        },
        "short_summary": short_summary,
        "vocal_quality_teaser": teaser,
        "vocal_function_teaser": vf_teaser,
        "vocal_type_teaser": _free_vocal_type_teaser(vf_profile),
        "main_finding_teaser": _free_main_finding_teaser(vf_profile),
        "premium_available": True,
        "products_available": {
            "song_detail": True,
            "diagnostic": True,
        },
        # Back-compat field — prefer products_available / ProductCatalog
        "premium_cta": {
            "title": "정밀 발성 진단",
            "body": (
                "필요한 항목만 짧은 추가 녹음으로 "
                "더 정밀하게 확인할 수 있어요. "
                "노래 상세 리포트는 별도 상품입니다."
            ),
        },
        "song_detail_cta": {
            "title": "이 노래를 더 자세히 알고 싶나요?",
            "body": (
                "발성 프로필, 특징 구간 듣기, 음역별 구성, "
                "분석 신뢰도를 추가 녹음 없이 확인할 수 있어요."
            ),
        },
        "diagnostic_cta": {
            "title": "내 발성 자체를 더 정밀하게 알고 싶나요?",
            "body": (
                "노래만으로 구분하기 어려운 항목을 "
                "짧은 추가 녹음으로 다시 확인할 수 있어요."
            ),
        },
        "diagnostic_offer": diagnostic_offer,
        "disclaimer": (
            "이 결과는 녹음된 음성의 음향적 특성을 바탕으로 "
            "발성 패턴을 분석한 발성 분석 참고 정보입니다. "
            "성대의 실제 구조나 질환을 진단하는 검사가 아닙니다."
        ),
        "preview_available": bool(
            result.get("preview_path") or (result.get("audio") or {}).get("preview_path")
        ),
    }


def _free_vocal_type_teaser(vf_profile: dict[str, Any] | None) -> dict[str, Any]:
    """Additive free-tier vocal type/style card (no criteria / timeline)."""
    from audio_analyzer.coach_profile import build_vocal_type_public

    vf = vf_profile or {}
    raw = vf.get("vocal_type_profile") if isinstance(vf, dict) else None
    if not isinstance(raw, dict):
        raw = {}
    pub = build_vocal_type_public(raw)
    style = vf.get("vocal_style_profile") if isinstance(vf, dict) else None
    if not isinstance(style, dict):
        style = pub.get("vocal_style_profile") or {}
    hc = pub.get("head_chest") or {}
    sb = pub.get("source_balance") or {}
    balance_class = str(sb.get("balance_class") or "").upper()
    show_raw = sb.get("show_ratio")
    if show_raw is None:
        show_raw = hc.get("show_ratio")
    if show_raw is None:
        show_raw = balance_class not in ("CONFLICTED", "UNRESOLVED", "UNKNOWN")
    show_ratio = bool(show_raw) and hc.get("available") is not False and balance_class != "CONFLICTED"
    from audio_analyzer.coach_profile.public_presentation import apply_public_vocal_type_copy

    display_name = (
        (style.get("display_name") if isinstance(style, dict) else None)
        or pub.get("display_name")
    )
    description = (
        (style.get("description") if isinstance(style, dict) else None)
        or pub.get("description")
    )
    teaser = {
        "available": bool(pub.get("available") or (isinstance(style, dict) and style.get("available"))),
        "display_name": display_name,
        "description": description,
        "confidence": pub.get("confidence"),
        "confidence_label": pub.get("confidence_label"),
        "resolution_state": pub.get("resolution_state") or (
            "RESOLVED"
            if pub.get("available") and str(pub.get("base_type") or pub.get("type_id") or "") != "UNRESOLVED"
            else "INSUFFICIENT_EVIDENCE"
        ),
        "style_id": style.get("style_id") if isinstance(style, dict) else None,
        "type_id": pub.get("type_id"),
        "base_type": pub.get("base_type"),
        "head_chest": {
            "available": bool(show_ratio and hc.get("available")),
            "chest_ratio": hc.get("chest_ratio") if show_ratio else None,
            "head_ratio": hc.get("head_ratio") if show_ratio else None,
            "broad_label": hc.get("broad_label") or sb.get("label"),
            "show_ratio": show_ratio,
        },
        "source_balance": {
            "balance_class": sb.get("balance_class"),
            "label": sb.get("label"),
            "show_ratio": show_ratio,
            "chest_percent": sb.get("chest_percent") if show_ratio else None,
            "head_percent": sb.get("head_percent") if show_ratio else None,
        },
        "key_traits": (style.get("primary_traits") if isinstance(style, dict) else None)
        or (pub.get("key_traits") or [])[:2],
        "vocal_style_profile": style if isinstance(style, dict) else None,
    }
    return apply_public_vocal_type_copy(teaser)


def _free_main_finding_teaser(vf_profile: dict[str, Any] | None) -> dict[str, Any]:
    """Single primary finding for FREE — diagnosis copy only."""
    unresolved = {
        "state": "UNRESOLVED",
        "none": False,
        "title": "이번 녹음에서는 한 가지 문제를 핵심으로 정하기 어려웠어요.",
        "detail": "",
    }
    vf = vf_profile if isinstance(vf_profile, dict) else None
    if not vf:
        return dict(unresolved)
    if "coaching_decision" not in vf:
        return dict(unresolved)
    decision = vf.get("coaching_decision") or {}
    if not isinstance(decision, dict):
        return dict(unresolved)
    primary = decision.get("primary_bottleneck")
    if not primary:
        return {
            "state": "NONE",
            "none": True,
            "title": "이번 녹음에서는 두드러진 발성 문제는 보이지 않았어요.",
            "detail": "",
        }
    return {
        "state": "FOUND",
        "none": False,
        "id": primary.get("id"),
        "user_title": primary.get("user_title") or primary.get("summary"),
        "why": primary.get("why") or primary.get("summary") or "",
        "title": primary.get("user_title") or primary.get("summary"),
        "detail": primary.get("why") or "",
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
