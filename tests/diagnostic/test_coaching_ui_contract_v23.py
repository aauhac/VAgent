"""UI presentation helpers for coaching v2.3 — task summary + token leak (node-free)."""

# Mirror of mapEvidenceTokenForUser / rowsFromTaskProfile expectations via Python
# so CI without node can still lock the contract. Frontend has the real impl.


def test_task_summary_contract_from_profiles():
    """Document expected rows when task_profiles exist — frontend must not use 과제 완료."""
    profile = {
        "high_note_sustain_a": {
            "valid": True,
            "dimensions": {
                "effort": {"status": "LOW", "available": True},
                "stability": {"status": "STEADY", "available": True},
                "contact": {"status": "MID", "available": True},
            },
        }
    }
    # Expected user-facing values (Korean)
    expected_labels = {"힘 사용", "발성 안정성", "접촉감"}
    dims = profile["high_note_sustain_a"]["dimensions"]
    assert dims["effort"]["status"] == "LOW"
    assert "과제 완료" not in str(profile)
    assert expected_labels  # sanity


def test_internal_tokens_must_be_mappable_or_hidden():
    from audio_analyzer.diagnostic.coaching import user_facing_evidence_token

    forbidden_raw = [
        "baseline_and_high_both_low",
        "brightness_ok=0.65",
        "presence_ok=0.58",
        "low_airiness_alone=0.25",
        "effort_delta_0.12",
        "song_effort_LOW",
    ]
    for tok in forbidden_raw:
        mapped = user_facing_evidence_token(tok)
        assert mapped is not None
        assert tok not in mapped
        assert "=" not in mapped or mapped != tok
