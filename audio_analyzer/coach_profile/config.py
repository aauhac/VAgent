"""Coach Profile / Vocal Type Engine configuration (v1.2)."""

from __future__ import annotations

COACH_PROFILE_VERSION = "vocal-type-v1.3"
CALIBRATION_STATUS = "semantic_calibration_v1_3"

# Soft directional cues — relative to local baseline
NAQ_CHEST_DELTA = -0.02
NAQ_HEAD_DELTA = 0.03
OQ_CHEST_DELTA = -0.04
OQ_HEAD_DELTA = 0.05
H1H2_CHEST_DELTA = -1.5
H1H2_HEAD_DELTA = 2.0
MFDR_CHEST_RATIO = 1.15
TILT_CHEST = -10.0
TILT_HEAD = -16.0

# Absolute priors (used when personal baseline ineligible) — weak but directional
ABS_NAQ_CHEST = 0.09
ABS_NAQ_HEAD = 0.14
ABS_H1H2_CHEST = 3.0
ABS_H1H2_HEAD = 9.0
ABS_PRIOR_WEIGHT = 0.55  # weaker than relative evidence (1.0)

# Evidence-mass gates
MIN_EVIDENCE_MASS_SEGMENT = 0.55
MIN_SOURCE_FAMILIES_FOR_RATIO = 1
MIN_FAMILIES_FOR_SEGMENT = 2
MIN_SEGMENTS_FOR_RATIO = 3
MIN_SEGMENTS_FOR_HIGH_CONF = 6
MIN_SONG_EVIDENCE_MASS = 1.8
MIN_FAMILY_COVERAGE_SONG = 1.5
MIN_FAMILY_AGREEMENT_HIGH = 0.55
MIN_BASELINE_SAMPLES = 3
MIN_BASELINE_STD_FRAC = 0.02  # relative std / |median|

# Family weights (documented; ablation audits justify changes)
WEIGHT_FLOW = 1.0
WEIGHT_HARMONIC = 0.85
WEIGHT_SPECTRAL = 0.55
WEIGHT_CONTACT = 0.25  # supporting only; never alone

# Reliability downs
BREATHY_HARMONIC_RELIABILITY = 0.35
BREATHY_SPECTRAL_RELIABILITY = 0.40
ROUGH_RELIABILITY = 0.25
FORMANT_LOW_HARMONIC_RELIABILITY = 0.45

# Pitch bands — context only
F0_LOW_MAX = 220.0
F0_MID_MAX = 350.0

# Bridge / global split
BRIDGE_SMOOTH_MIN = 0.62
BRIDGE_POOR_MAX = 0.38
REGISTER_SPLIT_MIN_EVENTS = 2
REGISTER_SPLIT_MIN_PREVALENCE = 0.35  # of transition opportunities
REGISTER_SPLIT_MIN_OPPORTUNITIES = 3
NEUTRAL_COLLAPSE_EPS = 0.04

# Type thresholds
CHEST_DOMINANT_MAX = 0.32
HEAD_DOMINANT_MIN = 0.68
MIX_LOW = 0.33
MIX_HIGH = 0.67
CHEST_LEAN_MAX = 0.45  # soft lean within mix band
HEAD_LEAN_MIN = 0.55

TYPE_DISPLAY = {
    "CHEST_DOMINANT": "흉성 쪽 성향이 더 강한 편",
    "CHEST_DOMINANT_MIX": "흉성 중심의 믹스 성향",
    "BALANCED_MIX": "흉성·두성을 연결하는 믹스 성향",
    "BALANCED_SOURCE": "흉성·두성 균형형",
    "HEAD_DOMINANT_MIX": "두성 중심의 믹스 성향",
    "HEAD_DOMINANT": "두성 쪽 성향이 더 강한 편",
    "LIGHT_HEAD_FALSETTO_LIKE": "가벼운 두성 중심 발성",
    "REGISTER_SPLIT": "성구 전환이 급격한 편",
    "REGISTER_SPLIT_GLOBAL": "성구 전환이 급격한 편",
    "TRANSITION_UNSTABLE": "성구 전환이 급격한 편",
    "UNRESOLVED": "발성 성향 판단 보류",
}

LOCAL_EVENT_DISPLAY = {
    "LOCAL_CHEST_PULL": "일부 고음에서 흉성 비중을 오래 유지",
    "LOCAL_EARLY_HEAD_SHIFT": "일부 구간에서 두성 쪽으로 전환이 빠름",
    "LOCAL_ABRUPT_BREAK": "일부 전환에서 성구가 급격히 바뀜",
    "LOCAL_UNSTABLE_BRIDGE": "일부 전환이 불안정",
    "LOCAL_EFFORT_SPIKE": "일부 고음에서 힘 증가",
}

MODIFIER_DISPLAY = {
    "WEAK_CONTACT": "접촉이 가벼운 편",
    "FIRM_CONTACT": "접촉이 단단한 편",
    "AIR_LEAKAGE": "기식성 경향",
    "EXCESS_EFFORT": "고음에서 힘 증가",
    "CHEST_PULL": "일부 구간에서 흉성을 오래 유지",
    "EARLY_HEAD_SHIFT": "일부 구간에서 두성 전환이 빠름",
    "PASSAGGIO_BREAK": "일부 전환에서 성구가 급함",
    "LOW_RESONANCE_PRESENCE": "중역 존재감 부족",
    "HIGH_NOTE_RESONANCE_LOSS": "고음 공명 집중도 저하",
    "HARD_ONSET": "급격한 시작",
    "ROUGHNESS": "거친 음질 경향",
    "GOOD_BRIDGE": "성구 연결이 안정적",
}

FAMILY_IDS = ("SOURCE_FLOW", "HARMONIC_SOURCE", "CONTACT", "SPECTRAL_WEIGHT")

# Ablation / audit: documented weight change log (v1.1 → v1.2)
WEIGHT_CHANGE_LOG = [
    {
        "family": "CONTACT",
        "old": 0.35,
        "new": 0.25,
        "reason": "contact alone flipped general sample toward head; keep supporting-only",
    },
    {
        "family": "HARMONIC_SOURCE",
        "old": 1.0,
        "new": 0.85,
        "reason": "raw H1-H2 overlaps breathiness; downweight + reliability gate",
    },
    {
        "family": "SPECTRAL_WEIGHT",
        "old": 0.7,
        "new": 0.55,
        "reason": "spectral alone over-drove when FLOW unavailable",
    },
]
