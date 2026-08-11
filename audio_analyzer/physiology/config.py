"""
physiology/config.py
--------------------
Physiology inference v1.3 — product visibility + eligibility policy.
"""

INFERENCE_VERSION = "physiology-inference-v1.3"
METRIC_VERSION = "physio-metrics-v1.1"
LITERATURE_REGISTRY_VERSION = "physiology-evidence-2026-08"
PROTOCOL_VERSION = "diagnostic-protocol-v1.2"
# Backward-compatible alias
PROTOCOL_VERSION_LEGACY = "vocal-dx-v1.0"
COACHING_VERSION = "physio-coach-v1.3"
REPORT_VERSION = "diagnostic-report-v1.2"
CALIBRATION_STATUS = "uncalibrated"

AUDIO_ONLY_GLOBAL_CONFIDENCE_CAP = 0.72

MIN_INDEPENDENT_FAMILIES_FOR_DIRECTION = 2
MIN_FAMILIES_FOR_MEDIUM = 3

CEPSTRAL_LOW_PERIODICITY_BELOW = 12.0
CEPSTRAL_HIGH_PERIODICITY_ABOVE = 20.0
HNR_PROXY_LOW_BELOW = 10.0
HNR_PROXY_HIGH_ABOVE = 20.0
RAW_H1H2_LIGHT_ABOVE = 8.0
RAW_H1H2_FIRM_BELOW = 2.0

MECHANISM_ID_ALIASES = {
    "glottal_closure_tendency": "phonation_contact_pattern",
    "breath_phonation_coordination": "intensity_phonation_coordination",
}

# Literature-aligned caps (do not inflate)
MECHANISM_CONFIDENCE_CAPS = {
    "phonation_contact_pattern": 0.58,
    "phonatory_efficiency": 0.35,
    "intensity_phonation_coordination": 0.60,
    "onset_coordination": 0.45,
    "release_coordination": 0.40,
    "register_transition_coordination": 0.65,
    "vocal_tract_resonance_balance": 0.40,
    "phonation_stability": 0.68,
}

MECHANISM_IDS = [
    "phonation_contact_pattern",
    "phonatory_efficiency",
    "intensity_phonation_coordination",
    "onset_coordination",
    "release_coordination",
    "register_transition_coordination",
    "vocal_tract_resonance_balance",
    "phonation_stability",
]

MECHANISM_DISPLAY = {
    "phonation_contact_pattern": "성대 접촉과 관련된 발성 경향",
    "phonatory_efficiency": "발성 효율",
    "intensity_phonation_coordination": "강도 변화와 발성 협응",
    "onset_coordination": "소리 시작 관찰",
    "release_coordination": "끝음 조절",
    "register_transition_coordination": "음역 전환의 연속성",
    "vocal_tract_resonance_balance": "공명·성도 균형",
    "phonation_stability": "발성 안정성",
}

MECHANISM_AUDIT = {
    "phonation_contact_pattern": "CONDITIONAL",
    "phonatory_efficiency": "WEAK",
    "intensity_phonation_coordination": "CONDITIONAL",
    "onset_coordination": "CONDITIONAL",
    "release_coordination": "WEAK",
    "register_transition_coordination": "CONDITIONAL",
    "vocal_tract_resonance_balance": "WEAK",
    "phonation_stability": "CONDITIONAL",
}

# Product visibility (hostile-audit aligned)
# PRIMARY: always attempted for user report
# CONDITIONAL_PRIMARY: shown only when eligibility passes
# SECONDARY: auxiliary observation card only
# RESEARCH_ONLY: scientific_debug / supporting observation only
PRODUCT_VISIBILITY = {
    "phonation_stability": "PRIMARY",
    "register_transition_coordination": "PRIMARY",
    "phonation_contact_pattern": "CONDITIONAL_PRIMARY",
    "intensity_phonation_coordination": "CONDITIONAL_PRIMARY",
    "onset_coordination": "SECONDARY",
    "phonatory_efficiency": "RESEARCH_ONLY",
    "release_coordination": "RESEARCH_ONLY",
    "vocal_tract_resonance_balance": "RESEARCH_ONLY",
}

PRIMARY_UX_MECHANISMS = [
    mid for mid, v in PRODUCT_VISIBILITY.items() if v == "PRIMARY"
]
CONDITIONAL_PRIMARY_MECHANISMS = [
    mid for mid, v in PRODUCT_VISIBILITY.items() if v == "CONDITIONAL_PRIMARY"
]
AUXILIARY_UX_MECHANISMS = [
    mid for mid, v in PRODUCT_VISIBILITY.items() if v == "SECONDARY"
]
NEEDS_MORE_UX_MECHANISMS = RESEARCH_ONLY_MECHANISMS = [
    mid for mid, v in PRODUCT_VISIBILITY.items() if v == "RESEARCH_ONLY"
]

# Mechanisms we attempt to fill in user report coverage denominator
ATTEMPTED_PRIMARY_MECHANISMS = PRIMARY_UX_MECHANISMS + CONDITIONAL_PRIMARY_MECHANISMS

WEAK_MECHANISMS_USER_SUPPRESS = set(RESEARCH_ONLY_MECHANISMS)

CONTACT_REQUIRES_CROSS_VOWEL = True
CONTACT_NEVER_HIGH_LABEL = True

SAFETY_DISCLAIMER = (
    "이 결과는 녹음된 음성의 음향적 특성을 바탕으로 "
    "발성 패턴을 분석한 발성 분석 참고 정보입니다. "
    "성대의 실제 구조나 질환을 진단하는 검사가 아닙니다."
)

SAFETY_STOP_INSTRUCTION = (
    "분석 중 통증, 심한 불편감, 어지러움, 호흡 곤란, "
    "갑작스러운 심한 음성 변화가 있으면 즉시 중단하세요. "
    "이 앱은 원인을 진단하지 않습니다."
)

EVIDENCE_FAMILY_LABELS = {
    "periodicity": "주기성(cepstral/HNR 계열)",
    "spectral_source": "스펙트럼 소스 프록시",
    "temporal_stability": "시간 안정성",
    "onset": "소리 시작 에너지",
    "release": "끝음 에너지",
    "intensity_coordination": "강도 변화 조절",
    "register_continuity": "음역 연속성",
}


def canonicalize_mechanism_id(mechanism_id: str) -> str:
    return MECHANISM_ID_ALIASES.get(mechanism_id, mechanism_id)


def product_visibility(mechanism_id: str) -> str:
    mid = canonicalize_mechanism_id(mechanism_id)
    return PRODUCT_VISIBILITY.get(mid, "RESEARCH_ONLY")


def confidence_label(conf: float, *, mechanism_id: str | None = None) -> str:
    mid = canonicalize_mechanism_id(mechanism_id) if mechanism_id else None
    if mid == "phonation_contact_pattern" and CONTACT_NEVER_HIGH_LABEL:
        if conf < 0.40:
            return "낮음"
        return "중간"
    if conf < 0.40:
        return "낮음"
    if conf < 0.60:
        return "중간"
    return "높음"


def ux_tier(mechanism_id: str) -> str:
    vis = product_visibility(mechanism_id)
    if vis == "PRIMARY":
        return "primary"
    if vis == "CONDITIONAL_PRIMARY":
        return "conditional_primary"
    if vis == "SECONDARY":
        return "auxiliary"
    return "research_only"
