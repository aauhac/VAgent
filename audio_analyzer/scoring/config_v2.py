"""
scoring/config_v2.py
--------------------
Vocal skill score v2 configuration.

SCORE_VERSION / CALIBRATION_STATUS must travel with every score payload.
Thresholds are provisional heuristics — not scientifically calibrated.
Do NOT retune thresholds from a few samples in this hardening pass.
"""

SCORE_VERSION = "vocal-score-v2.0"
CALIBRATION_STATUS = "uncalibrated"

# Minimum confidence to include an area in overall aggregation
MIN_AREA_CONFIDENCE = 0.35
# Below this, mark status=unknown (never auto-promote to good/strength)
UNKNOWN_CONFIDENCE = 0.35
# Strength generation requires reliable good/excellent measurement
STRENGTH_MIN_CONFIDENCE = 0.55
STRENGTH_MIN_SCORE = 70.0

# Need at least this many reliable areas to publish overall
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

# Stability: local residual std cents (lower is better)
STABILITY = {
    "metric": "median_residual_std_cents",
    "good": 18.0,
    "weak": 45.0,
    "direction": "lower_is_better",
}

# Projection: SPR dB (lower is better — smaller low-vs-presence gap)
PROJECTION = {
    "metric": "spr_db",
    "good": 22.6,
    "weak": 32.0,
    "direction": "lower_is_better",
    "singer_formant_prominence_good": 6.0,
    "singer_formant_prominence_weak": 0.0,
}

PROJECTION_COMPONENT_WEIGHTS = {
    "spr": 0.6,
    "singer_formant_prominence": 0.4,
}

# Resonance: blend of weight_gap + mouth_gap + spectral_slope
RESONANCE = {
    "weight_gap": {
        "good_min": -6.0,
        "good_max": 10.0,
        "bad_min": -16.0,
        "bad_max": 18.0,
    },
    "mouth_gap": {
        "good": 6.0,
        "weak": 14.0,
    },
    "spectral_slope": {
        "good_min": -16.0,
        "good_max": -8.0,
        "bad_min": -22.0,
        "bad_max": -4.0,
    },
}

RESONANCE_COMPONENT_WEIGHTS = {
    "weight_gap": 0.35,
    "mouth_gap": 0.30,
    "spectral_slope": 0.35,
}

# Completeness → confidence scales (available / expected)
PROJECTION_COMPLETENESS_CONF = {
    2: 1.0,
    1: 0.62,
    0: 0.0,
}
RESONANCE_COMPLETENESS_CONF = {
    3: 1.0,
    2: 0.72,
    1: 0.28,  # strongly down / typically unknown
    0: 0.0,
}

# Dynamic control: provisional target range (NOT higher-is-better)
DYNAMIC_CONTROL = {
    "metric": "dynamic_range_db",
    "good_min": 8.0,
    "good_max": 28.0,
    "bad_min": 3.0,
    "bad_max": 40.0,
}

STATUS_THRESHOLDS = {
    "excellent": 85.0,
    "good": 70.0,
    "normal": 55.0,
}

OVERALL_LABELS = [
    (85.0, "매우 안정적"),
    (70.0, "좋은 편"),
    (55.0, "보통이에요"),
    (40.0, "개선 여지가 있어요"),
    (0.0, "다시 녹음해 보면 좋아요"),
]

# Confidence penalties when source was demucs-separated
SEPARATED_SPECTRAL_CONFIDENCE_SCALE = 0.7
DEMUCS_HF_LOSS_CONFIDENCE_SCALE = 0.55

# Per-area multipliers applied when quality warning codes are present.
# RUMBLE intentionally omitted from skill-score penalties (quality note only).
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
