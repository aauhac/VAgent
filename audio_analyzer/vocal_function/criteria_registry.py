"""Functional dimension criteria registry (measurement sufficiency, not quality judgment).

Criteria answer: "Is there enough evidence to conclude about this dimension?"
They do NOT mean good/bad singing.
"""

from __future__ import annotations

from typing import Any

# Ordered display — every Functional dimension appears in the matrix
DIMENSION_ORDER: tuple[str, ...] = (
    "glottal_contact_profile",
    "air_leakage_breathiness",
    "vocal_effort_strain",
    "phonation_regularity",
    "register_configuration",
    "onset_offset_coordination",
    "vibrato_control",
    "resonance_formant_strategy",
    "respiratory_phonatory_coordination",
    "phonatory_economy_proxy",
)

# Bottleneck id → dimension_id for coaching eligibility gates
BOTTLENECK_DIMENSION: dict[str, str] = {
    "AIR_LEAKAGE": "air_leakage_breathiness",
    "APERIODIC_ROUGHNESS": "phonation_regularity",
    "REGISTER_TRANSITION_DISRUPTION": "register_configuration",
    "ABRUPT_ONSET": "onset_offset_coordination",
    "EXCESS_EFFORT_HIGH_NOTE": "vocal_effort_strain",
    "GENERAL_EXCESS_EFFORT": "vocal_effort_strain",
    "EXCESS_FIRMNESS_WITH_STRAIN": "vocal_effort_strain",
    "RESONANCE_MID_PRESENCE_LOSS": "resonance_formant_strategy",
    "RESONANCE_HIGH_NOTE_COLLAPSE": "resonance_formant_strategy",
    "PHRASE_END_SUPPORT_LOSS": "respiratory_phonatory_coordination",
    "VIBRATO_IRREGULARITY": "vibrato_control",
    "INTENSITY_OVERSHOOT": "vocal_effort_strain",
    "UNSTABLE_RELEASE": "onset_offset_coordination",
    "FIRM_PHONATION": "glottal_contact_profile",
}

# Minimum required criteria that must be SUFFICIENT (availability) for coaching YES
# and for primary selection. Not acoustic thresholds — coverage policy.
COACHING_MIN_REQUIRED_MET: dict[str, int] = {
    "air_leakage_breathiness": 3,
    "glottal_contact_profile": 2,
    "vocal_effort_strain": 2,
    "phonation_regularity": 2,
    "register_configuration": 4,
    "onset_offset_coordination": 2,
    "vibrato_control": 1,
    "resonance_formant_strategy": 2,
    "respiratory_phonatory_coordination": 1,
    "phonatory_economy_proxy": 1,
}

CRITERIA_BY_DIMENSION: dict[str, list[dict[str, Any]]] = {
    "air_leakage_breathiness": [
        {"criterion_id": "vocal_presence", "label": "목소리 신호(vocal presence)", "required": True},
        {"criterion_id": "periodicity_noise", "label": "주기성/노이즈 단서", "required": True},
        {"criterion_id": "spectral_harmonic", "label": "배음·스펙트럼 단서", "required": True},
        {"criterion_id": "glottal_source", "label": "source proxy (GIF)", "required": False},
        {"criterion_id": "evaluable_coverage", "label": "평가 가능 구간 수", "required": True},
        {"criterion_id": "repetition", "label": "반복성", "required": True},
    ],
    "glottal_contact_profile": [
        {"criterion_id": "vocal_presence", "label": "목소리 신호", "required": True},
        {"criterion_id": "glottal_source", "label": "source proxy (GIF)", "required": False},
        {"criterion_id": "harmonic", "label": "배음(H1-H2 등) 단서", "required": True},
        {
            "criterion_id": "contact_source_support",
            "label": "GIF 또는 multi-family contact 단서",
            "required": True,
        },
        {"criterion_id": "evaluable_coverage", "label": "평가 가능 구간 수", "required": True},
    ],
    "vocal_effort_strain": [
        {"criterion_id": "vocal_presence", "label": "목소리 신호", "required": True},
        {"criterion_id": "effort_multi_sign", "label": "effort 복수 단서", "required": True},
        {"criterion_id": "localization", "label": "국소 episode", "required": True},
        {"criterion_id": "evaluable_coverage", "label": "평가 가능 구간 수", "required": False},
    ],
    "phonation_regularity": [
        {"criterion_id": "vocal_presence", "label": "목소리 신호", "required": True},
        {"criterion_id": "periodicity_loss", "label": "주기성 저하", "required": True},
        {"criterion_id": "irregularity_specific", "label": "불규칙 진동 특화 단서", "required": True},
        {"criterion_id": "repetition", "label": "반복성", "required": True},
    ],
    "register_configuration": [
        {"criterion_id": "vocal_specific", "label": "보컬 구간 확인", "required": True},
        {"criterion_id": "f0_transition", "label": "F0 전환", "required": True},
        {"criterion_id": "source_shift", "label": "source pattern 변화", "required": True},
        {"criterion_id": "accompaniment_reject", "label": "반주 오염 가능성 낮음", "required": True},
        {"criterion_id": "vibrato_mask", "label": "비브라토로 설명되지 않음", "required": True},
        {"criterion_id": "localization", "label": "국소 core span", "required": True},
    ],
    "onset_offset_coordination": [
        {"criterion_id": "onset_metric", "label": "유효 onset 측정", "required": True},
        {"criterion_id": "repetition", "label": "반복 evidence", "required": True},
        {"criterion_id": "evaluable_coverage", "label": "평가 가능 구간 수", "required": True},
    ],
    "vibrato_control": [
        {"criterion_id": "vibrato_detection", "label": "비브라토 관측 가능", "required": True},
        {"criterion_id": "regularity_depth", "label": "규칙성·깊이 단서", "required": False},
    ],
    "resonance_formant_strategy": [
        {"criterion_id": "spectral_evidence", "label": "스펙트럼 단서", "required": True},
        {"criterion_id": "formant_or_band", "label": "formant/대역 coverage", "required": True},
        {"criterion_id": "evaluable_coverage", "label": "평가 가능 구간 수", "required": False},
    ],
    "respiratory_phonatory_coordination": [
        {"criterion_id": "phrase_energy", "label": "구절 에너지 패턴", "required": True},
        {"criterion_id": "evaluable_coverage", "label": "평가 가능 구간 수", "required": False},
    ],
    "phonatory_economy_proxy": [
        {"criterion_id": "proxy_available", "label": "효율 proxy 가용", "required": True},
    ],
}


def criteria_for(dimension_id: str) -> list[dict[str, Any]]:
    return list(CRITERIA_BY_DIMENSION.get(dimension_id) or [])


def coaching_min_required(dimension_id: str) -> int:
    return int(COACHING_MIN_REQUIRED_MET.get(dimension_id, 2))
