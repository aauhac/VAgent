"""Measurement Validation v1 — task evidence gates (diagnostic-protocol-v1.2)."""

from __future__ import annotations

import numpy as np

from audio_analyzer.diagnostic.analyze import analyze_task_audio
from audio_analyzer.diagnostic.fusion import fuse_song_and_task_evidence
from audio_analyzer.diagnostic.task_registry import TASK_REGISTRY


def _tone(dur=4.0, freq=220.0, sr=22050, amp=0.25):
    t = np.arange(int(sr * dur)) / sr
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32), sr


def _swell(dur=5.0, freq=220.0, sr=22050):
    t = np.arange(int(sr * dur)) / sr
    # soft → loud → soft
    env = np.ones_like(t)
    n = len(t)
    env[: n // 3] = np.linspace(0.08, 0.15, n // 3, endpoint=False)
    env[n // 3 : 2 * n // 3] = np.linspace(0.15, 0.45, n // 3, endpoint=False)
    env[2 * n // 3 :] = np.linspace(0.45, 0.1, n - 2 * (n // 3))
    y = (env * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    return y, sr


def _siren(dur=5.0, sr=22050):
    t = np.arange(int(sr * dur)) / sr
    # glide 180→360→180
    f = np.where(t < dur / 2, 180 + 180 * (t / (dur / 2)), 360 - 180 * ((t - dur / 2) / (dur / 2)))
    phase = 2 * np.pi * np.cumsum(f) / sr
    return (0.25 * np.sin(phase)).astype(np.float32), sr


def test_registry_covers_have_evidence_builders():
    """Planner capability must map to real dimension_evidence producers."""
    y, sr = _tone()
    for tid, meta in TASK_REGISTRY.items():
        if tid == "dynamic_swell":
            y2, sr2 = _swell()
            res = analyze_task_audio(y2, sr2, task_id=tid)
        elif tid == "siren":
            y2, sr2 = _siren()
            res = analyze_task_audio(y2, sr2, task_id=tid)
        elif tid == "high_note_sustain_a":
            y2, sr2 = _tone(dur=4.0, freq=440.0)
            res = analyze_task_audio(y2, sr2, task_id=tid)
        else:
            res = analyze_task_audio(y, sr, task_id=tid)
        assert "dimension_evidence" in res
        for dim in meta.get("covers") or []:
            assert dim in res["dimension_evidence"], f"{tid} missing evidence for {dim}"


def test_no_observed_fallback_resolution():
    song = {
        "dimensions": {
            "glottal_contact_profile": {
                "status": "light",
                "confidence_label": "low",
            }
        }
    }
    # Valid-looking task shell WITHOUT dimension_evidence.contact available
    tasks = [
        {
            "task_id": "sustain_a",
            "quality": {"status": "ok"},
            "compliance": {"ok": True},
            "dimension_evidence": {
                "contact": {
                    "dimension_id": "contact",
                    "available": False,
                    "resolution_eligible": False,
                    "confidence_score": None,
                    "reason": "no_contact_families",
                    "quality_valid": True,
                }
            },
            "actual_coverage": [],
        }
    ]
    fused = fuse_song_and_task_evidence(
        song_profile=song,
        task_results=tasks,
        unresolved_before=["contact"],
        selected_tasks=["sustain_a"],
    )
    assert "contact" in fused["remaining_uncertainties"]
    assert fused["fusion_rules"]["observed_marker_fallback"] is False
    assert fused["resolved_dimensions"].get("contact") is None


def test_resolution_eligible_can_resolve():
    song = {
        "dimensions": {
            "glottal_contact_profile": {
                "status": "unknown",
                "confidence_label": "low",
            }
        }
    }
    tasks = [
        {
            "task_id": "sustain_a",
            "quality": {"status": "ok"},
            "compliance": {"ok": True},
            "dimension_evidence": {
                "contact": {
                    "dimension_id": "contact",
                    "available": True,
                    "status": "FIRM_LEANING",
                    "estimate": 0.7,
                    "confidence_score": 0.74,
                    "confidence_label": "medium",
                    "resolution_eligible": True,
                    "quality_valid": True,
                    "reason": "multi_family_firm",
                    "confidence_source": "metric_family_aggregation",
                }
            },
            "actual_coverage": ["contact"],
        }
    ]
    fused = fuse_song_and_task_evidence(
        song_profile=song,
        task_results=tasks,
        unresolved_before=["contact"],
        selected_tasks=["sustain_a"],
    )
    assert "contact" in fused["resolved_dimensions"]
    assert fused["resolved_dimensions"]["contact"]["final_confidence"] == 0.74


def test_partial_dimension_validity():
    song = {"dimensions": {}}
    tasks = [
        {
            "task_id": "sustain_a",
            "quality": {"status": "ok"},
            "compliance": {"ok": True},
            "dimension_evidence": {
                "stability": {
                    "dimension_id": "stability",
                    "available": True,
                    "status": "STEADY",
                    "confidence_score": 0.72,
                    "resolution_eligible": True,
                    "quality_valid": True,
                    "reason": "multi_cue_steady",
                },
                "breathiness": {
                    "dimension_id": "breathiness",
                    "available": True,
                    "status": "LOW",
                    "confidence_score": 0.7,
                    "resolution_eligible": True,
                    "quality_valid": True,
                    "reason": "explicit_anti_breathy",
                },
                "contact": {
                    "dimension_id": "contact",
                    "available": False,
                    "resolution_eligible": False,
                    "quality_valid": True,
                    "reason": "h1h2_alone_or_no_families",
                },
            },
            "actual_coverage": ["stability", "breathiness"],
        }
    ]
    fused = fuse_song_and_task_evidence(
        song_profile=song,
        task_results=tasks,
        unresolved_before=["contact", "breathiness", "stability"],
        selected_tasks=["sustain_a"],
    )
    assert "stability" in fused["resolved_dimensions"]
    assert "breathiness" in fused["resolved_dimensions"]
    assert "contact" in fused["remaining_uncertainties"]


def test_flat_swell_cannot_resolve_effort():
    # Constant amplitude "swell"
    y, sr = _tone(dur=5.0, amp=0.2)
    res = analyze_task_audio(y, sr, task_id="dynamic_swell")
    assert res["compliance"]["ok"] is False
    assert res["dimension_evidence"]["effort"]["resolution_eligible"] is False


def test_controlled_swell_can_measure_low_effort():
    y, sr = _swell()
    res = analyze_task_audio(y, sr, task_id="dynamic_swell")
    assert res["compliance"]["ok"] is True
    ev = res["dimension_evidence"]["effort"]
    assert ev["available"] is True
    # Controlled loud may be LOW and still resolution_eligible
    if ev.get("status") == "LOW":
        assert ev["resolution_eligible"] is True


def test_fake_siren_single_pitch_unresolved():
    y, sr = _tone(dur=5.0, freq=220.0)
    res = analyze_task_audio(y, sr, task_id="siren")
    assert res["compliance"]["ok"] is False
    assert res["dimension_evidence"]["register"]["resolution_eligible"] is False


def test_real_siren_register_eligible():
    y, sr = _siren()
    res = analyze_task_audio(y, sr, task_id="siren")
    assert res["compliance"]["ok"] is True
    stats = res.get("siren_continuity_stats") or {}
    assert "voiced_dropout_ratio" in stats
    assert res["dimension_evidence"]["register"]["available"] is True


def test_strong_conflict_context_dependent():
    song = {
        "dimensions": {
            "glottal_contact_profile": {
                "status": "LIGHT_LEANING",
                "confidence_label": "high",
                "confidence_score": 0.82,
            }
        }
    }
    tasks = [
        {
            "task_id": "sustain_a",
            "quality": {"status": "ok"},
            "compliance": {"ok": True},
            "dimension_evidence": {
                "contact": {
                    "dimension_id": "contact",
                    "available": True,
                    "status": "FIRM_LEANING",
                    "confidence_score": 0.8,
                    "resolution_eligible": True,
                    "quality_valid": True,
                    "reason": "multi_family_firm",
                }
            },
            "actual_coverage": ["contact"],
        }
    ]
    fused = fuse_song_and_task_evidence(
        song_profile=song,
        task_results=tasks,
        unresolved_before=["contact"],
        selected_tasks=["sustain_a"],
    )
    assert "contact" in fused["context_resolved_dimensions"]
    assert fused["context_resolved_dimensions"]["contact"]["final_status"] == "CONTEXT_DEPENDENT"
    assert fused["song_profile"]["contact"]["status"] == "LIGHT_LEANING"
    assert fused["resolved_dimensions"].get("contact") is None


def test_task_existence_alone_no_confidence_boost():
    song = {
        "dimensions": {
            "glottal_contact_profile": {
                "status": "light",
                "confidence_label": "low",
                "confidence_score": 0.35,
            }
        }
    }
    tasks = [
        {
            "task_id": "sustain_a",
            "quality": {"status": "ok"},
            "compliance": {"ok": True},
            "dimension_evidence": {},
            "actual_coverage": [],
        }
    ]
    fused = fuse_song_and_task_evidence(
        song_profile=song,
        task_results=tasks,
        unresolved_before=["contact"],
        selected_tasks=["sustain_a"],
    )
    assert fused["remaining_uncertainties"] == ["contact"]
    row = fused.get("resolved_dimensions", {}).get("contact") or {}
    # remainders live in remaining list; confidence must stay song-level
    remain_row = None
    # reconstruct from internal path: uncertainty_remains stores in resolved dict with resolved=False
    # fuse keeps them only in remaining_uncertainties list — check no boost via confidence_delta
    assert not any(
        d.get("dimension") == "contact" and (d.get("final_confidence") or 0) > 0.35
        for d in fused.get("confidence_delta") or []
    )


def test_invalid_task_no_boost():
    song = {
        "dimensions": {
            "glottal_contact_profile": {"status": "light", "confidence_label": "low", "confidence_score": 0.3}
        }
    }
    tasks = [
        {
            "task_id": "sustain_a",
            "quality": {"status": "fail"},
            "invalid": True,
            "dimension_evidence": {
                "contact": {
                    "dimension_id": "contact",
                    "available": True,
                    "status": "FIRM_LEANING",
                    "confidence_score": 0.9,
                    "resolution_eligible": True,
                    "quality_valid": False,
                }
            },
            "actual_coverage": ["contact"],
        }
    ]
    fused = fuse_song_and_task_evidence(
        song_profile=song,
        task_results=tasks,
        unresolved_before=["contact"],
        selected_tasks=["sustain_a"],
    )
    assert "contact" in fused["remaining_uncertainties"]
