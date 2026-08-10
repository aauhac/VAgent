"""Coaching decision layer (LEVEL 5) — never skips evidence."""

from __future__ import annotations

from typing import Any, Optional

EXERCISES = [
    {
        "exercise_id": "sovt_straw",
        "target_function": ["vocal_effort_strain", "air_leakage_breathiness"],
        "when_to_use": ["effort_repeated", "abrupt_onset_with_effort"],
        "when_not_to_use": ["pain", "severe_hoarseness"],
        "instructions": "편한 음에서 빨대/좁은 관으로 짧은 SOVT 20–30초.",
        "duration_sec": 30,
        "progression": "음량↓ → 음역 살짝 확장",
        "stop_conditions": ["pain", "dizziness"],
    },
    {
        "exercise_id": "balanced_onset_hum",
        "target_function": ["onset_offset_coordination"],
        "when_to_use": ["abrupt_like"],
        "when_not_to_use": ["pain"],
        "instructions": "허밍으로 부드럽게 시작해 모음으로 열기.",
        "duration_sec": 20,
        "progression": "시작 더 부드럽게",
        "stop_conditions": ["pain"],
    },
    {
        "exercise_id": "siren_ng",
        "target_function": ["register_configuration"],
        "when_to_use": ["transition_disruption"],
        "when_not_to_use": ["pain"],
        "instructions": "ng로 작은 사이렌, 전환 구간만 부드럽게.",
        "duration_sec": 25,
        "progression": "범위 조금씩 확장",
        "stop_conditions": ["pain", "strain_increase"],
    },
    {
        "exercise_id": "messa_di_voce_short",
        "target_function": ["respiratory_phonatory_coordination", "phonatory_economy_proxy"],
        "when_to_use": ["end_phrase_drop", "dynamic_swell_goal"],
        "when_not_to_use": ["pain"],
        "instructions": "한 음에서 작게→조금 크게→작게 (무리한 크게 금지).",
        "duration_sec": 20,
        "progression": "강도 범위 아주 조금 확장",
        "stop_conditions": ["pain"],
    },
]


def identify_functional_problems(profile: dict[str, Any]) -> list[dict[str, Any]]:
    dims = profile.get("dimensions") or {}
    problems = []
    effort = dims.get("vocal_effort_strain") or {}
    if effort.get("status") in ("MODERATE", "REPEATED", "OCCASIONAL"):
        problems.append(
            {
                "problem_id": "effort_like",
                "dimension_id": "vocal_effort_strain",
                "severity": effort.get("status"),
                "layer": "LEVEL_3",
            }
        )
    leak = dims.get("air_leakage_breathiness") or {}
    if leak.get("status") in ("MODERATE", "HIGH"):
        problems.append(
            {
                "problem_id": "leakage_like",
                "dimension_id": "air_leakage_breathiness",
                "severity": leak.get("status"),
                "layer": "LEVEL_3",
            }
        )
    reg = dims.get("register_configuration") or {}
    if reg.get("status") == "TRANSITION_EVENTS":
        problems.append(
            {
                "problem_id": "transition_disruption",
                "dimension_id": "register_configuration",
                "severity": reg.get("status"),
                "layer": "LEVEL_3",
            }
        )
    onset = dims.get("onset_offset_coordination") or {}
    if onset.get("status") == "ABRUPT_LIKE":
        problems.append(
            {
                "problem_id": "abrupt_like",
                "dimension_id": "onset_offset_coordination",
                "severity": onset.get("status"),
                "layer": "LEVEL_3",
            }
        )
    return problems


def prescribe(profile: dict[str, Any], *, style_goal: str = "unspecified") -> dict[str, Any]:
    """Select exercises from functional evidence — no canned strain→SOVT only."""
    problems = identify_functional_problems(profile)
    chosen = []
    for p in problems:
        pid = p["problem_id"]
        for ex in EXERCISES:
            triggers = set(ex["when_to_use"]) | set(ex["target_function"])
            match = (
                pid in triggers
                or p["dimension_id"] in triggers
                or (pid == "effort_like" and "effort_repeated" in ex["when_to_use"])
                or (pid == "abrupt_like" and "abrupt_like" in ex["when_to_use"])
                or (
                    pid == "transition_disruption"
                    and "transition_disruption" in ex["when_to_use"]
                )
            )
            if match and ex["exercise_id"] not in [c["exercise_id"] for c in chosen]:
                chosen.append({**ex, "triggered_by": pid, "style_goal": style_goal})
        if len(chosen) >= 3:
            break
    if not chosen:
        chosen = [
            {
                **EXERCISES[0],
                "triggered_by": "general_maintenance",
                "style_goal": style_goal,
            }
        ]
    return {
        "layer": "LEVEL_5_COACHING_DECISION",
        "problems": problems,
        "exercises": chosen[:3],
        "pre_post_protocol": {
            "enabled": True,
            "record_before": True,
            "exercise_sec": 30,
            "record_after": True,
            "compare_axes": [
                "periodicity",
                "onset_behavior",
                "contact_related_proxy",
            ],
            "wording": "이 운동에 긍정적인 음향 반응이 나타났어요. (치료 효과 표현 금지)",
        },
        "note": "style_goal은 vocabulary/target 선택에만 쓰며 raw score를 바꾸지 않습니다.",
    }


def evaluate_pre_post(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Deterministic acoustic response check — not clinical outcome."""
    keys = [
        "estimated_naq",
        "periodicity_primary_db",
        "onset_slope_db_per_sec",
    ]
    deltas = {}
    improved = 0
    for k in keys:
        b, a = before.get(k), after.get(k)
        if b is None or a is None:
            continue
        deltas[k] = float(a) - float(b)
        if k == "onset_slope_db_per_sec" and a < b:
            improved += 1
        elif k == "periodicity_primary_db" and a > b:
            improved += 1
        elif k == "estimated_naq" and abs(a - b) > 0:  # directional, context-dependent
            improved += 0
    return {
        "deltas": deltas,
        "positive_acoustic_response": improved >= 1,
        "claim": (
            "이 운동에 긍정적인 음향 반응이 나타났어요."
            if improved >= 1
            else "뚜렷한 음향 반응은 제한적이었어요."
        ),
        "not_a_treatment_claim": True,
    }
