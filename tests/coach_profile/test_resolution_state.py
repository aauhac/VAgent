"""Additive vocal-type resolution_state mapping. Thresholds are not changed here."""

from audio_analyzer.coach_profile.engine import classify_vocal_type_resolution_state


def test_resolved_when_type_is_not_unresolved():
    assert (
        classify_vocal_type_resolution_state(
            base_type="CHEST_DOMINANT",
            confidence="low",
            ratios_available=False,
            balance_class="CONFLICTED",
            neutral_collapse=True,
        )
        == "RESOLVED"
    )


def test_conflicted_evidence_from_source_balance():
    assert (
        classify_vocal_type_resolution_state(
            base_type="UNRESOLVED",
            confidence="medium",
            ratios_available=True,
            balance_class="CONFLICTED",
            neutral_collapse=False,
        )
        == "CONFLICTED_EVIDENCE"
    )


def test_neutral_evidence_from_collapse():
    assert (
        classify_vocal_type_resolution_state(
            base_type="UNRESOLVED",
            confidence="medium",
            ratios_available=False,
            balance_class="BALANCED",
            neutral_collapse=True,
        )
        == "NEUTRAL_EVIDENCE"
    )


def test_insufficient_from_low_confidence():
    assert (
        classify_vocal_type_resolution_state(
            base_type="UNRESOLVED",
            confidence="low",
            ratios_available=False,
            balance_class="UNKNOWN",
            neutral_collapse=False,
        )
        == "INSUFFICIENT_EVIDENCE"
    )
