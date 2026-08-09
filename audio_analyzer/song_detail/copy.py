"""
song_detail/copy.py
-------------------
User-facing display names and copy helpers for Song Detail (v3-aware).
"""

from __future__ import annotations

from typing import Any, Optional

# Positive-oriented display names for ratio-normalized submetrics
SUBMETRIC_DISPLAY_USER = {
    "sustain_pitch_stability": "지속음 안정성",
    "sustain_level_stability": "음량 유지",
    "region_consistency": "구간 일관성",
    "unstable_region_ratio": "구간 안정 유지",
    "stability_worst_region": "최악 구간",
    "spectral_projection": "스펙트럼 전달",
    "presence_prominence": "소리 선명도",
    "projection_consistency": "전달 일관성",
    "weak_projection_segment_ratio": "전달 유지력",
    "projection_worst_segment": "최악 전달 구간",
    "weight_balance": "저역–전달 균형",
    "mid_resonance_balance": "중역 공명 균형",
    "spectral_slope_balance": "스펙트럼 기울기 균형",
    "resonance_consistency": "공명 일관성",
    "extreme_resonance_ratio": "공명 균형 유지력",
    "resonance_worst_segment": "최악 공명 구간",
    "global_dynamic_range": "전체 강약 폭",
    "local_dynamic_variation": "구간 강약 변화",
    "smoothness": "변화 부드러움",
    "phrase_consistency": "구절 일관성",
    "abrupt_change_ratio": "강약 변화 안정성",
    "dynamic_worst_segment": "최악 강약 구간",
}

AREA_DISPLAY = {
    "stability": "발성 안정성",
    "projection": "목소리 전달력",
    "resonance": "공명 균형",
    "dynamic_control": "강약 컨트롤",
}

CONF_HIGH = 0.70
CONF_MEDIUM = 0.45
CONF_HIDE_SCORE = 0.20

SUBMETRIC_STRENGTH_MIN = 85.0
SUBMETRIC_WEAK_MAX = 60.0
WORST_FOCUS_THRESHOLD = 65.0


def submetric_display_name(submetric_id: str, fallback: Optional[str] = None) -> str:
    return SUBMETRIC_DISPLAY_USER.get(submetric_id) or fallback or submetric_id


def confidence_label(confidence: Optional[float]) -> str:
    if confidence is None:
        return "판단 어려움"
    c = float(confidence)
    if c >= CONF_HIGH:
        return "신뢰 높음"
    if c >= CONF_MEDIUM:
        return "참고 가능"
    return "신뢰 낮음"


def confidence_state(confidence: Optional[float]) -> str:
    if confidence is None or float(confidence) < CONF_MEDIUM:
        return "low"
    if float(confidence) < CONF_HIGH:
        return "medium"
    return "high"


def coverage_state(coverage: Optional[float]) -> str:
    if coverage is None:
        return "low"
    c = float(coverage)
    if c >= 0.8:
        return "high"
    if c >= 0.5:
        return "medium"
    return "low"


def format_mmss(sec: Optional[float]) -> str:
    if sec is None:
        return "—"
    s = max(0, int(float(sec)))
    return f"{s // 60:02d}:{s % 60:02d}"


def join_summary(overall: Optional[float], label: Optional[str], *, partial: bool) -> str:
    """Avoid '있어요이에요' style double endings."""
    parts: list[str] = []
    if overall is not None:
        if partial:
            parts.append(f"부분 분석 점수 {overall}점")
        else:
            parts.append(f"종합 {overall}점")
    lab = (label or "").strip()
    if lab:
        # label is already a complete phrase (e.g. 개선 여지가 있어요)
        if lab.endswith(("요", "다", "음")):
            parts.append(lab)
        else:
            parts.append(f"{lab}예요")
    if not parts:
        return "노래 발성 특성 상세 결과예요."
    text = ", ".join(parts)
    if not text.endswith("."):
        text += "."
    if "보정" not in text:
        text += " 점수는 아직 보정 전 잠정 기준입니다."
    return text


def topic_particle(name: str) -> str:
    """Return 은/는 after a Korean noun (approximate by final jamo)."""
    if not name:
        return "은(는)"
    ch = name[-1]
    code = ord(ch)
    if 0xAC00 <= code <= 0xD7A3:
        return "은" if (code - 0xAC00) % 28 else "는"
    return "은(는)"


def subject_particle(name: str) -> str:
    """Return 이/가 after a Korean noun."""
    if not name:
        return "이(가)"
    ch = name[-1]
    code = ord(ch)
    if 0xAC00 <= code <= 0xD7A3:
        return "이" if (code - 0xAC00) % 28 else "가"
    return "이(가)"


def practice_for_submetric(submetric_id: str) -> str:
    return {
        "sustain_level_stability": (
            "'아—' 4초 × 3회. 처음과 끝의 음량이 비슷하게 유지되는지 확인해 보세요."
        ),
        "sustain_pitch_stability": (
            "편한 음에서 3~4초 유지. 음량보다 음의 중심이 일정하게 느껴지는지 확인해 보세요."
        ),
        "region_consistency": (
            "비슷한 길이의 지속음을 여러 번 반복하며, 구간마다 느낌이 크게 달라지지 않게 연습해 보세요."
        ),
        "stability_worst_region": (
            "가장 흔들린 구간만 따로 짧게 반복해, 시작부터 끝까지 같은 크기로 유지해 보세요."
        ),
        "presence_prominence": (
            "가사를 말하듯 읽은 뒤, 같은 느낌으로 낮은 볼륨에서 또렷하게 시작해 보세요."
        ),
        "spectral_projection": (
            "지르지 말고 말하듯 앞쪽으로 전달되는 느낌으로 한 문장을 불러 보세요."
        ),
        "mid_resonance_balance": (
            "'네', '니', '냐'로 같은 멜로디를 부르며 소리가 앞으로 나오는지 확인해 보세요."
        ),
        "weight_balance": (
            "턱을 억지로 열기보다 평소 말소리 위치에서 편하게 유지해 보세요."
        ),
        "global_dynamic_range": (
            "한 문장을 말하듯 읽고, 강조 단어 하나만 살짝 더 분명하게 불러 보세요."
        ),
        "dynamic_worst_segment": (
            "문제가 난 구간만 골라, 강약을 작게→중간→작게로 부드럽게 바꿔 보세요."
        ),
        "local_dynamic_variation": (
            "구절마다 같은 크기로 부르지 말고, 중요한 단어만 조금 더 살리는 연습을 해보세요."
        ),
        "smoothness": (
            "소리 크기를 바꿀 때 갑자기 커지거나 작아지지 않게, 한 호흡 안에서 천천히 바꿔 보세요."
        ),
    }.get(
        submetric_id,
        "편한 음 하나를 골라 짧게 반복하며, 가장 약한 세부 항목을 의식해 연습해 보세요.",
    )


def focus_headline(area_id: str) -> str:
    return {
        "stability": "지속음이 가장 흔들린 구간",
        "projection": "목소리 전달이 약해진 구간",
        "resonance": "공명 균형이 벗어난 구간",
        "dynamic_control": "강약 조절이 가장 흔들린 구간",
    }.get(area_id, "점수가 낮았던 구간")


def focus_message(area_id: str, *, score: Optional[float] = None) -> str:
    base = {
        "stability": "이 구간은 지속음의 음량 유지가 다른 구간보다 불안정했어요.",
        "projection": "이 구간에서는 목소리 전달 특성이 다른 구간보다 약하게 측정됐어요.",
        "resonance": "이 구간에서는 스펙트럼 균형이 다른 구간보다 크게 벗어났어요.",
        "dynamic_control": "이 구간에서는 강약 조절이 다른 구간보다 불안정했어요.",
    }.get(area_id, "이 구간은 다른 구간보다 점수가 낮게 측정됐어요.")
    if score is not None:
        return f"{base} (구간 점수 {round(float(score))})"
    return base
