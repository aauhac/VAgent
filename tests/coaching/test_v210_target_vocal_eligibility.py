"""v2.10 Primary target vocal eligibility (ranker unchanged)."""

from __future__ import annotations

from audio_analyzer.coaching.bottleneck.ranker import select_primary
from audio_analyzer.vocal_function.vocal_attribution import (
    STATE_CONFIRMED,
    STATE_REJECTED,
    STATE_UNCERTAIN,
    evaluate_target_vocal_eligibility,
)


def test_ranker_thresholds_unchanged_medium_required():
    hyps = [
        {
            "id": "GENERAL_EXCESS_EFFORT",
            "confidence_label": "low",
            "supporting_episode_ids": ["e1"],
            "supporting_evidence": [{"x": 1}],
        }
    ]
    primary, _, trace = select_primary(hyps, criteria_matrix=None)
    assert primary is None
    assert any(r["reason"] == "confidence_below_medium" for r in trace)


def test_gate_eligible_does_not_require_legacy_vocal_specific_true_on_members():
    members = [
        {
            "validity": {
                "vocal_specific": False,
                "vocal_attribution": {
                    "state": STATE_CONFIRMED,
                    "confidence_score": 0.8,
                    "vocal_dominance": 0.8,
                    "accompaniment_match": 0.05,
                    "tracking": {"f0_confidence": 0.15},
                    "f0_confidence": 0.15,
                    "positive_families": ["stem_attribution"],
                    "negative_families": [],
                },
            }
        }
    ]
    from audio_analyzer.vocal_function.vocal_attribution import (
        aggregate_episode_vocal_attribution,
    )

    ep = aggregate_episode_vocal_attribution(members, claim_family="effort")
    gate = evaluate_target_vocal_eligibility(
        {"id": "GENERAL_EXCESS_EFFORT", "confidence_label": "medium"},
        {
            "type": "GENERAL_EFFORT",
            "members": members,
            "feature_matrix": {"validity": {"episode_vocal_attribution": ep}},
        },
    )
    assert gate["status"] == "ELIGIBLE"


def test_gate_uncertain_blocks():
    members = [
        {
            "validity": {
                "vocal_attribution": {
                    "state": STATE_UNCERTAIN,
                    "confidence_score": 0.4,
                    "vocal_dominance": 0.5,
                    "accompaniment_match": 0.2,
                    "tracking": {"f0_confidence": 0.2},
                    "positive_families": [],
                    "negative_families": [],
                }
            }
        }
    ]
    from audio_analyzer.vocal_function.vocal_attribution import (
        aggregate_episode_vocal_attribution,
    )

    ep = aggregate_episode_vocal_attribution(members, claim_family="effort")
    gate = evaluate_target_vocal_eligibility(
        {"id": "GENERAL_EXCESS_EFFORT"},
        {
            "type": "GENERAL_EFFORT",
            "members": members,
            "feature_matrix": {"validity": {"episode_vocal_attribution": ep}},
        },
    )
    assert gate["status"] == "UNCERTAIN"


def test_gate_non_vocal_blocks():
    members = [
        {
            "validity": {
                "vocal_attribution": {
                    "state": STATE_REJECTED,
                    "confidence_score": 0.2,
                    "vocal_dominance": 0.2,
                    "accompaniment_match": 0.85,
                    "tracking": {"f0_confidence": 0.9},
                    "positive_families": [],
                    "negative_families": ["accompaniment_spectral_match"],
                }
            }
        }
    ]
    from audio_analyzer.vocal_function.vocal_attribution import (
        aggregate_episode_vocal_attribution,
    )

    ep = aggregate_episode_vocal_attribution(members, claim_family="effort")
    gate = evaluate_target_vocal_eligibility(
        {"id": "GENERAL_EXCESS_EFFORT"},
        {
            "type": "GENERAL_EFFORT",
            "members": members,
            "feature_matrix": {"validity": {"episode_vocal_attribution": ep}},
        },
    )
    assert gate["status"] == "REJECTED"
    assert gate["reason"] == "target_non_vocal_contamination"
