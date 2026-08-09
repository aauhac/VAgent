"""
scoring/config_v3.py
--------------------
Vocal skill score v3 — hierarchical precision scoring config.

Thresholds are provisional engineering scales, NOT clinical calibration.
Do not retune from a handful of local samples.
"""

SCORE_VERSION = "vocal-score-v3.0"
CALIBRATION_STATUS = "uncalibrated"

MIN_AREA_CONFIDENCE = 0.35
UNKNOWN_CONFIDENCE = 0.35
STRENGTH_MIN_CONFIDENCE = 0.55
STRENGTH_MIN_SCORE = 70.0
MIN_AREAS_FOR_OVERALL = 2

AREA_DISPLAY = {
    "stability": "발성 안정성",
    "projection": "목소리 전달력",
    "resonance": "공명 균형",
    "dynamic_control": "강약 컨트롤",
}

AREA_WEIGHTS = {
    "stability": 0.30,
    "projection": 0.28,
    "resonance": 0.24,
    "dynamic_control": 0.18,
}

# User-facing status bands (beta / uncalibrated)
STATUS_BANDS = [
    (95.0, "매우 뛰어남"),
    (88.0, "매우 좋음"),
    (78.0, "좋음"),
    (68.0, "보통 이상"),
    (55.0, "개선 여지 있음"),
    (0.0, "집중 개선 권장"),
]

# Machine status for API compat
STATUS_THRESHOLDS = {
    "excellent": 88.0,
    "good": 78.0,
    "normal": 68.0,
}

OVERALL_LABELS = [
    (90.0, "매우 안정적"),
    (78.0, "좋은 편"),
    (68.0, "보통이에요"),
    (55.0, "개선 여지가 있어요"),
    (0.0, "다시 녹음해 보면 좋아요"),
]

# ── Coverage → score ceiling ─────────────────────────────────────────────
COVERAGE_CEILINGS = [
    (0.90, 100.0),
    (0.80, 100.0),
    (0.60, 90.0),
    (0.40, 80.0),
    (0.0, 70.0),
]
# coverage < 0.40 with very few metrics → prefer unknown (handled in code)

# ── Confidence → score ceiling ───────────────────────────────────────────
CONFIDENCE_CEILINGS = [
    (0.85, 100.0),
    (0.70, 95.0),
    (0.55, 85.0),
    (0.35, 75.0),
    (0.0, 0.0),  # unknown
]

# ── Worst-segment penalty (config, not calibration claims) ───────────────
WORST_SEGMENT_PENALTY = [
    # (worst_min_inclusive, score_scale)
    (85.0, 1.00),
    (70.0, 0.96),
    (50.0, 0.88),
    (0.0, 0.78),
]

# bad_segment_ratio extra scale (applied after worst penalty)
BAD_RATIO_PENALTY = [
    (0.05, 1.00),
    (0.15, 0.96),
    (0.30, 0.90),
    (0.50, 0.82),
    (1.01, 0.75),
]

# ── 100-point eligibility ────────────────────────────────────────────────
ELITE_100 = {
    "min_required_submetric_score": 90.0,
    "min_coverage": 0.90,
    "min_confidence": 0.85,
    "min_worst_segment": 90.0,
    "max_bad_segment_ratio": 0.05,
    "fail_ceiling": 99.0,
}

# ── Stability submetric weights ──────────────────────────────────────────
STABILITY_WEIGHTS = {
    "sustain_pitch_stability": 0.35,
    "sustain_level_stability": 0.20,
    "region_consistency": 0.20,
    "unstable_region_ratio": 0.15,
    "stability_worst_region": 0.10,
}

# Piecewise anchors: (raw, score) — lower residual/rms is better
STABILITY_PITCH_ANCHORS = [
    (45.0, 30.0),
    (30.0, 60.0),
    (22.0, 75.0),
    (14.0, 90.0),
    (8.0, 100.0),
]
STABILITY_LEVEL_ANCHORS = [
    (10.0, 30.0),
    (6.0, 60.0),
    (4.0, 75.0),
    (2.5, 90.0),
    (1.2, 100.0),
]
# region_consistency uses std of region scores (lower better) mapped via anchors
STABILITY_CONSISTENCY_STD_ANCHORS = [
    (25.0, 30.0),
    (15.0, 60.0),
    (10.0, 75.0),
    (5.0, 90.0),
    (2.0, 100.0),
]
# unstable_region_ratio (higher worse) — anchors as ratio 0-1
STABILITY_UNSTABLE_RATIO_ANCHORS = [
    (0.60, 30.0),
    (0.35, 60.0),
    (0.20, 75.0),
    (0.08, 90.0),
    (0.02, 100.0),
]
UNSTABLE_REGION_RESIDUAL_THRESHOLD = 35.0
STABILITY_MIN_REGIONS_FOR_FULL = 3
STABILITY_TARGET_SUSTAIN_SEC = 6.0

# ── Projection ───────────────────────────────────────────────────────────
PROJECTION_WEIGHTS = {
    "spectral_projection": 0.30,
    "presence_prominence": 0.25,
    "projection_consistency": 0.20,
    "weak_projection_segment_ratio": 0.15,
    "projection_worst_segment": 0.10,
}
# SPR lower better
PROJECTION_SPR_ANCHORS = [
    (32.0, 30.0),
    (28.0, 60.0),
    (24.0, 75.0),
    (20.0, 90.0),
    (16.0, 100.0),
]
# prominence higher better
PROJECTION_PROMINENCE_ANCHORS = [
    (0.0, 30.0),
    (2.0, 60.0),
    (4.0, 75.0),
    (6.5, 90.0),
    (9.0, 100.0),
]
WEAK_PROJECTION_SEGMENT_SCORE = 55.0

# ── Resonance ────────────────────────────────────────────────────────────
RESONANCE_WEIGHTS = {
    "weight_balance": 0.25,
    "mid_resonance_balance": 0.20,
    "spectral_slope_balance": 0.20,
    "resonance_consistency": 0.15,
    "extreme_resonance_ratio": 0.10,
    "resonance_worst_segment": 0.10,
}
# Distance from ideal center → score (piecewise on abs deviation)
RESONANCE_WEIGHT_CENTER = 2.0
RESONANCE_MOUTH_CENTER = 3.0
RESONANCE_SLOPE_CENTER = -12.0
RESONANCE_ABS_DEV_ANCHORS = [
    (14.0, 30.0),
    (10.0, 60.0),
    (6.0, 75.0),
    (3.0, 90.0),
    (1.0, 100.0),
]
EXTREME_RESONANCE_SEGMENT_SCORE = 50.0

# ── Dynamic control ──────────────────────────────────────────────────────
DYNAMIC_WEIGHTS = {
    "global_dynamic_range": 0.20,
    "local_dynamic_variation": 0.25,
    "smoothness": 0.20,
    "phrase_consistency": 0.15,
    "abrupt_change_ratio": 0.10,
    "dynamic_worst_segment": 0.10,
}
# Ideal center ~16 dB; score by abs deviation from center (NOT flat 100 in range)
DYNAMIC_RANGE_CENTER = 16.0
DYNAMIC_RANGE_DEV_ANCHORS = [
    (20.0, 30.0),
    (14.0, 55.0),
    (10.0, 70.0),
    (6.0, 85.0),
    (2.0, 95.0),
    (0.0, 98.0),  # perfect center still not auto-100 without other subs
]
# Local variation (segment dynamic range) — moderate preferred
LOCAL_DYN_CENTER = 10.0
LOCAL_DYN_DEV_ANCHORS = [
    (18.0, 30.0),
    (12.0, 60.0),
    (8.0, 75.0),
    (4.0, 90.0),
    (1.5, 98.0),
]
# Smoothness: abrupt jump ratio lower better
SMOOTHNESS_ABRUPT_ANCHORS = [
    (0.40, 30.0),
    (0.25, 60.0),
    (0.15, 75.0),
    (0.07, 90.0),
    (0.02, 100.0),
]
ABRUPT_JUMP_DB = 8.0

# ── Overall blend ────────────────────────────────────────────────────────
OVERALL_ARITHMETIC_WEIGHT = 0.70
OVERALL_GEOMETRIC_WEIGHT = 0.30
WEAKEST_AXIS_BLEND = 0.25  # pull overall toward weakest reliable axis

# Segment windowing
SEGMENT_WINDOW_SEC = 3.0
SEGMENT_HOP_SEC = 1.5
SEGMENT_MIN_RMS_RATIO = 0.08  # vs global peak

# Quality penalties (same spirit as v2)
QUALITY_CODE_PENALTIES = {
    "CLIPPING": {
        "stability": 0.85,
        "projection": 0.80,
        "resonance": 0.80,
        "dynamic_control": 0.45,
    },
    "LOW_LEVEL": {
        "stability": 0.70,
        "projection": 0.75,
        "resonance": 0.75,
        "dynamic_control": 0.85,
    },
    "LOW_VOICED_RATIO": {
        "stability": 0.60,
        "projection": 0.90,
        "resonance": 0.90,
        "dynamic_control": 0.90,
    },
    "SHORT_VOICED_DURATION": {
        "stability": 0.70,
        "projection": 0.90,
        "resonance": 0.90,
        "dynamic_control": 0.90,
    },
    "HIGH_SILENCE": {
        "stability": 0.80,
        "projection": 0.90,
        "resonance": 0.90,
        "dynamic_control": 0.85,
    },
    "SHORT_DURATION": {
        "stability": 0.85,
        "projection": 0.90,
        "resonance": 0.90,
        "dynamic_control": 0.90,
    },
}

SEPARATED_SPECTRAL_CONFIDENCE_SCALE = 0.7
DEMUCS_HF_LOSS_CONFIDENCE_SCALE = 0.55

SUBMETRIC_DISPLAY = {
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
