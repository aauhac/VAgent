"""Question semantics registry for Dynamic Concern QA v3.

Maps every concern_id → question type + candidate factor priorities.
Not a causal truth table — defines what evidence to inspect first.
"""

from __future__ import annotations

from typing import Any

TYPE_DESCRIPTIVE = "DESCRIPTIVE_PROFILE"
TYPE_PERCEPTUAL = "PERCEPTUAL_CAUSAL"
TYPE_FUNCTIONAL = "FUNCTIONAL_DIFFICULTY"
TYPE_CONTROL = "CONTROL_COORDINATION"
TYPE_SAFETY = "SAFETY"
TYPE_OTHER = "OTHER"

# Factor ids used in scoring / practice mapping
FACTOR_REGISTER = "REGISTER_CONNECTION"
FACTOR_EFFORT = "EFFORT"
FACTOR_CONTACT = "CONTACT"
FACTOR_STABILITY = "STABILITY"
FACTOR_PRESENCE = "PRESENCE"
FACTOR_BRIGHTNESS = "BRIGHTNESS"
FACTOR_BREATHINESS = "BREATHINESS"
FACTOR_TIMBRE = "TIMBRE"
FACTOR_AIRINESS = "AIRINESS"
FACTOR_TEXTURE = "TEXTURE"
FACTOR_DYNAMICS = "DYNAMICS"
FACTOR_HIGH_NOTE = "HIGH_NOTE"
FACTOR_SAFETY = "SAFETY"
FACTOR_MAINTAIN = "MAINTAIN"

QUESTION_SEMANTICS: dict[str, dict[str, Any]] = {
    # --- High note / functional ---
    "HIGH_NOTE_CANNOT_REACH": {
        "type": TYPE_FUNCTIONAL,
        "category": "high_note",
        "candidate_factors": [
            FACTOR_REGISTER,
            FACTOR_EFFORT,
            FACTOR_CONTACT,
            FACTOR_STABILITY,
            FACTOR_HIGH_NOTE,
            FACTOR_PRESENCE,
        ],
        "practice_required": True,
        "fallback_focus": FACTOR_REGISTER,
    },
    "HIGH_NOTE_TOO_EFFORTFUL": {
        "type": TYPE_FUNCTIONAL,
        "category": "high_note",
        "candidate_factors": [
            FACTOR_EFFORT,
            FACTOR_CONTACT,
            FACTOR_REGISTER,
            FACTOR_STABILITY,
        ],
        "practice_required": True,
        "fallback_focus": FACTOR_EFFORT,
    },
    "HIGH_NOTE_FLIPS": {
        "type": TYPE_FUNCTIONAL,
        "category": "high_note",
        "candidate_factors": [
            FACTOR_REGISTER,
            FACTOR_STABILITY,
            FACTOR_EFFORT,
            FACTOR_PRESENCE,
        ],
        "practice_required": True,
        "fallback_focus": FACTOR_REGISTER,
    },
    "HIGH_NOTE_THINS": {
        "type": TYPE_FUNCTIONAL,
        "category": "high_note",
        "candidate_factors": [
            FACTOR_BREATHINESS,
            FACTOR_AIRINESS,
            FACTOR_PRESENCE,
            FACTOR_CONTACT,
            FACTOR_REGISTER,
        ],
        "practice_required": True,
        "fallback_focus": FACTOR_PRESENCE,
    },
    "HIGH_NOTE_UNSTABLE": {
        "type": TYPE_FUNCTIONAL,
        "category": "high_note",
        "candidate_factors": [
            FACTOR_STABILITY,
            FACTOR_EFFORT,
            FACTOR_REGISTER,
        ],
        "practice_required": True,
        "fallback_focus": FACTOR_STABILITY,
    },
    "THROAT_EFFORT": {
        "type": TYPE_FUNCTIONAL,
        "category": "effort",
        "candidate_factors": [FACTOR_EFFORT, FACTOR_CONTACT, FACTOR_REGISTER, FACTOR_STABILITY],
        "practice_required": True,
        "fallback_focus": FACTOR_EFFORT,
    },
    "LOUD_VOICE_DIFFICULT": {
        "type": TYPE_FUNCTIONAL,
        "category": "effort",
        "candidate_factors": [FACTOR_EFFORT, FACTOR_DYNAMICS, FACTOR_CONTACT],
        "practice_required": True,
        "fallback_focus": FACTOR_EFFORT,
    },
    "VOCAL_FATIGUE": {
        "type": TYPE_FUNCTIONAL,
        "category": "effort",
        "candidate_factors": [FACTOR_EFFORT, FACTOR_DYNAMICS, FACTOR_STABILITY],
        "practice_required": True,
        "fallback_focus": FACTOR_EFFORT,
    },
    "AFTER_SINGING_FATIGUE": {
        "type": TYPE_FUNCTIONAL,
        "category": "effort",
        "candidate_factors": [FACTOR_EFFORT, FACTOR_STABILITY, FACTOR_BREATHINESS],
        "practice_required": True,
        "fallback_focus": FACTOR_EFFORT,
    },
    # --- Timbre / perceptual / descriptive ---
    "TIMBRE_DISSATISFIED": {
        "type": TYPE_DESCRIPTIVE,
        "category": "timbre",
        "candidate_factors": [
            FACTOR_BRIGHTNESS,
            FACTOR_PRESENCE,
            FACTOR_AIRINESS,
            FACTOR_BREATHINESS,
            FACTOR_CONTACT,
            FACTOR_TEXTURE,
            FACTOR_TIMBRE,
        ],
        "practice_required": False,
        "fallback_focus": FACTOR_TIMBRE,
    },
    "VOICE_TOO_THIN": {
        "type": TYPE_PERCEPTUAL,
        "category": "timbre",
        "candidate_factors": [
            FACTOR_BREATHINESS,
            FACTOR_AIRINESS,
            FACTOR_PRESENCE,
            FACTOR_CONTACT,
            FACTOR_REGISTER,
        ],
        "practice_required": True,
        "fallback_focus": FACTOR_PRESENCE,
    },
    "VOICE_TOO_DARK_MUFFLED": {
        "type": TYPE_PERCEPTUAL,
        "category": "timbre",
        "candidate_factors": [
            FACTOR_BRIGHTNESS,
            FACTOR_PRESENCE,
            FACTOR_TIMBRE,
            FACTOR_CONTACT,
            FACTOR_EFFORT,
        ],
        "practice_required": True,
        "fallback_focus": FACTOR_PRESENCE,
    },
    "VOICE_TOO_NASAL_PERCEPT": {
        "type": TYPE_PERCEPTUAL,
        "category": "timbre",
        "candidate_factors": [FACTOR_PRESENCE, FACTOR_BRIGHTNESS, FACTOR_CONTACT, FACTOR_TIMBRE],
        "practice_required": True,
        "fallback_focus": FACTOR_TIMBRE,
    },
    "VOICE_TOO_BREATHY": {
        "type": TYPE_PERCEPTUAL,
        "category": "timbre",
        "candidate_factors": [FACTOR_BREATHINESS, FACTOR_AIRINESS, FACTOR_CONTACT, FACTOR_STABILITY],
        "practice_required": True,
        "fallback_focus": FACTOR_BREATHINESS,
    },
    "VOICE_TOO_SHARP": {
        "type": TYPE_PERCEPTUAL,
        "category": "timbre",
        "candidate_factors": [
            FACTOR_BRIGHTNESS,
            FACTOR_PRESENCE,
            FACTOR_TEXTURE,
            FACTOR_CONTACT,
        ],
        "practice_required": True,
        "fallback_focus": FACTOR_BRIGHTNESS,
    },
    "VOICE_ROUGH": {
        "type": TYPE_PERCEPTUAL,
        "category": "timbre",
        "candidate_factors": [
            FACTOR_STABILITY,
            FACTOR_TEXTURE,
            FACTOR_CONTACT,
            FACTOR_BREATHINESS,
        ],
        "practice_required": True,
        "fallback_focus": FACTOR_STABILITY,
    },
    "TIMBRE_CHANGES_HIGH": {
        "type": TYPE_PERCEPTUAL,
        "category": "timbre",
        "candidate_factors": [
            FACTOR_REGISTER,
            FACTOR_PRESENCE,
            FACTOR_BRIGHTNESS,
            FACTOR_BREATHINESS,
            FACTOR_EFFORT,
        ],
        "practice_required": True,
        "fallback_focus": FACTOR_REGISTER,
    },
    # --- Control ---
    "PITCH_UNSTABLE": {
        "type": TYPE_CONTROL,
        "category": "control",
        "candidate_factors": [FACTOR_STABILITY, FACTOR_EFFORT, FACTOR_REGISTER],
        "practice_required": True,
        "fallback_focus": FACTOR_STABILITY,
    },
    "REGISTER_CONNECTION_DIFFICULT": {
        "type": TYPE_CONTROL,
        "category": "control",
        "candidate_factors": [FACTOR_REGISTER, FACTOR_EFFORT, FACTOR_STABILITY],
        "practice_required": True,
        "fallback_focus": FACTOR_REGISTER,
    },
    "VIBRATO_UNSTABLE": {
        "type": TYPE_CONTROL,
        "category": "control",
        "candidate_factors": [FACTOR_STABILITY, FACTOR_EFFORT],
        "practice_required": True,
        "fallback_focus": FACTOR_STABILITY,
    },
    "DYNAMICS_DIFFICULT": {
        "type": TYPE_CONTROL,
        "category": "control",
        "candidate_factors": [FACTOR_DYNAMICS, FACTOR_EFFORT, FACTOR_CONTACT],
        "practice_required": True,
        "fallback_focus": FACTOR_DYNAMICS,
    },
    "PHRASE_END_WEAK": {
        "type": TYPE_CONTROL,
        "category": "control",
        "candidate_factors": [FACTOR_DYNAMICS, FACTOR_STABILITY, FACTOR_BREATHINESS],
        "practice_required": True,
        "fallback_focus": FACTOR_DYNAMICS,
    },
    # --- Safety ---
    "PAIN_WHILE_SINGING": {
        "type": TYPE_SAFETY,
        "category": "safety",
        "candidate_factors": [FACTOR_SAFETY],
        "practice_required": True,
        "fallback_focus": FACTOR_SAFETY,
    },
    "PAIN_AFTER_SINGING": {
        "type": TYPE_SAFETY,
        "category": "safety",
        "candidate_factors": [FACTOR_SAFETY],
        "practice_required": True,
        "fallback_focus": FACTOR_SAFETY,
    },
    "SPEAKING_DISCOMFORT": {
        "type": TYPE_SAFETY,
        "category": "safety",
        "candidate_factors": [FACTOR_SAFETY],
        "practice_required": True,
        "fallback_focus": FACTOR_SAFETY,
    },
    "PERSISTENT_HOARSENESS": {
        "type": TYPE_SAFETY,
        "category": "safety",
        "candidate_factors": [FACTOR_SAFETY],
        "practice_required": True,
        "fallback_focus": FACTOR_SAFETY,
    },
    "OTHER_CONCERN": {
        "type": TYPE_OTHER,
        "category": "other",
        "candidate_factors": [FACTOR_EFFORT, FACTOR_REGISTER, FACTOR_TIMBRE, FACTOR_STABILITY],
        "practice_required": False,
        "fallback_focus": FACTOR_MAINTAIN,
    },
}


def semantics_for(concern_id: str) -> dict[str, Any]:
    return dict(
        QUESTION_SEMANTICS.get(
            concern_id,
            {
                "type": TYPE_OTHER,
                "category": "other",
                "candidate_factors": [FACTOR_MAINTAIN],
                "practice_required": False,
                "fallback_focus": FACTOR_MAINTAIN,
            },
        )
    )


def question_type_for(concern_id: str) -> str:
    return str(semantics_for(concern_id).get("type") or TYPE_OTHER)


def audited_concern_ids() -> list[str]:
    return sorted(QUESTION_SEMANTICS.keys())
