"""Vocal Function Engine v2.2 configuration."""

from __future__ import annotations

FUNCTION_ENGINE_VERSION = "vocal-function-v2.6"
REPORT_VERSION = "vocal-coach-report-v2.6"
METRIC_REGISTRY_VERSION = "vf-metrics-2026-08"
RULE_VERSION = "vf-rules-2026-08-v23-criteria"
LITERATURE_VERSION = "vf-lit-2026-08"

MEASUREMENT_MODE = "AUDIO_ONLY"  # future: AUDIO_PLUS_EGG

MIN_SEGMENTS_GLOBAL = 3
MIN_SEGMENTS_HIGH = 3
PREVALENCE_OCCASIONAL = 0.15
PREVALENCE_REPEATED = 0.35
MIN_VOCAL_DOMINANCE = 0.55
MAIN_DISPLAY_MIN_CONFIDENCE = "medium"  # low hidden from main cards

# Episode context windows (outside episode span)
PRE_CONTEXT_MAX_SEC = 4.0
PRE_CONTEXT_N = 3
POST_CONTEXT_MAX_SEC = 4.0
POST_CONTEXT_N = 3

# Best-self minimum meaningful effort improvement
BEST_SELF_MIN_EFFORT_DELTA = 0.15

# Relative (not clinical) direction hints for contact — soft cues only
NAQ_LIGHTER_HINT = 0.15
NAQ_FIRMER_HINT = 0.08
H1H2_LIGHTER_DB = 6.0
H1H2_FIRMER_DB = 1.0

# Soft directional shift thresholds (uncalibrated)
NAQ_SHIFT_HINT = 0.03
H1H2_SHIFT_DB = 2.0
MFDR_NORM_SHIFT_RATIO = 0.25
ENERGY_24K_SHIFT = 0.04
CENTROID_SHIFT_HZ = 150.0
INTENSITY_OVERSHOOT_DB = 3.0
F0_JUMP_CENTS_REGISTER = 350.0

BANNED_CLAIM_SUBSTRINGS = (
    "TA가",
    "CT가",
    "CT를",
    "LCA",
    "성대가 벌어",
    "성문 폐쇄 부족",
    "후두가 상승",
    "후두가 올라",
    "결절",
    "부종",
    "목 근육 긴장",
    "목이 조",
    "복압을",
    "횡격막을",
    "ANATOMY_ESTIMATE",
)

DIMENSION_DISPLAY = {
    "glottal_contact_profile": "성대 접촉 관련 발성 경향",
    "air_leakage_breathiness": "기류 누출·기식성 경향",
    "vocal_effort_strain": "힘이 과하게 들어간 소리 경향",
    "phonation_regularity": "성대 진동 안정성",
    "register_configuration": "성구·음역 전환",
    "onset_offset_coordination": "소리 시작·마무리",
    "vibrato_control": "비브라토 제어",
    "resonance_formant_strategy": "공명·음색 전략",
    "respiratory_phonatory_coordination": "호흡과 발성의 협응",
    "phonatory_economy_proxy": "발성 효율 경향",
}

METRIC_GRADES = {
    "f0": "A",
    "cpp_proxy": "B",
    "hnr_proxy": "B",
    "h1_h2_proxy": "B",
    "estimated_naq": "B",
    "estimated_qoq": "C",
    "estimated_clq_proxy": "C",
    "estimated_mfdr_proxy": "C",
    "formants": "B",
    "subglottal_pressure": "D",
    "diaphragm_activation": "D",
}
