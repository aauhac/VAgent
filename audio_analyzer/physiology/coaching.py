"""
physiology/coaching.py
----------------------
Motor coaching templates — no intrinsic laryngeal muscle instructions.
"""

from __future__ import annotations

from typing import Any, Optional

from .config import (
    COACHING_VERSION,
    SAFETY_DISCLAIMER,
    SAFETY_STOP_INSTRUCTION,
    canonicalize_mechanism_id,
)


COACHING = {
    "phonation_contact_pattern": {
        "possibly_light_contact": {
            "motor_cue": (
                "목을 조여 접촉을 만들려고 하지 마세요. "
                "가벼운 '음—' 또는 립트릴에서 숨과 소리가 거의 동시에 시작되는 느낌을 찾아보세요."
            ),
            "exercise_id": "lip_trill_to_hum",
            "duration": "립트릴 20초 → '음—' 3초×3 → '아—' 4초×2",
            "reason": "주기성·스펙트럼 계열이 가벼운 쪽 패턴과 일치 (가설)",
            "stop_conditions": SAFETY_STOP_INSTRUCTION,
            "rationale_refs": ["titze_2006_sovt", "hillenbrand_1994_cpp_breathiness"],
        },
        "possibly_firm_contact": {
            "motor_cue": (
                "목 앞쪽으로 힘을 더 주지 말고, 작은 음량에서 공기가 일정하게 흐르는 느낌으로 시작하세요. "
                "첫음을 세게 찍는 대신 부드럽게 연결해 보세요."
            ),
            "exercise_id": "gentle_onset_sovt",
            "duration": "SOVT/립트릴 20초 → soft siren 2회 → light humming 3회",
            "reason": "상대적으로 단단한 쪽 음향 패턴 가설",
            "stop_conditions": SAFETY_STOP_INSTRUCTION,
            "rationale_refs": ["titze_2006_sovt"],
        },
        "balanced": {
            "motor_cue": "지금처럼 목으로 억지로 붙이거나 떼지 않는 느낌을 유지해 보세요.",
            "exercise_id": "maintain_light_hum",
            "duration": "'음—' 4초 × 4",
            "reason": "극단적 접촉 편향이 관찰되지 않음",
            "stop_conditions": SAFETY_STOP_INSTRUCTION,
            "rationale_refs": [],
        },
    },
    "intensity_phonation_coordination": {
        "needs_attention": {
            "motor_cue": (
                "배를 딱딱하게 밀어내기보다, 들이마신 뒤 갈비뼈·옆구리의 확장감이 "
                "갑자기 무너지지 않도록 유지하면서 공기를 일정하게 보내 보세요. "
                "실제 복압이나 폐압을 직접 측정한 것은 아닙니다."
            ),
            "exercise_id": "rib_expansion_swell",
            "duration": "편한 한 음에서 soft→a bit louder→soft 5초 × 4",
            "reason": "강도 envelope 협응 불안정 관측 (호흡압 미측정)",
            "stop_conditions": SAFETY_STOP_INSTRUCTION,
            "rationale_refs": ["titze_2006_sovt"],
        },
        "balanced": {
            "motor_cue": "소리 크기가 바뀔 때 공기 흐름이 급하게 끊기지 않게 유지해 보세요.",
            "exercise_id": "easy_swell",
            "duration": "dynamic swell 5초 × 3",
            "reason": "강도 협응이 비교적 자연스러움",
            "stop_conditions": SAFETY_STOP_INSTRUCTION,
            "rationale_refs": [],
        },
    },
    "onset_coordination": {
        "needs_attention": {
            "motor_cue": "첫음을 세게 찍지 말고, 숨과 소리가 거의 함께 시작되는 느낌을 연습하세요.",
            "exercise_id": "gentle_onset",
            "duration": "'하—'로 부드럽게 시작 → '아—' 연결 5회",
            "reason": "onset 에너지 패턴 가설 (성문 attack 미관측)",
            "stop_conditions": SAFETY_STOP_INSTRUCTION,
            "rationale_refs": [],
        },
        "balanced": {
            "motor_cue": "지금처럼 부드럽게 시작하는 감각을 유지하세요.",
            "exercise_id": "easy_onset_keep",
            "duration": "easy onset 4회",
            "reason": "onset 에너지가 비교적 자연스러움",
            "stop_conditions": SAFETY_STOP_INSTRUCTION,
            "rationale_refs": [],
        },
    },
    "register_transition_coordination": {
        "needs_attention": {
            "motor_cue": "더 높은 음을 목표로 하지 마세요. 편한 범위에서 부드럽게 이어지는지만 확인하세요.",
            "exercise_id": "soft_siren_range",
            "duration": "짧은 soft siren 4회 (무리한 고음 금지)",
            "reason": "F0/유성음 연속성 저하 (근육 미추정)",
            "stop_conditions": SAFETY_STOP_INSTRUCTION,
            "rationale_refs": [],
        },
        "balanced": {
            "motor_cue": "편한 범위의 부드러운 연결감을 유지하세요.",
            "exercise_id": "soft_siren_keep",
            "duration": "soft siren 3회",
            "reason": "전환이 비교적 연속적",
            "stop_conditions": SAFETY_STOP_INSTRUCTION,
            "rationale_refs": [],
        },
    },
    "phonation_stability": {
        "needs_attention": {
            "motor_cue": "큰 소리로 버티기보다 작은 볼륨에서 같은 음을 일정하게 유지해 보세요.",
            "exercise_id": "soft_sustain",
            "duration": "편한 음 3초 유지 × 6",
            "reason": "지속음 국소 F0 잔차 변동",
            "stop_conditions": SAFETY_STOP_INSTRUCTION,
            "rationale_refs": [],
        },
        "balanced": {
            "motor_cue": "작은 볼륨에서도 같은 안정감을 유지해 보세요.",
            "exercise_id": "soft_sustain_keep",
            "duration": "3초 유지 × 4",
            "reason": "지속음이 비교적 안정적",
            "stop_conditions": SAFETY_STOP_INSTRUCTION,
            "rationale_refs": [],
        },
    },
    # WEAK mechanisms: no aggressive coaching when unknown (default)
}


def build_coaching(
    mechanisms: list[dict[str, Any]],
    *,
    safety_flags: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    safety_flags = safety_flags or []
    aggressive_blocked = bool(safety_flags)
    out: list[dict[str, Any]] = []
    priority = 1
    for m in mechanisms:
        mid = canonicalize_mechanism_id(m["mechanism_id"])
        if m.get("status") == "unknown":
            continue
        if mid in ("phonatory_efficiency", "release_coordination", "vocal_tract_resonance_balance"):
            continue  # WEAK: no primary coaching cards
        status = m.get("status")
        table = COACHING.get(mid) or {}
        entry = table.get(status) or table.get("balanced")
        if not entry:
            continue
        # Auxiliary onset: lower priority, still allow gentle cue
        if mid == "onset_coordination" and priority > 3:
            continue
        cue = entry["motor_cue"]
        exercise = entry["duration"]
        if aggressive_blocked:
            cue = (
                "불편감이 있다면 세게 밀거나 오래 버티는 연습은 피하고, "
                "짧은 편한 발성만 참고하세요. "
            ) + cue
            exercise = "짧은 편한 발성 2~3회만 (무리 금지)"
        out.append(
            {
                "mechanism_id": mid,
                "display_name": m.get("display_name"),
                "priority": priority,
                "motor_cue": cue,
                "exercise_id": entry["exercise_id"],
                "duration": exercise,
                "reason": entry["reason"],
                "stop_conditions": entry.get("stop_conditions") or SAFETY_STOP_INSTRUCTION,
                "coaching_version": COACHING_VERSION,
            }
        )
        priority += 1
        if priority > 4:
            break
    return out


def build_training_routine(coaching: list[dict[str, Any]]) -> list[str]:
    if not coaching:
        return ["편한 음에서 '음—' 3초 × 3", "립트릴 20초"]
    return [c["duration"] for c in coaching[:3]]


def safety_disclaimer() -> str:
    return SAFETY_DISCLAIMER
