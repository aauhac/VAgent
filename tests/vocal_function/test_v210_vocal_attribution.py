"""v2.10 — vocal attribution vs pitch tracking vs claim suitability."""

from __future__ import annotations

from audio_analyzer.vocal_function.vocal_attribution import (
    STATE_CONFIRMED,
    STATE_REJECTED,
    STATE_UNCERTAIN,
    aggregate_episode_vocal_attribution,
    claim_vocal_suitability,
    classify_segment_vocal_attribution,
    evaluate_target_vocal_eligibility,
)


def test_low_f0_alone_not_non_vocal():
    a = classify_segment_vocal_attribution(
        vocal_dominance=0.8,
        vocal_vs_instrumental_ratio=3.0,
        vocal_energy=0.05,
        f0_confidence=0.1,
        voicing_confidence=0.5,
        periodicity_confidence=0.4,
        accompaniment_match=0.1,
        stem_present=True,
    )
    assert a["state"] != STATE_REJECTED
    assert a["state"] == STATE_CONFIRMED


def test_low_voicing_alone_not_non_vocal():
    a = classify_segment_vocal_attribution(
        vocal_dominance=0.75,
        vocal_vs_instrumental_ratio=2.5,
        vocal_energy=0.04,
        f0_confidence=0.5,
        voicing_confidence=0.1,
        periodicity_confidence=0.4,
        accompaniment_match=0.1,
        stem_present=True,
    )
    assert a["state"] != STATE_REJECTED


def test_high_accomp_low_dominance_rejected():
    a = classify_segment_vocal_attribution(
        vocal_dominance=0.3,
        vocal_vs_instrumental_ratio=0.4,
        vocal_energy=0.01,
        f0_confidence=0.8,
        voicing_confidence=0.8,
        periodicity_confidence=0.7,
        accompaniment_match=0.8,
        stem_present=True,
    )
    assert a["state"] == STATE_REJECTED


def test_strong_dominance_low_f0_effort_usable_register_not():
    a = classify_segment_vocal_attribution(
        vocal_dominance=0.85,
        vocal_vs_instrumental_ratio=4.0,
        vocal_energy=0.06,
        f0_confidence=0.1,
        voicing_confidence=0.2,
        periodicity_confidence=0.2,
        accompaniment_match=0.05,
        stem_present=True,
    )
    assert a["state"] == STATE_CONFIRMED
    effort = claim_vocal_suitability("effort", a)
    register = claim_vocal_suitability("register", a)
    assert effort["eligible"] is True
    assert register["eligible"] is False


def test_episode_confirmed_uncertain_confirmed():
    def _m(state):
        return {
            "validity": {
                "vocal_attribution": {
                    "state": state,
                    "confidence_score": 0.7,
                    "vocal_dominance": 0.7,
                    "accompaniment_match": 0.1,
                    "tracking": {"f0_confidence": 0.2},
                    "positive_families": ["stem_attribution"],
                    "negative_families": [],
                }
            }
        }

    ep = aggregate_episode_vocal_attribution(
        [_m(STATE_CONFIRMED), _m(STATE_UNCERTAIN), _m(STATE_CONFIRMED)],
        claim_family="effort",
    )
    assert ep["state"] == STATE_CONFIRMED


def test_episode_rejected_rejected_uncertain():
    def _m(state, acc=0.8):
        return {
            "validity": {
                "vocal_attribution": {
                    "state": state,
                    "confidence_score": 0.3,
                    "vocal_dominance": 0.3,
                    "accompaniment_match": acc,
                    "tracking": {"f0_confidence": 0.5},
                    "positive_families": [],
                    "negative_families": ["accompaniment_spectral_match"],
                }
            }
        }

    ep = aggregate_episode_vocal_attribution(
        [_m(STATE_REJECTED), _m(STATE_REJECTED), _m(STATE_UNCERTAIN)],
        claim_family="effort",
    )
    assert ep["state"] == STATE_REJECTED


def test_single_legacy_false_member_does_not_reject_episode():
    members = [
        {
            "validity": {
                "vocal_specific": True,
                "vocal_attribution": {
                    "state": STATE_CONFIRMED,
                    "confidence_score": 0.8,
                    "vocal_dominance": 0.8,
                    "accompaniment_match": 0.1,
                    "tracking": {"f0_confidence": 0.2},
                    "positive_families": ["stem_attribution"],
                    "negative_families": [],
                },
            }
        },
        {
            "validity": {
                "vocal_specific": False,  # legacy false (tracking weak)
                "vocal_attribution": {
                    "state": STATE_UNCERTAIN,
                    "confidence_score": 0.5,
                    "vocal_dominance": 0.7,
                    "accompaniment_match": 0.1,
                    "tracking": {"f0_confidence": 0.1},
                    "positive_families": ["stem_attribution"],
                    "negative_families": [],
                },
            }
        },
        {
            "validity": {
                "vocal_specific": True,
                "vocal_attribution": {
                    "state": STATE_CONFIRMED,
                    "confidence_score": 0.75,
                    "vocal_dominance": 0.75,
                    "accompaniment_match": 0.1,
                    "tracking": {"f0_confidence": 0.3},
                    "positive_families": ["stem_attribution"],
                    "negative_families": [],
                },
            }
        },
    ]
    ep = aggregate_episode_vocal_attribution(members, claim_family="effort")
    assert ep["state"] == STATE_CONFIRMED


def test_all_uncertain_blocks_primary():
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
    ] * 3
    primary = {"id": "GENERAL_EXCESS_EFFORT", "confidence_label": "medium"}
    target = {
        "type": "GENERAL_EFFORT",
        "members": members,
        "feature_matrix": {
            "validity": aggregate_episode_vocal_attribution(members, claim_family="effort")
        },
    }
    # Put full attr into validity
    target["feature_matrix"]["validity"] = {
        "episode_vocal_attribution": aggregate_episode_vocal_attribution(
            members, claim_family="effort"
        )
    }
    gate = evaluate_target_vocal_eligibility(primary, target)
    assert gate["status"] == "UNCERTAIN"


def test_confirmed_effort_survives_weak_f0():
    members = [
        {
            "validity": {
                "vocal_attribution": {
                    "state": STATE_CONFIRMED,
                    "confidence_score": 0.8,
                    "vocal_dominance": 0.85,
                    "accompaniment_match": 0.05,
                    "tracking": {"f0_confidence": 0.1, "voicing_confidence": 0.15},
                    "f0_confidence": 0.1,
                    "positive_families": ["stem_attribution"],
                    "negative_families": [],
                }
            }
        }
    ]
    ep = aggregate_episode_vocal_attribution(members, claim_family="effort")
    primary = {"id": "GENERAL_EXCESS_EFFORT", "confidence_label": "medium"}
    target = {
        "type": "GENERAL_EFFORT",
        "members": members,
        "feature_matrix": {"validity": {"episode_vocal_attribution": ep}},
    }
    gate = evaluate_target_vocal_eligibility(primary, target)
    assert gate["status"] == "ELIGIBLE"


def test_register_confirmed_but_f0_insufficient():
    members = [
        {
            "validity": {
                "vocal_attribution": {
                    "state": STATE_CONFIRMED,
                    "confidence_score": 0.8,
                    "vocal_dominance": 0.85,
                    "accompaniment_match": 0.05,
                    "tracking": {"f0_confidence": 0.1},
                    "f0_confidence": 0.1,
                    "positive_families": ["stem_attribution"],
                    "negative_families": [],
                }
            }
        }
    ]
    ep = aggregate_episode_vocal_attribution(members, claim_family="register")
    primary = {"id": "REGISTER_TRANSITION_DISRUPTION", "confidence_label": "medium"}
    target = {
        "type": "REGISTER_TRANSITION",
        "members": members,
        "feature_matrix": {"validity": {"episode_vocal_attribution": ep}},
    }
    gate = evaluate_target_vocal_eligibility(primary, target)
    assert gate["status"] == "REJECTED"
    assert "f0" in (gate.get("reason") or "")


def test_no_stem_low_voiced_not_rejected():
    a = classify_segment_vocal_attribution(
        vocal_dominance=0.1,
        vocal_vs_instrumental_ratio=None,
        vocal_energy=0.02,
        f0_confidence=0.05,
        voicing_confidence=0.05,
        periodicity_confidence=0.1,
        accompaniment_match=0.0,
        stem_present=False,
        voiced_ratio=0.05,
    )
    assert a["state"] != STATE_REJECTED


def test_core_span_contamination_rejects_episode():
    def _m(state, acc, dom):
        return {
            "start_sec": 0.0,
            "end_sec": 1.0,
            "validity": {
                "vocal_attribution": {
                    "state": state,
                    "confidence_score": 0.5,
                    "vocal_dominance": dom,
                    "accompaniment_match": acc,
                    "tracking": {"f0_confidence": 0.5},
                    "positive_families": [],
                    "negative_families": ["accompaniment_spectral_match"] if state == STATE_REJECTED else [],
                }
            },
        }

    members = [
        _m(STATE_CONFIRMED, 0.1, 0.8),
        _m(STATE_CONFIRMED, 0.1, 0.8),
        _m(STATE_REJECTED, 0.85, 0.2),
    ]
    # core only the contaminated window
    core = [members[2]]
    members[2]["start_sec"] = 1.0
    members[2]["end_sec"] = 2.0
    ep = aggregate_episode_vocal_attribution(members, claim_family="effort", core_members=core)
    assert ep["state"] == STATE_REJECTED
    assert "core_span_contaminated" in (ep.get("reason_codes") or [])


def test_breathy_weak_f0_not_rejected():
    a = classify_segment_vocal_attribution(
        vocal_dominance=0.8,
        vocal_vs_instrumental_ratio=3.0,
        vocal_energy=0.04,
        f0_confidence=0.12,
        voicing_confidence=0.15,
        periodicity_confidence=0.2,
        accompaniment_match=0.1,
        stem_present=True,
    )
    assert a["state"] != STATE_REJECTED
    assert claim_vocal_suitability("breathiness", a)["eligible"] is True
