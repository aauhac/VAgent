"""
vocal_quality/config.py
-----------------------
Vocal Quality / Phonation State Engine v1 config.

Non-medical. Audio-observable tendencies only.
"""

from __future__ import annotations

ENGINE_VERSION = "vocal-quality-v1.0"
CALIBRATION_STATUS = "uncalibrated"

SEGMENT_WINDOW_SEC = 3.0
SEGMENT_HOP_SEC = 1.5
MAX_SEGMENTS = 24
MIN_VOICED_RATIO = 0.30
MIN_RMS_RATIO = 0.08

# Prevalence thresholds (fraction of valid segments)
PREVALENCE_RARE = 0.10
PREVALENCE_OCCASIONAL = 0.25
PREVALENCE_REPEATED = 0.45
PREVALENCE_DOMINANT = 0.70

MIN_SEGMENTS_FOR_GLOBAL = 3
MIN_SEGMENTS_FOR_HIGH = 4
MIN_FAMILIES_FOR_HIGH = 2

# Metric status registry
METRIC_STATUS = {
    "cepstral_prominence_proxy_db": "PROXY",
    "hnr_ac_proxy_db": "PROXY",  # same periodicity family as cepstral — not independent
    "raw_h1_h2_proxy_db": "PROXY",
    "spectral_tilt_db_per_oct": "KEEP",
    "spectral_centroid_hz": "KEEP",
    "f0_frame_period_perturbation_proxy_percent": "RESTRICTED",
    "onset_slope_db_per_sec": "PROXY",
    "periodicity_establishment_ratio": "EXPERIMENTAL",
    "residual_std_cents": "KEEP",
    "spr_db": "RESTRICTED",
    "weight_gap_db": "PROXY",
}

# Engineering thresholds (provisional — NOT calibrated on human labels)
BREATHY_CPP_LOW = 8.0
BREATHY_HNR_LOW = 8.0
BREATHY_TILT_STEEP = -18.0  # more negative → steeper tilt / weaker highs
BREATHY_H1H2_HIGH = 8.0

PRESSED_CPP_HIGH = 18.0
PRESSED_HNR_HIGH = 18.0
PRESSED_TILT_FLAT = -6.0
PRESSED_H1H2_LOW = 0.0
PRESSED_ONSET_ABRUPT = 80.0  # dB/s

ROUGH_CPP_DROP = 6.0
ROUGH_PERTURB_HIGH = 2.5
ROUGH_RESIDUAL_HIGH = 35.0

CENTROID_BRIGHT = 2200.0
CENTROID_DARK = 1400.0

TRANSITION_F0_JUMP_CENTS = 350.0
TRANSITION_DROPOUT_GAP_SEC = 0.12

BANNED_USER_SUBSTRINGS = (
    "성대가",
    "성문",
    "후두",
    "TA",
    "CT",
    "LCA",
    "복압",
    "횡격막",
    "결절",
    "폴립",
    "근육이 긴장",
    "목이 조",
    "성대 접촉",
)

DIMENSION_DISPLAY = {
    "breathy_like": "숨이 섞이는 음질 경향",
    "pressed_like": "단단하고 강한 음질 경향",
    "rough_like": "거칠고 불규칙한 음질 경향",
    "resonance_timbre": "공명·음색 프로필",
    "onset_behavior": "발성 시작 특성",
    "register_transition": "음역 전환 특성",
    "phonation_stability": "발성 안정성",
}

PREVALENCE_LABELS = {
    "not_observed": "관찰되지 않음",
    "rare": "드묾",
    "occasional": "일부",
    "repeated": "반복 관찰",
    "dominant": "전반적",
    "unknown": "판단 어려움",
}

STATUS_LABELS = {
    "LOW": "낮음",
    "MODERATE": "중간",
    "HIGH": "높음",
    "INTERMITTENT": "일부 구간",
    "MIXED": "혼합",
    "AMBIGUOUS": "모호함",
    "UNKNOWN": "판단 어려움",
    "SOFT_LIKE": "부드러운 편",
    "BALANCED_LIKE": "균형",
    "ABRUPT_LIKE": "급하게 형성",
    "BREATHY_LIKE": "숨 섞인 시작",
    "SMOOTH": "대체로 부드러움",
    "MILD_DISRUPTION": "가벼운 흔들림",
    "BREAK_LIKE": "전환 흔들림",
}
