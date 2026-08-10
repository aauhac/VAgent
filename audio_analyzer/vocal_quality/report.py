"""
vocal_quality/report.py
-----------------------
User-facing Vocal Quality slices for Song Detail / Free summary.
"""

from __future__ import annotations

from typing import Any

from . import config as cfg
from .engine import excluded_dimensions, public_dimensions, strip_scientific_debug


_AFFIRMATIVE_KEYS = (
    "summary",
    "status_label",
    "prevalence_label",
    "what_it_may_mean",
    "user_message",
    "headline",
    "what_user_may_hear",
    "practice_hint",
    "evidence_summary",
)


def affirmative_copy_blob(dims: list[dict[str, Any]], headline: Any = None) -> str:
    """User-facing claim text only (excludes boundary / cannot-know disclaimers)."""
    chunks: list[str] = []
    if headline is not None:
        chunks.append(str(headline))
    for d in dims:
        for key in _AFFIRMATIVE_KEYS:
            if key in d and d[key] is not None:
                chunks.append(str(d[key]))
        for item in d.get("practice") or []:
            chunks.append(str(item))
        for fs in d.get("focus_segments") or []:
            for key in _AFFIRMATIVE_KEYS:
                if key in fs and fs[key] is not None:
                    chunks.append(str(fs[key]))
    return " ".join(chunks)


def assert_no_banned_wording(blob: str) -> None:
    for banned in cfg.BANNED_USER_SUBSTRINGS:
        if banned in blob:
            raise AssertionError(f"banned medical/anatomy wording: {banned}")


def build_vocal_quality_public(profile: dict[str, Any]) -> dict[str, Any]:
    if not profile or not profile.get("available"):
        return {
            "available": False,
            "headline": ["발성 상태 분석을 제공하지 못했어요."],
            "dimensions": [],
            "excluded": [],
            "focus_segments": [],
            "disclaimer": profile.get("disclaimer") if profile else "",
        }
    pub = strip_scientific_debug(profile)
    dims = public_dimensions(pub)
    excl = excluded_dimensions(pub)
    focus = pub.get("focus_segments") or []
    claim_blob = affirmative_copy_blob(dims, pub.get("headline"))
    claim_blob += " " + affirmative_copy_blob([{"focus_segments": focus}])
    assert_no_banned_wording(claim_blob)
    return {
        "available": True,
        "engine_version": pub.get("engine_version"),
        "headline": pub.get("headline") or [],
        "dimensions": dims,
        "excluded": excl,
        "focus_segments": focus,
        "disclaimer": pub.get("disclaimer"),
        "valid_segment_count": pub.get("valid_segment_count"),
        "total_segment_count": pub.get("total_segment_count"),
    }


def free_vocal_quality_teaser(profile: dict[str, Any]) -> list[str]:
    """Short Free-tier bullets — no detailed segments."""
    if not profile or not profile.get("available"):
        return []
    bullets = []
    dims = profile.get("dimensions") or {}
    b = dims.get("breathy_like") or {}
    if b.get("status") in ("MODERATE", "HIGH", "INTERMITTENT"):
        bullets.append("일부 구간에서 숨이 섞이는 음질 가능성이 있어요.")
    p = dims.get("pressed_like") or {}
    if p.get("status") in ("MODERATE", "HIGH", "INTERMITTENT"):
        bullets.append("일부 구간에서 압착된 음질과 일치할 수 있는 경향이 있어요.")
    r = dims.get("rough_like") or {}
    if r.get("status") in ("MODERATE", "HIGH", "INTERMITTENT"):
        bullets.append("일부 구간에서 거친 음질 경향이 관찰됐어요.")
    t = dims.get("register_transition") or {}
    if t.get("status") in ("MILD_DISRUPTION", "BREAK_LIKE"):
        bullets.append("음역 전환 일부에서 소리가 흔들리는 패턴이 있어요.")
    if not bullets:
        bullets.append("뚜렷한 음질 이상 패턴은 제한적으로 관찰됐어요.")
    return bullets[:3]
