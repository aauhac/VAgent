"""Rule registry for physiology-informed hypotheses (v1.2)."""

from __future__ import annotations

from typing import Any

RULES: list[dict[str, Any]] = [
    {
        "rule_id": "CONTACT_LIGHT_V2",
        "mechanism_id": "phonation_contact_pattern",
        "version": "2.0",
        "literature_strength": "CONDITIONAL",
        "evidence_families": ["periodicity", "spectral_source", "onset"],
        "minimum_families": 2,
        "required_cross_vowel": True,
        "required_tasks_any": ["sustain_a", "sustain_i"],
        "preferred_cross_task_confirmation": ["sustain_a", "sustain_i"],
        "confidence_cap": 0.58,
        "allowed_status": "possibly_light_contact",
        "allowed_user_claim": (
            "주기적 진동 구조가 상대적으로 약하고, 숨이 더 섞인 발성과 일치할 수 있는 "
            "음향 특징이 관찰됐어요. 성대 접촉과 관련된 발성 경향으로 해석할 수 있어요 "
            "(성문 모양을 본 것은 아닙니다)."
        ),
        "forbidden_claims": [
            "성대가 벌어져 있다",
            "성문 폐쇄 부전",
            "LCA가 약하다",
            "성대가 안 붙는다",
        ],
        "alternative_explanations": [
            "의도적으로 작은 음량",
            "마이크 거리/응답",
            "모음·F0 차이",
            "배경 소음",
            "압축/코덱",
        ],
        "references": [
            "hillenbrand_1994_cpp_breathiness",
            "saldias_2022_cpps_singing",
            "brockmann_bauser_2021_cpp_intensity_f0",
            "kreiman_2008_oq_h1h2",
            "iseli_2004_h1h2_correction",
        ],
        "direction": "light",
    },
    {
        "rule_id": "CONTACT_FIRM_V2",
        "mechanism_id": "phonation_contact_pattern",
        "version": "2.0",
        "literature_strength": "CONDITIONAL",
        "evidence_families": ["periodicity", "spectral_source"],
        "minimum_families": 2,
        "required_cross_vowel": True,
        "required_tasks_any": ["sustain_a", "sustain_i"],
        "preferred_cross_task_confirmation": ["sustain_a", "sustain_i"],
        "confidence_cap": 0.55,
        "allowed_status": "possibly_firm_contact",
        "allowed_user_claim": (
            "주기성·고조파 특징이 상대적으로 강한 쪽에 있어요. "
            "성대 접촉과 관련된 발성 경향이 단단한 쪽에 가깝다고 볼 수 있지만, "
            "세게 눌렀다고 확정하지는 않아요."
        ),
        "forbidden_claims": ["성대를 세게 붙이고 있다", "pressed voice 확정", "TA 과활성"],
        "alternative_explanations": ["큰 음량/SPL", "마이크 근접", "모음 차이"],
        "references": ["holmborg_1995_aerodynamic_egg", "hanson_1997_h1h2"],
        "direction": "firm",
    },
    {
        "rule_id": "INTENSITY_COORD_SWELL_V2",
        "mechanism_id": "intensity_phonation_coordination",
        "version": "2.0",
        "literature_strength": "CONDITIONAL",
        "evidence_families": ["intensity_coordination", "release", "temporal_stability"],
        "minimum_families": 2,
        "required_tasks_any": ["dynamic_swell"],
        "confidence_cap": 0.60,
        "allowed_status": "needs_attention",
        "allowed_user_claim": (
            "발성 강도 변화가 매끄럽게 이어지지 않는 경향이 관찰됐어요. "
            "호흡압·복압·횡격막 활성도는 오디오만으로 알 수 없어요."
        ),
        "forbidden_claims": ["복압 부족", "횡격막이 약하다", "폐활량이 적다", "호흡 지지 부족 확정"],
        "alternative_explanations": ["작은 절대 음량", "마이크 거리", "Task 수행 방식"],
        "references": ["titze_2006_sovt"],
        "direction": "awkward_swell",
    },
    {
        "rule_id": "ONSET_AUX_V2",
        "mechanism_id": "onset_coordination",
        "version": "2.0",
        "literature_strength": "CONDITIONAL",
        "evidence_families": ["onset", "periodicity"],
        "minimum_families": 2,
        "required_tasks_any": ["sustain_a", "sustain_i"],
        "confidence_cap": 0.45,
        "ux_tier": "auxiliary",
        "allowed_status": "needs_attention",
        "allowed_user_claim": (
            "보조 관찰: 소리 시작 구간의 에너지 상승이 급하거나 불안정한 쪽과 일치하는 특징이 있어요. "
            "성문 attack을 직접 본 것은 아닙니다."
        ),
        "forbidden_claims": ["hard glottal attack 확정", "성대를 세게 닫고 시작한다"],
        "alternative_explanations": ["의도적 악센트", "녹음 시작 클리핑", "레벨 설정"],
        "references": [],
        "direction": "abrupt_or_soft_onset",
    },
    {
        "rule_id": "REGISTER_CONTINUITY_V1",
        "mechanism_id": "register_transition_coordination",
        "version": "1.1",
        "literature_strength": "CONDITIONAL",
        "evidence_families": ["register_continuity"],
        "minimum_families": 1,
        "required_tasks_any": ["siren"],
        "confidence_cap": 0.65,
        "allowed_status": "needs_attention",
        "allowed_user_claim": (
            "음높이를 옮길 때 F0/유성음 연속성이 끊기는 구간이 관찰됐어요. "
            "TA/CT 협응을 직접 추정하지는 않습니다."
        ),
        "forbidden_claims": ["CT가 약하다", "TA가 부족하다", "레지스터가 깨졌다(질환)"],
        "alternative_explanations": ["좁은 음역만 사용", "의도적 스타일", "피치 추적 오류"],
        "references": [],
        "direction": "interrupted",
    },
    {
        "rule_id": "PHONATION_STABILITY_V1",
        "mechanism_id": "phonation_stability",
        "version": "1.1",
        "literature_strength": "CONDITIONAL",
        "evidence_families": ["temporal_stability"],
        "minimum_families": 1,
        "required_tasks_any": ["sustain_a", "sustain_i"],
        "confidence_cap": 0.68,
        "allowed_status": "needs_attention",
        "allowed_user_claim": (
            "지속음 국소 구간에서 F0 잔차 변동이 큰 편이에요. "
            "전역 멜로디 변화나 의도적 비브라토와는 구분합니다."
        ),
        "forbidden_claims": ["성대 손상", "tremor 진단"],
        "alternative_explanations": ["피로", "작은 음량", "피치 추적 잡음", "비브라토"],
        "references": ["saldias_2024_perturbation_fo_vibrato"],
        "direction": "unstable",
    },
]


def get_rules_for(mechanism_id: str) -> list[dict[str, Any]]:
    from ..config import canonicalize_mechanism_id

    mid = canonicalize_mechanism_id(mechanism_id)
    return [r for r in RULES if r["mechanism_id"] == mid]


def all_rules() -> list[dict[str, Any]]:
    return list(RULES)
