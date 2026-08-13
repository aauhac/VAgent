"""Vocal Style Profile v1 + NAQ contract + register canonical + lifecycle tests."""

from __future__ import annotations

import numpy as np
import pytest

from audio_analyzer.coach_profile.register_strategy import classify_source_balance
from audio_analyzer.glottal_source.source_params import compute_source_params
from audio_analyzer.vocal_style.engine import build_vocal_style_profile
from audio_analyzer.vocal_style.register_canonical import build_canonical_register_assessment


def test_naq_producer_consumer_scale_matches():
    """NAQ must be dimensionless ~O(0.01–1), not inflated by sample rate."""
    from audio_analyzer.coach_profile import config as cfg

    sr = 16000
    t = np.arange(0, 0.25, 1 / sr)
    # Synthetic glottal-like pulses
    flow = np.sin(2 * np.pi * 120 * t)
    flow = np.maximum(flow, 0.0)
    out = compute_source_params(flow, sr, f0_hz=120.0)
    assert out.get("valid")
    naq = float(out["estimated_naq"])
    assert 0.01 <= naq <= 2.0, f"NAQ out of physical-ish range: {naq}"
    assert naq < cfg.ABS_NAQ_HEAD * 50  # not ~sr-scaled hundreds


def test_naq_absolute_threshold_units_match_value():
    from audio_analyzer.coach_profile import config as cfg

    assert 0.01 <= cfg.ABS_NAQ_CHEST <= 0.5
    assert 0.01 <= cfg.ABS_NAQ_HEAD <= 0.5
    assert cfg.ABS_NAQ_CHEST < cfg.ABS_NAQ_HEAD


def test_naq_does_not_generate_head_vote_from_scale_bug():
    """Huge legacy-scale NAQ must not appear with fixed producer."""
    sr = 16000
    rng = np.random.default_rng(0)
    flow = np.abs(rng.normal(0, 0.3, size=sr // 2))
    out = compute_source_params(flow, sr, f0_hz=150.0)
    if out.get("valid") and out.get("estimated_naq") is not None:
        assert float(out["estimated_naq"]) < 50


def test_relative_naq_delta_uses_same_unit():
    from audio_analyzer.coach_profile import config as cfg

    # Relative deltas must be same order as absolute priors
    assert abs(cfg.NAQ_CHEST_DELTA) < 1.0
    assert abs(cfg.NAQ_HEAD_DELTA) < 1.0
    assert abs(cfg.NAQ_HEAD_DELTA) < cfg.ABS_NAQ_HEAD * 5


def test_conflicting_families_not_labeled_balanced():
    out = classify_source_balance(0.50, family_agreement=0.30, directionality=0.05)
    assert out["balance_class"] == "CONFLICTED"
    assert out.get("show_ratio") is False
    assert "균형형" not in (out.get("label") or "")


def test_true_balanced_evidence_can_be_balanced():
    out = classify_source_balance(0.50, family_agreement=0.80, directionality=0.05)
    assert out["balance_class"] == "BALANCED_ACOUSTIC"
    assert "균형" in (out.get("label") or "")


def test_source_balance_does_not_define_vocal_style_alone():
    style = build_vocal_style_profile(
        vocal_type_profile={
            "modifiers": [],
            "source_balance": {
                "balance_class": "BALANCED_ACOUSTIC",
                "chest_percent": 52,
                "head_percent": 48,
                "confidence_label": "medium",
                "show_ratio": True,
                "label": "균형",
            },
            "register_strategy": {"status": "UNRESOLVED"},
        },
        dimensions={},
        effort_assessment={"severity": "LOW"},
    )
    assert style["style_id"] != "BALANCED_SOURCE"
    # Without multi-axis support, stay unresolved rather than invent balance style
    assert style["style_id"] in ("UNRESOLVED", "EASY_CONNECTED", "STABLE_CONNECTED")


def test_low_agreement_near_half_ratio_is_conflicted_or_unresolved():
    out = classify_source_balance(0.52, family_agreement=0.48, directionality=0.10)
    assert out["balance_class"] in ("CONFLICTED", "UNRESOLVED")


def test_firm_high_effort_archetype():
    style = build_vocal_style_profile(
        vocal_type_profile={
            "modifiers": ["FIRM_CONTACT", "EXCESS_EFFORT"],
            "source_balance": {
                "balance_class": "BALANCED_ACOUSTIC",
                "chest_percent": 52,
                "head_percent": 48,
                "confidence_label": "medium",
                "show_ratio": True,
            },
            "register_strategy": {"status": "UNRESOLVED"},
        },
        dimensions={
            "air_leakage_breathiness": {"status": "LOW", "summary": "낮은 편"},
            "glottal_contact_profile": {"status": "OBSERVED", "summary": "단단함 쪽"},
        },
        effort_assessment={"severity": "MODERATE", "label": "힘이 들어가는 편"},
    )
    assert style["style_id"] == "FIRM_HIGH_EFFORT"
    assert "힘" in style["display_name"] or "접촉" in style["display_name"]
    assert "균형형" not in style["display_name"]


def test_mokjabi_style_not_balanced_only():
    style = build_vocal_style_profile(
        vocal_type_profile={
            "modifiers": ["FIRM_CONTACT", "EXCESS_EFFORT"],
            "display_name": "흉성·두성 균형형",
            "source_balance": {
                "balance_class": "CONFLICTED",
                "label": "서로 다른 방향",
                "show_ratio": False,
                "confidence_label": "low",
            },
            "register_strategy": {"status": "UNRESOLVED"},
        },
        dimensions={
            "air_leakage_breathiness": {"status": "LOW"},
            "glottal_contact_profile": {"status": "OBSERVED", "summary": "단단함"},
            "vocal_effort_strain": {"status": "OCCASIONAL"},
        },
        effort_assessment={"severity": "MODERATE"},
    )
    assert style["style_id"] == "FIRM_HIGH_EFFORT"
    assert style["axes"]["effort"]["value"] == "HIGH"
    assert style["axes"]["contact"]["value"] == "FIRM"


def test_easy_connected_archetype():
    style = build_vocal_style_profile(
        vocal_type_profile={
            "modifiers": [],
            "register_strategy": {
                "status": "MIX_LIKE_BALANCED",
                "mix_evidence": "SUFFICIENT",
            },
            "source_balance": {"balance_class": "BALANCED_ACOUSTIC", "confidence_label": "medium"},
        },
        dimensions={
            "register_configuration": {"status": "STABLE_LIKE"},
            "phonation_regularity": {"status": "STABLE"},
        },
        effort_assessment={"severity": "LOW"},
    )
    assert style["style_id"] in ("EASY_CONNECTED", "STABLE_CONNECTED")
    assert style["canonical_register"]["status"] == "CONNECTED"


def test_light_airy_archetype():
    style = build_vocal_style_profile(
        vocal_type_profile={
            "modifiers": ["WEAK_CONTACT", "AIR_LEAKAGE"],
            "register_strategy": {"status": "UNRESOLVED"},
            "source_balance": {"balance_class": "HEAD_LEANING", "confidence_label": "medium"},
        },
        dimensions={
            "air_leakage_breathiness": {"status": "HIGH"},
            "glottal_contact_profile": {"status": "OBSERVED", "summary": "가벼운"},
        },
        effort_assessment={"severity": "LOW"},
    )
    assert style["style_id"] == "LIGHT_AIRY"


def test_bright_present_archetype():
    style = build_vocal_style_profile(
        vocal_type_profile={"modifiers": [], "register_strategy": {"status": "UNRESOLVED"}},
        dimensions={
            "resonance_formant_strategy": {
                "status": "OBSERVED",
                "summary": "밝기 밝은 편 · 중역 높은 편",
            }
        },
        timbre_profile={
            "available": True,
            "axes": {
                "brightness": {"value": "BRIGHT"},
                "presence": {"value": "HIGH"},
            },
        },
        effort_assessment={"severity": "LOW"},
    )
    assert style["style_id"] == "BRIGHT_PRESENT"


def test_archetype_requires_multiple_axes():
    style = build_vocal_style_profile(
        vocal_type_profile={
            "modifiers": ["FIRM_CONTACT"],
            "register_strategy": {"status": "UNRESOLVED"},
            "source_balance": {"balance_class": "UNKNOWN"},
        },
        dimensions={},
        effort_assessment=None,
    )
    # Only contact available → unresolved (need ≥2 axes)
    assert style["style_id"] == "UNRESOLVED"


def test_unresolved_style_not_invented():
    style = build_vocal_style_profile(
        vocal_type_profile={"modifiers": [], "register_strategy": {"status": "UNRESOLVED"}},
        dimensions={},
    )
    assert style["style_id"] == "UNRESOLVED"
    assert "확인된 발성 특징" in style["display_name"]


def test_easy_loud_not_high_effort_style():
    """편안세게 invariant: loud/presence != high effort."""
    style = build_vocal_style_profile(
        vocal_type_profile={
            "modifiers": ["WEAK_CONTACT", "AIR_LEAKAGE", "LOW_RESONANCE_PRESENCE"],
            "register_strategy": {"status": "UNRESOLVED"},
            "source_balance": {
                "balance_class": "BALANCED_ACOUSTIC",
                "chest_percent": 51,
                "head_percent": 49,
                "confidence_label": "medium",
                "show_ratio": True,
            },
        },
        dimensions={
            "glottal_contact_profile": {"status": "OBSERVED", "summary": "가벼운"},
            "air_leakage_breathiness": {"status": "OCCASIONAL"},
            "resonance_formant_strategy": {"status": "OBSERVED", "summary": "중역 높은 편"},
        },
        effort_assessment={"severity": "LOW", "label": "편안한 편"},
    )
    assert style["style_id"] != "FIRM_HIGH_EFFORT"
    assert style["axes"]["effort"]["value"] == "LOW"


def test_breathy_head_anchor_not_equated_with_head_register():
    style = build_vocal_style_profile(
        vocal_type_profile={
            "modifiers": ["WEAK_CONTACT", "AIR_LEAKAGE"],
            "register_strategy": {"status": "HEAD_DOMINANT"},
            "source_balance": {
                "balance_class": "HEAD_DOMINANT",
                "confidence_label": "medium",
                "show_ratio": True,
                "chest_percent": 41,
                "head_percent": 59,
            },
        },
        dimensions={
            "air_leakage_breathiness": {"status": "HIGH"},
            "glottal_contact_profile": {"status": "OBSERVED", "summary": "가벼운"},
        },
        effort_assessment={"severity": "LOW"},
    )
    assert style["style_id"] == "LIGHT_AIRY"
    # Source tendency alone is not register connection
    assert style["canonical_register"]["status"] in ("UNRESOLVED", "CONFLICTED", "PARTIAL")


def test_canonical_register_single_source_of_truth():
    can = build_canonical_register_assessment(
        register_strategy={
            "status": "MIX_LIKE_BALANCED",
            "mix_evidence": "SUFFICIENT",
        },
        dimensions={"register_configuration": {"status": "EVENT"}},
        mode="SONG_DETAIL",
    )
    # Positive mix evidence wins over conflicting dimension → not dual labels
    assert can["status"] in ("CONNECTED", "CONFLICTED")
    assert can["profile_label"]
    assert can["title"]


def test_vocal_type_and_profile_cannot_disagree_register():
    style = build_vocal_style_profile(
        vocal_type_profile={
            "modifiers": [],
            "register_strategy": {
                "status": "MIX_LIKE_BALANCED",
                "mix_evidence": "SUFFICIENT",
                "title": "믹스 성향",
            },
        },
        dimensions={"register_configuration": {"status": "TRANSITION_EVENT"}},
        effort_assessment={"severity": "LOW"},
    )
    pub = style["register_strategy_public"]
    can = style["canonical_register"]
    assert pub["title"] == can["title"]
    assert pub["profile_label"] == can["profile_label"]
    # Must not simultaneously claim mix-connected and "다소 급함"
    if can["status"] == "CONNECTED":
        assert "급" not in (can["profile_label"] or "")


def test_conflicting_register_evidence_becomes_conflicted():
    can = build_canonical_register_assessment(
        register_strategy={"status": "UNRESOLVED"},
        dimensions={"register_configuration": {"status": "STABLE_LIKE"}},
        controlled_siren={"status": "DISRUPTED", "register_status": "DISRUPTED"},
        mode="PRECISION",
    )
    # Siren priority in precision
    assert can["status"] in ("DISRUPTED", "CONFLICTED")


def test_controlled_siren_has_priority_in_precision():
    can = build_canonical_register_assessment(
        register_strategy={"status": "MIX_LIKE_BALANCED", "mix_evidence": "SUFFICIENT"},
        dimensions={"register_configuration": {"status": "EVENT"}},
        controlled_siren={"register_status": "CONNECTED"},
        mode="PRECISION",
    )
    assert can["status"] == "CONNECTED"
    assert any("siren" in p for p in can["provenance"])


def test_mokjabi_not_forced_head_from_breathiness():
    style = build_vocal_style_profile(
        vocal_type_profile={
            "modifiers": ["FIRM_CONTACT", "EXCESS_EFFORT"],
            "register_strategy": {"status": "UNRESOLVED"},
            "source_balance": {"balance_class": "CONFLICTED", "show_ratio": False},
        },
        dimensions={"air_leakage_breathiness": {"status": "LOW"}},
        effort_assessment={"severity": "MODERATE"},
    )
    assert style["axes"]["breathiness"]["value"] == "LOW"
    assert style["style_id"] != "HEAD_DRIVEN"


def test_mokjabi_head_vote_provenance_explainable():
    """Family conflict remains explainable; style still firm-high-effort."""
    out = classify_source_balance(0.48, family_agreement=0.478, directionality=0.106)
    assert out["balance_class"] == "CONFLICTED"
    style = build_vocal_style_profile(
        vocal_type_profile={
            "modifiers": ["FIRM_CONTACT", "EXCESS_EFFORT"],
            "source_balance": {**out, "chest_percent": 52, "head_percent": 48},
            "register_strategy": {"status": "UNRESOLVED"},
        },
        dimensions={"air_leakage_breathiness": {"status": "LOW"}},
        effort_assessment={"severity": "MODERATE"},
    )
    assert style["style_id"] == "FIRM_HIGH_EFFORT"


BANNED_COPY = (
    "실제 흉성을",
    "실제 두성을",
    "목을 사용",
    "목 근육이 긴장",
    "후두가",
    "복압이",
)


def test_production_copy_blocks_anatomical_and_usage_claims():
    style = build_vocal_style_profile(
        vocal_type_profile={
            "modifiers": ["FIRM_CONTACT", "EXCESS_EFFORT"],
            "register_strategy": {"status": "UNRESOLVED"},
            "source_balance": {
                "balance_class": "CONFLICTED",
                "label": "흉성·두성 관련 음향 특징이 서로 다른 방향으로 나타났어요",
                "show_ratio": False,
            },
        },
        effort_assessment={"severity": "MODERATE"},
    )
    blob = " ".join(
        [
            style["display_name"],
            style["description"],
            str(style.get("source_balance_presentation")),
        ]
    )
    for banned in BANNED_COPY:
        assert banned not in blob
    # Anatomical acronyms as whole tokens only
    assert " TA " not in f" {blob} "
    assert " CT " not in f" {blob} "
