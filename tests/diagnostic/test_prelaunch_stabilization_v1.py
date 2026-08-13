"""Pre-launch stabilization: high-note range contract + pain severity."""

from __future__ import annotations

import json
from pathlib import Path

from audio_analyzer.diagnostic.concerns import (
    classify_safety_severity,
    filter_tasks_for_safety,
)
from audio_analyzer.vocal_function.profiles.high_note_function import (
    build_high_note_function_profile,
    partition_pitch_regions,
)
from tests.vocal_function.test_v211_high_note_timbre import _ladder_segments, _seg


def test_high_threshold_outside_observed_support_does_not_mean_no_high_note():
    # Narrow cluster (~1 st) → relative thr exceeds observed max
    segs = [_seg(i * 0.7, i * 0.7 + 0.6, f0=380 + (i % 3) * 2) for i in range(5)]
    mid, high, ctx = partition_pitch_regions(segs)
    assert ctx["pitch_range_sufficiency"]["status"] == "INSUFFICIENT"
    assert ctx["pitch_range_sufficiency"]["reason"] == "INSUFFICIENT_PITCH_RANGE"
    assert ctx.get("threshold_outside_observed_support") or ctx["pitch_range_sufficiency"].get(
        "threshold_outside_observed_support"
    )
    out = build_high_note_function_profile(segments=segs, dimensions={})
    assert out["reason"] == "INSUFFICIENT_PITCH_RANGE"
    assert "고음을 못" not in (out.get("reason_user") or "")
    assert "음역 변화" in (out.get("reason_user") or "")
    assert out["available"] is False
    assert out.get("axes") == {}


def test_narrow_pitch_range_returns_insufficient_pitch_range():
    segs = [_seg(i, i + 0.55, f0=220 + i * 0.5) for i in range(6)]
    out = build_high_note_function_profile(segments=segs, dimensions={})
    assert out["reason"] == "INSUFFICIENT_PITCH_RANGE"
    span = (out.get("pitch_context") or {}).get("range_span_semitones")
    assert span is not None and span < 1.5


def test_sufficient_range_builds_upper_region():
    mid, high, ctx = partition_pitch_regions(_ladder_segments())
    assert ctx["pitch_range_sufficiency"]["status"] == "SUFFICIENT"
    assert ctx["n_high_segments"] >= 2
    assert len(high) >= 2
    assert ctx["high_threshold_hz"] <= ctx["highest_observed_f0_hz"] + 1e-6


def test_high_region_reason_is_traceable():
    segs = [_seg(i * 0.7, i * 0.7 + 0.6, f0=370 + i) for i in range(4)]
    out = build_high_note_function_profile(segments=segs, dimensions={})
    assert out.get("reason")
    assert out.get("reason_user")
    assert (out.get("pitch_context") or {}).get("rejection_class") == out["reason"]


def test_high_note_partial_preserves_real_axes():
    segs = _ladder_segments()
    # Keep only one reliable high → PARTIAL path (MIN_HIGH_SEGMENTS=2)
    highish = [s for s in segs if ((s.get("observations") or {}).get("f0_hz") or 0) >= 400]
    midish = [s for s in segs if ((s.get("observations") or {}).get("f0_hz") or 0) < 300]
    trimmed = midish + highish[:1]
    out = build_high_note_function_profile(segments=trimmed, dimensions={})
    if out.get("availability") == "PARTIAL":
        assert out.get("pitch_context", {}).get("highest_reliable_f0_hz") is not None
        # Must not invent full axis suite
        assert "high_note_effort_cost" not in (out.get("axes") or {})
    else:
        # Narrow after trim may be INSUFFICIENT_PITCH_RANGE / COVERAGE — still no fake axes
        assert not any(
            k in (out.get("axes") or {})
            for k in ("high_note_effort_cost", "high_note_stability")
        )


def test_high_note_does_not_fake_candidate_by_clamping_threshold():
    segs = [_seg(i * 0.7, i * 0.7 + 0.6, f0=380 + (i % 2)) for i in range(5)]
    _, high, ctx = partition_pitch_regions(segs)
    assert high == []
    # Threshold may exceed max — must NOT invent candidates via clamp
    if ctx.get("high_threshold_hz") and ctx.get("highest_observed_f0_hz"):
        if ctx["high_threshold_hz"] > ctx["highest_observed_f0_hz"]:
            assert ctx["n_high_segments"] == 0


def test_highest_observed_not_called_absolute_vocal_limit():
    text = Path("miniapp/src/components/report/HighNoteFunctionSection.tsx").read_text(
        encoding="utf-8"
    )
    assert "도달 가능한 고음" not in text
    assert "신뢰 가능하게 확인된 최고 음높이" in text
    assert "당신의 최고음" not in text


def test_user_sample_pitch_range_audit():
    aid = "d2cd74d3d1f4426f992393da0b62d0de"
    path = Path("runtime") / aid / "analysis.json"
    if not path.exists():
        return
    a = json.loads(path.read_text(encoding="utf-8"))
    segs = a["vocal_function_profile"]["scientific_debug"]["segments"]
    mid, high, ctx = partition_pitch_regions(segs)
    out = build_high_note_function_profile(segments=segs, dimensions={})
    assert ctx["pitch_range_sufficiency"]["status"] == "INSUFFICIENT"
    assert out["reason"] == "INSUFFICIENT_PITCH_RANGE"
    assert high == []


def test_pain_on_phonation_blocks_all_controlled_phonation_tasks():
    assert (
        filter_tasks_for_safety(
            ["sustain_a", "siren", "dynamic_swell"],
            pain_flag=True,
            safety_flags=["pain_on_phonation"],
        )
        == []
    )


def test_pain_and_discomfort_not_same_severity():
    assert classify_safety_severity(["pain_on_phonation"]) == "PAIN_LIMITED"
    assert classify_safety_severity(["severe_discomfort_after"]) == "DISCOMFORT"


def test_discomfort_can_keep_policy_safe_tasks():
    out = filter_tasks_for_safety(
        ["sustain_a", "siren", "dynamic_swell", "high_note_sustain_a"],
        pain_flag=True,
        safety_flags=["severe_discomfort_after"],
    )
    assert "sustain_a" in out
    assert "siren" in out
    assert "dynamic_swell" not in out
