"""v2.13 — Chest/Head balance != Mix classification."""

from __future__ import annotations

from audio_analyzer.coach_profile.naming import classify_base_type, compose_display_name
from audio_analyzer.coach_profile.register_strategy import (
    classify_register_strategy,
    classify_source_balance,
    positive_mix_transition_evidence,
)


def _bridge_smooth(**extra):
    b = {
        "type": "SMOOTH_BRIDGE",
        "score": 0.75,
        "available": True,
        "register_sufficiency": "SUFFICIENT",
        "n_transition_opportunities": 4,
        "split_eligibility": {"eligible": False, "n_opportunities": 4},
    }
    b.update(extra)
    return b


def _bridge_insufficient(**extra):
    b = {
        "type": "UNDETERMINED",
        "score": 0.47,
        "available": True,
        "register_sufficiency": "INSUFFICIENT",
        "n_transition_opportunities": 3,
        "split_eligibility": {
            "eligible": False,
            "n_opportunities": 3,
            "break_prevalence": 0.0,
            "f0_disrupted": True,
            "source_disrupted": True,
        },
    }
    b.update(extra)
    return b


def test_balanced_chest_head_does_not_imply_mix():
    t = classify_base_type(
        index=0.52,
        bridge=_bridge_insufficient(),
        modifiers=[],
        confidence="medium",
    )
    assert t not in ("BALANCED_MIX", "CHEST_DOMINANT_MIX", "HEAD_DOMINANT_MIX")
    assert "MIX" not in t


def test_ratio_only_cannot_produce_mix():
    t = classify_base_type(
        index=0.50,
        bridge={
            "type": "UNDETERMINED",
            "score": 0.5,
            "register_sufficiency": "INSUFFICIENT",
            "split_eligibility": {"eligible": False, "break_prevalence": 0.0},
        },
        modifiers=["FIRM_CONTACT", "EXCESS_EFFORT"],
        confidence="medium",
        family_agreement=0.9,
        mix_coverage_ok=True,
    )
    assert "MIX" not in t


def test_balanced_without_transition_evidence_is_unresolved():
    s = classify_register_strategy(
        index=0.50,
        bridge=_bridge_insufficient(),
        confidence="medium",
        family_agreement=0.5,
    )
    assert s["status"] == "UNRESOLVED"
    assert s["mix_evidence"] == "INSUFFICIENT"
    assert classify_source_balance(0.50)["balance_class"] == "BALANCED"


def test_balanced_with_transition_disruption_is_not_mix():
    s = classify_register_strategy(
        index=0.50,
        bridge={
            "type": "ABRUPT_REGISTER_BREAK",
            "score": 0.25,
            "register_sufficiency": "SUFFICIENT",
            "split_eligibility": {"eligible": True},
        },
        confidence="medium",
        register_split_ok=True,
    )
    assert s["status"] == "TRANSITION_UNSTABLE"
    assert "MIX" not in (s.get("type_id") or "")


def test_chest_dominant_can_still_be_mix_like():
    s = classify_register_strategy(
        index=0.28,
        bridge=_bridge_smooth(),
        confidence="medium",
    )
    assert s["status"] == "MIX_LIKE_CHEST_DOMINANT"
    assert s["type_id"] == "CHEST_DOMINANT_MIX"


def test_head_dominant_can_still_be_mix_like():
    s = classify_register_strategy(
        index=0.72,
        bridge=_bridge_smooth(),
        confidence="medium",
    )
    assert s["status"] == "MIX_LIKE_HEAD_DOMINANT"
    assert s["type_id"] == "HEAD_DOMINANT_MIX"


def test_firm_contact_does_not_imply_mix():
    t = classify_base_type(
        index=0.50,
        bridge=_bridge_insufficient(),
        modifiers=["FIRM_CONTACT"],
        confidence="medium",
    )
    assert "MIX" not in t
    name = compose_display_name(
        t,
        ["FIRM_CONTACT"],
        source_balance=classify_source_balance(0.50),
        register_strategy=classify_register_strategy(
            index=0.50, bridge=_bridge_insufficient(), confidence="medium"
        ),
    )
    assert "믹스" not in name
    assert "단단한 믹스" not in name


def test_high_effort_does_not_define_mix():
    t = classify_base_type(
        index=0.50,
        bridge=_bridge_insufficient(),
        modifiers=["EXCESS_EFFORT"],
        confidence="medium",
    )
    assert "MIX" not in t


def test_low_effort_does_not_define_mix():
    t = classify_base_type(
        index=0.50,
        bridge=_bridge_insufficient(),
        modifiers=[],
        confidence="medium",
    )
    assert "MIX" not in t


def test_mix_requires_transition_evidence():
    gate = positive_mix_transition_evidence(_bridge_insufficient())
    assert gate["ok"] is False
    gate2 = positive_mix_transition_evidence(_bridge_smooth())
    assert gate2["ok"] is True


def test_insufficient_pitch_coverage_blocks_mix():
    # Smooth bridge but mix_coverage_ok False
    t = classify_base_type(
        index=0.50,
        bridge=_bridge_smooth(),
        modifiers=[],
        confidence="medium",
        mix_coverage_ok=False,
        family_agreement=0.6,
    )
    # Without coverage, should not claim mix
    assert t in ("BALANCED_SOURCE", "UNRESOLVED", "CHEST_DOMINANT", "HEAD_DOMINANT")


def test_register_disruption_is_contra_evidence():
    gate = positive_mix_transition_evidence(
        {
            "type": "ABRUPT_REGISTER_BREAK",
            "score": 0.2,
            "register_sufficiency": "SUFFICIENT",
            "split_eligibility": {"eligible": True},
        }
    )
    assert gate["ok"] is False
    assert "abrupt_register_break" in gate["reasons_block"] or "register_split_eligible" in gate[
        "reasons_block"
    ]


def test_mix_label_uses_register_confidence():
    s = classify_register_strategy(
        index=0.50,
        bridge=_bridge_smooth(),
        confidence="high",
        family_agreement=0.6,
    )
    assert s["status"] == "MIX_LIKE_BALANCED"
    assert s["confidence_label"] in ("high", "medium")


def test_compound_firm_mix_title_removed():
    name = compose_display_name(
        "BALANCED_MIX",
        ["FIRM_CONTACT", "EXCESS_EFFORT"],
        register_strategy={
            "status": "MIX_LIKE_BALANCED",
            "mix_evidence": "SUFFICIENT",
        },
    )
    assert "단단한 믹스보이스" not in name
    assert "힘이 함께 증가" not in name
    assert "믹스" in name


def test_source_balance_and_register_strategy_render_separately():
    bal = classify_source_balance(0.48)
    reg = classify_register_strategy(
        index=0.48, bridge=_bridge_insufficient(), confidence="medium"
    )
    assert bal["balance_class"] == "BALANCED"
    assert reg["status"] == "UNRESOLVED"
    title = compose_display_name(
        "BALANCED_SOURCE",
        ["FIRM_CONTACT", "EXCESS_EFFORT"],
        source_balance=bal,
        register_strategy=reg,
    )
    assert title == "흉성·두성 균형형"
    assert "믹스" not in title
    assert "힘" not in title


def test_siren_completion_alone_does_not_create_mix():
    # Completing a task is not modeled as a bridge type; empty/undetermined stays unresolved
    t = classify_base_type(
        index=0.50,
        bridge={
            "type": "UNDETERMINED",
            "score": None,
            "register_sufficiency": "PARTIAL",
            "n_transition_opportunities": 0,
        },
        modifiers=[],
        confidence="medium",
        mix_coverage_ok=True,
    )
    assert "MIX" not in t


def test_actual_siren_evidence_can_resolve_register_strategy():
    t = classify_base_type(
        index=0.50,
        bridge=_bridge_smooth(),
        modifiers=[],
        confidence="medium",
        family_agreement=0.55,
        mix_coverage_ok=True,
    )
    assert t == "BALANCED_MIX"
