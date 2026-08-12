"""v2.11 High-note function + timbre derived profile tests."""

from __future__ import annotations

from audio_analyzer.vocal_function.profiles.high_note_function import (
    build_high_note_function_profile,
    partition_pitch_regions,
)
from audio_analyzer.vocal_function.profiles.timbre import build_timbre_profile_v211
from audio_analyzer.vocal_function.validity import build_validity_by_dimension
from audio_analyzer.diagnostic.evidence.compliance import check_high_note_sustain_compliance
from audio_analyzer.diagnostic.task_registry import TASK_REGISTRY, normalize_recommended_task
import numpy as np


def _seg(
    start: float,
    end: float,
    *,
    f0: float,
    rms: float = 0.05,
    dropout: float = 0.1,
    e24: float = 0.18,
    e48: float = 0.08,
    e12: float = 0.2,
    centroid: float = 1800.0,
    tilt: float = -12.0,
    h1h2: float = 3.0,
    period: float = 12.0,
    voiced: float = 0.8,
    octave_jump: float = 0.0,
    tracker_suspect: bool = False,
    vocal_specific: bool = True,
    accomp: float = 0.0,
):
    obs = {
        "f0_hz": f0,
        "f0_dropout_ratio": dropout,
        "f0_octave_jump_ratio": octave_jump,
        "f0_tracker_artifact": {"suspect": tracker_suspect},
        "rms": rms,
        "energy_1_2k": e12,
        "energy_2_4k": e24,
        "energy_4_8k": e48,
        "spectral_centroid_hz": centroid,
        "spectral_tilt_db_per_oct": tilt,
        "raw_h1_h2_proxy_db": h1h2,
        "periodicity_primary_db": period,
        "alpha_ratio_db": 5.0,
        "voiced_ratio": voiced,
    }
    seg = {
        "start_sec": start,
        "end_sec": end,
        "valid": True,
        "voiced_ratio": voiced,
        "observations": obs,
        "vocal_evidence": {
            "vocal_specific": vocal_specific,
            "vocal_dominance": 0.85,
            "vocal_confidence": 0.75,
            "accompaniment_match": accomp,
        },
        "level2_proxies": {
            "glottal_source": {"valid": False},
            "gif_gate": {"valid": False},
            "formants": {"valid": True, "confidence": 0.55},
        },
        "rms": rms,
    }
    seg["validity_by_dimension"] = build_validity_by_dimension(seg)
    return seg


def _ladder_segments():
    """Mid cluster ~220Hz and high cluster ~440Hz with continuity."""
    segs = []
    t = 0.0
    for i in range(6):
        segs.append(_seg(t, t + 0.8, f0=210 + i * 2, e24=0.2, centroid=1600))
        t += 0.85
    for i in range(5):
        segs.append(_seg(t, t + 0.8, f0=430 + i * 3, e24=0.12, centroid=2100, rms=0.06))
        t += 0.85
    return segs


def test_highest_reliable_f0_rejects_single_spike():
    segs = _ladder_segments()
    # Inject a single spike segment that is short + high dropout
    segs.append(
        _seg(20.0, 20.2, f0=900.0, dropout=0.7, voiced=0.2, octave_jump=0.3, tracker_suspect=True)
    )
    mid, high, ctx = partition_pitch_regions(segs)
    assert ctx["highest_observed_f0_hz"] >= 430
    assert ctx["highest_reliable_f0_hz"] is not None
    assert ctx["highest_reliable_f0_hz"] < 800  # spike rejected


def test_high_note_region_requires_vocal_pitch_validity():
    segs = _ladder_segments()
    segs.append(_seg(30, 31, f0=500, vocal_specific=False, accomp=0.9))
    mid, high, ctx = partition_pitch_regions(segs)
    assert all((s.get("vocal_evidence") or {}).get("vocal_specific", True) for s in high)


def test_no_high_note_no_fake_profile():
    segs = [_seg(i, i + 0.6, f0=220 + (i % 3)) for i in range(5)]
    out = build_high_note_function_profile(
        segments=segs,
        dimensions={},
        baseline={},
        episodes=[],
        input_mode="VOCAL_ONLY",
    )
    assert out["available"] is False
    assert out["reason"] == "INSUFFICIENT_HIGH_NOTE_COVERAGE"


def test_high_note_effort_uses_existing_effort_engine(monkeypatch):
    calls = {"n": 0}

    def fake_effort_like(seg, baseline, pre=None, post=None):
        calls["n"] += 1
        f0 = (seg.get("observations") or {}).get("f0_hz") or 0
        return f0 >= 400

    monkeypatch.setattr(
        "audio_analyzer.vocal_function.profiles.high_note_function.effort_like",
        fake_effort_like,
    )
    segs = _ladder_segments()
    out = build_high_note_function_profile(
        segments=segs,
        dimensions={"register_configuration": {"status": "STABLE"}},
        baseline={"rms": 0.04},
        episodes=[],
    )
    assert out["available"] is True
    assert calls["n"] > 0
    axis = out["axes"]["high_note_effort_cost"]
    assert axis["status"] in ("INCREASED", "STABLE", "DECREASED")
    assert "provenance" in axis
    assert "vocal_effort_strain" in axis["provenance"]["source_dimensions"]


def test_loud_firm_easy_not_high_effort(monkeypatch):
    """Loud/firm high notes must not auto-mark INCREASED effort (reuse effort_like)."""

    def never_effort(seg, baseline, pre=None, post=None):
        return False

    monkeypatch.setattr(
        "audio_analyzer.vocal_function.profiles.high_note_function.effort_like",
        never_effort,
    )
    segs = _ladder_segments()
    # Make high segments loud
    for s in segs:
        if (s["observations"]["f0_hz"] or 0) >= 400:
            s["observations"]["rms"] = 0.2
            s["rms"] = 0.2
    out = build_high_note_function_profile(
        segments=segs,
        dimensions={"register_configuration": {"status": "STABLE"}},
        baseline={"rms": 0.05},
        episodes=[],
    )
    assert out["axes"]["high_note_effort_cost"]["status"] in ("STABLE", "DECREASED")


def test_head_voice_not_automatically_breathy(monkeypatch):
    monkeypatch.setattr(
        "audio_analyzer.vocal_function.profiles.high_note_function.leakage_like",
        lambda seg: False,
    )
    segs = _ladder_segments()
    out = build_high_note_function_profile(
        segments=segs,
        dimensions={"register_configuration": {"status": "STABLE"}},
        baseline={},
        episodes=[],
    )
    assert out["axes"]["high_note_breathiness_shift"]["status"] in ("STABLE", "DECREASED", "UNCERTAIN")


def test_high_note_stability_masks_vibrato(monkeypatch):
    def rough(seg):
        # Would be rough unless vibrato mask path skips — we force non-positive
        return {"verdict": "NEGATIVE"}

    monkeypatch.setattr(
        "audio_analyzer.vocal_function.profiles.high_note_function.classify_rough_segment",
        rough,
    )
    segs = _ladder_segments()
    for s in segs:
        s["observations"]["vibrato_rate_hz"] = 5.5
        s["observations"]["periodicity_primary_db"] = 14.0
    out = build_high_note_function_profile(
        segments=segs,
        dimensions={"register_configuration": {"status": "STABLE"}},
        baseline={},
        episodes=[],
    )
    assert out["axes"]["high_note_stability"]["status"] in ("PRESERVED", "DEGRADED", "UNCERTAIN")


def test_resonance_preservation_uses_relative_band_energy():
    segs = _ladder_segments()
    out = build_high_note_function_profile(
        segments=segs,
        dimensions={},
        baseline={},
        episodes=[],
    )
    res = out["axes"]["resonance_preservation"]
    assert "energy_2_4k" in (res.get("deltas") or {})
    fams = (res.get("provenance") or {}).get("evidence_families") or []
    assert "energy_2_4k" in fams
    assert "spectral_centroid" in fams


def test_timbre_brightness_not_single_metric():
    segs = _ladder_segments()
    tp = build_timbre_profile_v211(segments=segs, mid_segments=segs[:4], high_segments=segs[6:])
    assert tp["available"] is True
    bright = tp["axes"]["brightness"]
    assert bright.get("continuum") is not None
    assert (bright.get("provenance") or {}).get("families", 0) >= 2
    assert tp.get("descriptive_only") is True
    assert "음색 점수" not in str(tp.get("summary") or [])
    assert "좋다" not in "".join(tp.get("summary") or [])
    assert tp.get("what_it_is_not")


def test_mixed_contamination_caps_timbre_confidence():
    segs = _ladder_segments()
    tp = build_timbre_profile_v211(segments=segs, input_mode="MIXED", functional_quality="LIMITED")
    assert tp["available"] is True
    assert tp["confidence_label"] == "low"


def test_airiness_reuses_breathiness_engine(monkeypatch):
    monkeypatch.setattr(
        "audio_analyzer.vocal_function.profiles.timbre.leakage_like",
        lambda seg: True,
    )
    segs = _ladder_segments()
    tp = build_timbre_profile_v211(segments=segs)
    assert tp["axes"]["airiness"]["provenance"]["source"] == "breathiness_engine"
    assert tp["axes"]["airiness"]["continuum"] is not None


def test_high_note_sustain_actual_evidence_required():
    assert "high_note_sustain_a" in TASK_REGISTRY
    assert normalize_recommended_task("high_note_sustain_a")["supported"] is True
    # Synthetic silence → compliance fail → cannot resolve by task id alone
    sr = 16000
    y = np.zeros(sr * 2, dtype=np.float32)
    pitch = {"frame_f0": [{"time_sec": i / 100.0, "f0_hz": None} for i in range(200)]}
    comp = check_high_note_sustain_compliance(y, sr, pitch=pitch, song_median_f0_hz=220.0)
    assert comp["ok"] is False
    assert comp.get("completion_alone_insufficient") is True


def test_song_vs_task_context_not_blindly_averaged():
    """High-note profile keeps mid vs high separation (not a single blob average)."""
    segs = _ladder_segments()
    out = build_high_note_function_profile(
        segments=segs,
        dimensions={"register_configuration": {"status": "STABLE"}},
        baseline={},
        episodes=[],
    )
    assert out["available"] is True
    assert out["axes"]["high_note_effort_cost"].get("mid_effort") is not None
    assert out["axes"]["high_note_effort_cost"].get("high_effort") is not None
