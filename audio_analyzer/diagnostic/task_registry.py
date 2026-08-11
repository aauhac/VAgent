"""Supported Adaptive Precision Diagnostic tasks (protocol v1.1).

Only tasks listed here may be selected by the planner or rendered in UX.
Unsupported coaching recommendations are normalized or marked unsupported.
"""

from __future__ import annotations

from typing import Any

PLANNER_VERSION = "adaptive-dx-planner-v1.1"
PROTOCOL_VERSION = "diagnostic-protocol-v1.1"
REPORT_VERSION = "diagnostic-report-v1.1"

# Product-facing dimension keys (planner) → song engine dimension ids
DIMENSION_ALIASES = {
    "contact": "glottal_contact_profile",
    "breathiness": "air_leakage_breathiness",
    "effort": "vocal_effort_strain",
    "register": "register_configuration",
    "stability": "phonation_regularity",
    "roughness": "phonation_regularity",
    "resonance": "resonance_formant_strategy",
    "onset": "onset_offset_coordination",
    "dynamic_response": "respiratory_phonatory_coordination",
}

# Product priority for set-cover (lower index = higher priority)
DIMENSION_PRIORITY = [
    "contact",
    "breathiness",
    "effort",
    "register",
    "stability",
    "resonance",
    "onset",
    "dynamic_response",
]

DIMENSION_USER_LABELS = {
    "contact": "접촉감",
    "breathiness": "숨 섞임",
    "effort": "힘 사용",
    "register": "성구 연결",
    "stability": "발성 안정성",
    "roughness": "발성 안정성",
    "resonance": "공명",
    "onset": "시작음",
    "dynamic_response": "강약 반응",
}

# expected_gain: high=1.0, medium=0.55, low=0.25
TASK_REGISTRY: dict[str, dict[str, Any]] = {
    "sustain_a": {
        "task_id": "sustain_a",
        "covers": ["contact", "breathiness", "stability"],
        "secondary": ["onset", "resonance"],
        "expected_gain": {
            "contact": 1.0,
            "breathiness": 1.0,
            "stability": 1.0,
            "onset": 0.55,
            "resonance": 0.55,
            "roughness": 0.75,
        },
        "cost": 1.0,
        "purpose_labels": ["접촉감", "숨 섞임"],
    },
    "sustain_i": {
        "task_id": "sustain_i",
        "covers": ["contact", "breathiness", "resonance"],
        "secondary": ["stability"],
        "expected_gain": {
            "contact": 0.9,
            "breathiness": 0.9,
            "resonance": 1.0,
            "stability": 0.7,
        },
        "cost": 1.0,
        "purpose_labels": ["접촉감", "공명"],
    },
    "siren": {
        "task_id": "siren",
        "covers": ["register"],
        "secondary": ["effort"],
        "expected_gain": {
            "register": 1.0,
            "effort": 0.4,
        },
        "cost": 1.0,
        "purpose_labels": ["성구 연결"],
    },
    "dynamic_swell": {
        "task_id": "dynamic_swell",
        "covers": ["effort", "dynamic_response"],
        "secondary": ["contact", "stability"],
        "expected_gain": {
            "effort": 1.0,
            "dynamic_response": 1.0,
            "contact": 0.4,
            "stability": 0.35,
        },
        "cost": 1.0,
        "purpose_labels": ["힘 사용", "강약 반응"],
    },
}

# Map legacy / coaching recommended_task strings → supported task ids
RECOMMENDED_TASK_NORMALIZE: dict[str, str | None] = {
    "sustain_a": "sustain_a",
    "sustain_i": "sustain_i",
    "siren": "siren",
    "dynamic_swell": "dynamic_swell",
    "sustain_a_soft": "sustain_a",
    "sustain_a_strong": "sustain_a",
    "sustain_a_comfortable": "sustain_a",
    "sustain_i_comfortable": "sustain_i",
    "strong_sustain_or_high_siren": "sustain_a",
    "siren_five_tone": "siren",
    "five_tone": "siren",
    "siren_ng": "siren",
    "messa_di_voce": "dynamic_swell",
    "messa_di_voce_short": "dynamic_swell",
    "balanced_onset_hum": "sustain_a",
    "sovt_straw": "sustain_a",
    "additional_measurement": None,
    "re_record_with_headphones": None,
}


def normalize_recommended_task(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {"supported": False, "task_id": None, "raw": raw, "status": "empty"}
    key = str(raw).strip()
    if key in TASK_REGISTRY:
        return {"supported": True, "task_id": key, "raw": raw, "status": "exact"}
    mapped = RECOMMENDED_TASK_NORMALIZE.get(key)
    if mapped and mapped in TASK_REGISTRY:
        return {"supported": True, "task_id": mapped, "raw": raw, "status": "normalized"}
    if key in RECOMMENDED_TASK_NORMALIZE and RECOMMENDED_TASK_NORMALIZE[key] is None:
        return {"supported": False, "task_id": None, "raw": raw, "status": "unsupported"}
    return {"supported": False, "task_id": None, "raw": raw, "status": "unsupported"}


def task_covers(task_id: str) -> list[str]:
    meta = TASK_REGISTRY.get(task_id) or {}
    return list(meta.get("covers") or []) + list(meta.get("secondary") or [])


def user_labels_for_dimensions(dims: list[str]) -> list[str]:
    labels: list[str] = []
    seen = set()
    for d in dims:
        lab = DIMENSION_USER_LABELS.get(d) or d
        if lab not in seen:
            seen.add(lab)
            labels.append(lab)
    return labels
