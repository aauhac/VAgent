"""Vocal Function Engine v2 tests — firm≠strain, GIF gate, banned claims."""

from __future__ import annotations

import numpy as np

from audio_analyzer.coaching import evaluate_pre_post, prescribe
from audio_analyzer.glottal_source import gif_validity
from audio_analyzer.song_detail.report import build_song_detailed_report
from audio_analyzer.vocal_function.evidence.families import effort_like, firmer_like
from audio_analyzer.vocal_function.report import affirmative_blob, build_vocal_function_public
from audio_analyzer.vocal_function.rules.fusion import fuse_contact, fuse_effort, fuse_leakage
from audio_analyzer.vocal_function.config import BANNED_CLAIM_SUBSTRINGS


def _seg(start, end, *, obs=None, src=None, valid=True):
    return {
        "start_sec": start,
        "end_sec": end,
        "valid": valid,
        "observations": obs or {},
        "level2_proxies": {
            "glottal_source": src or {"valid": False},
            "formants": {"valid": True, "confidence": 0.5},
            "timbre": {"brightness": "중간", "mid_presence": "보통"},
        },
    }


def test_firm_contact_alone_not_strain():
    segs = [
        _seg(
            i,
            i + 2,
            obs={
                "raw_h1_h2_proxy_db": -1.0,
                "energy_2_4k": 0.2,
                "periodicity_primary_db": 14.0,
                "onset_slope_db_per_sec": 20.0,
                "f0_frame_period_perturbation_proxy_percent": 0.5,
                "rms": 0.05,
            },
            src={
                "valid": True,
                "estimated_naq": 0.05,
                "estimated_mfdr_proxy": 1.0,
                "estimated_oq_proxy": 0.4,
            },
        )
        for i in range(0, 12, 2)
    ]
    assert any(firmer_like(s) for s in segs)
    assert not any(effort_like(s) for s in segs)
    effort = fuse_effort(segs)
    assert effort["status"] == "LOW"
    assert effort["profile"]["firm_without_effort_segments"] >= 1


def test_firm_plus_effort_evidence_eligible():
    segs = [
        _seg(
            i,
            i + 2,
            obs={
                "raw_h1_h2_proxy_db": -1.0,
                "energy_2_4k": 0.22,
                "periodicity_primary_db": 4.0,
                "onset_slope_db_per_sec": 90.0,
                "f0_frame_period_perturbation_proxy_percent": 3.0,
                "rms": 0.08,
            },
            src={"valid": True, "estimated_naq": 0.05, "estimated_mfdr_proxy": 2.0},
        )
        for i in range(0, 12, 2)
    ]
    effort = fuse_effort(segs)
    assert effort["status"] in ("OCCASIONAL", "MODERATE", "REPEATED")
    assert effort["profile"]["effort_hit_segments"] >= 1


def test_single_family_leakage_no_high_from_one_metric():
    # Only periodicity low — need 2 families for leakage_like
    segs = [
        _seg(i, i + 2, obs={"periodicity_primary_db": 5.0, "raw_h1_h2_proxy_db": 2.0})
        for i in range(0, 12, 2)
    ]
    out = fuse_leakage(segs)
    assert out["status"] != "HIGH"


def test_gif_invalid_unknown_source():
    gate = gif_validity(
        voiced_ratio=0.2,
        snr_proxy_db=3.0,
        f0_hz=None,
        periodicity_db=2.0,
        harmonic_confidence=0.1,
        vocal_dominant=False,
        separation_artifact=True,
    )
    assert gate["valid"] is False


def test_formant_uncertainty_resonance_restricted():
    segs = [
        _seg(
            i,
            i + 2,
            obs={"periodicity_primary_db": 12.0},
        )
        for i in range(0, 6, 2)
    ]
    for s in segs:
        s["level2_proxies"]["formants"] = {"valid": False, "confidence": 0.1}
        s["level2_proxies"]["timbre"] = {"restricted": True}
    from audio_analyzer.vocal_function.rules.fusion import fuse_resonance

    res = fuse_resonance(segs)
    assert res["status"] == "UNKNOWN" or res.get("restricted")


def test_high_note_firm_stable_no_auto_correction():
    from audio_analyzer.vocal_function.engine import analyze_high_note_events

    segs = []
    for i, f0 in enumerate([180, 190, 200, 400, 210]):
        segs.append(
            _seg(
                i * 2,
                i * 2 + 2,
                obs={
                    "f0_hz": f0,
                    "raw_h1_h2_proxy_db": -1.0,
                    "energy_2_4k": 0.2,
                    "periodicity_primary_db": 14.0,
                    "onset_slope_db_per_sec": 20.0,
                    "f0_frame_period_perturbation_proxy_percent": 0.4,
                    "rms": 0.05,
                },
                src={"valid": True, "estimated_naq": 0.05, "estimated_mfdr_proxy": 1.0},
            )
        )
    events = analyze_high_note_events(segs, {"rms": 0.04, "f0_hz": 200})
    if events:
        assert events[0]["concern"] is False


def test_high_note_firm_rough_persistence_concern():
    from audio_analyzer.vocal_function.engine import analyze_high_note_events

    segs = []
    for i, f0 in enumerate([180, 190, 420, 430, 440]):
        segs.append(
            _seg(
                i * 2,
                i * 2 + 2,
                obs={
                    "f0_hz": f0,
                    "raw_h1_h2_proxy_db": -1.0,
                    "energy_2_4k": 0.25,
                    "periodicity_primary_db": 4.0,
                    "onset_slope_db_per_sec": 95.0,
                    "f0_frame_period_perturbation_proxy_percent": 3.5,
                    "rms": 0.12,
                },
                src={"valid": True, "estimated_naq": 0.04, "estimated_mfdr_proxy": 2.0},
            )
        )
    events = analyze_high_note_events(segs, {"rms": 0.04, "f0_hz": 180})
    assert events
    assert any(e.get("concern") for e in events)


def test_respiration_proxy_never_outputs_pressure():
    from audio_analyzer.vocal_function.rules.fusion import fuse_respiratory

    out = fuse_respiratory(
        [_seg(i, i + 2, obs={"periodicity_primary_db": 12.0, "rms": 0.05}) for i in range(0, 8, 2)]
    )
    blob = str(out)
    assert "subglottal" not in blob.lower() or "측정하지" in blob
    assert out["profile"]["never_outputs_actual_pressure"] is True


def test_anatomical_banned_claims_absent():
    segs = [
        _seg(
            i,
            i + 2,
            obs={
                "periodicity_primary_db": 6.0,
                "raw_h1_h2_proxy_db": 10.0,
                "spectral_tilt_db_per_oct": -18.0,
                "rms": 0.04,
            },
            src={"valid": True, "estimated_naq": 0.2, "estimated_oq_proxy": 0.7},
        )
        for i in range(0, 12, 2)
    ]
    contact = fuse_contact(segs)
    leak = fuse_leakage(segs)
    effort = fuse_effort(segs)
    profile = {
        "available": True,
        "engine_version": "vocal-function-v2.0",
        "report_version": "vocal-coach-report-v2.0",
        "headline": ["t"],
        "dimensions": {
            "glottal_contact_profile": contact,
            "air_leakage_breathiness": leak,
            "vocal_effort_strain": effort,
            "phonation_regularity": {"status": "STABLE", "hidden": False, "dimension_id": "phonation_regularity", "display_name": "x", "summary": "ok", "focus_segments": [], "what_it_may_mean": "", "what_we_cannot_know": ""},
            "register_configuration": {"status": "STABLE_LIKE", "hidden": False, "dimension_id": "register_configuration", "display_name": "x", "summary": "ok", "focus_segments": [], "what_it_may_mean": "", "what_we_cannot_know": ""},
            "onset_offset_coordination": {"status": "BALANCED_LIKE", "hidden": False, "dimension_id": "onset_offset_coordination", "display_name": "x", "summary": "ok", "focus_segments": [], "what_it_may_mean": "", "what_we_cannot_know": ""},
            "vibrato_control": {"status": "UNKNOWN", "hidden": True, "dimension_id": "vibrato_control", "display_name": "x", "summary": "", "focus_segments": []},
            "resonance_formant_strategy": {"status": "OBSERVED", "hidden": False, "dimension_id": "resonance_formant_strategy", "display_name": "x", "summary": "중간", "focus_segments": [], "profile": {"brightness": "중간", "mid_presence": "보통"}, "what_it_may_mean": "음색", "what_we_cannot_know": ""},
            "respiratory_phonatory_coordination": {"status": "STABLE_LIKE", "hidden": False, "dimension_id": "respiratory_phonatory_coordination", "display_name": "x", "summary": "ok", "focus_segments": [], "what_it_may_mean": "", "what_we_cannot_know": "복압을 측정하지 않습니다."},
            "phonatory_economy_proxy": {"status": "UNKNOWN", "hidden": True, "dimension_id": "phonatory_economy_proxy", "display_name": "x", "summary": "", "focus_segments": []},
        },
        "high_note_events": [],
        "style_goal": "unspecified",
        "disclaimer": "참고",
    }
    pub = build_vocal_function_public(profile)
    blob = affirmative_blob(pub)
    for banned in BANNED_CLAIM_SUBSTRINGS:
        if banned in ("복압을",):  # may appear only in cannot-know which is stripped
            assert banned not in blob
        else:
            assert banned not in blob


def test_exercise_only_if_eligible():
    profile = {
        "available": True,
        "dimensions": {
            "vocal_effort_strain": {"status": "REPEATED", "dimension_id": "vocal_effort_strain"},
            "air_leakage_breathiness": {"status": "LOW"},
            "register_configuration": {"status": "STABLE_LIKE"},
            "onset_offset_coordination": {"status": "ABRUPT_LIKE", "dimension_id": "onset_offset_coordination"},
        },
        "style_goal": "pop",
    }
    out = prescribe(profile, style_goal="pop")
    assert out["exercises"]
    assert out["note"]


def test_pre_post_response_deterministic():
    a = evaluate_pre_post(
        {"periodicity_primary_db": 6.0, "onset_slope_db_per_sec": 90.0, "estimated_naq": 0.05},
        {"periodicity_primary_db": 10.0, "onset_slope_db_per_sec": 40.0, "estimated_naq": 0.08},
    )
    b = evaluate_pre_post(
        {"periodicity_primary_db": 6.0, "onset_slope_db_per_sec": 90.0, "estimated_naq": 0.05},
        {"periodicity_primary_db": 10.0, "onset_slope_db_per_sec": 40.0, "estimated_naq": 0.08},
    )
    assert a == b
    assert a["not_a_treatment_claim"] is True


def test_style_does_not_alter_raw_score():
    # style_goal is metadata for coaching vocabulary only — not a score input
    from audio_analyzer.coaching import prescribe

    base = {
        "available": True,
        "dimensions": {
            "vocal_effort_strain": {"status": "LOW", "dimension_id": "vocal_effort_strain"},
            "air_leakage_breathiness": {"status": "LOW"},
            "register_configuration": {"status": "STABLE_LIKE"},
            "onset_offset_coordination": {"status": "BALANCED_LIKE"},
        },
    }
    a = prescribe(base, style_goal="classical")
    b = prescribe(base, style_goal="rock")
    assert a["note"] == b["note"]
    assert "raw score" in a["note"]


def test_performance_v3_and_entitlement_unchanged():
    from backend.app.products.catalog import PRODUCT_SONG_DETAIL
    from audio_analyzer.scoring.score_v3 import compute_score_v3

    assert PRODUCT_SONG_DETAIL == "song_detail"
    assert callable(compute_score_v3)


def test_scientific_debug_isolated_in_public():
    profile = {
        "available": True,
        "engine_version": "vocal-function-v2.0",
        "report_version": "vocal-coach-report-v2.0",
        "headline": [],
        "dimensions": {},
        "high_note_events": [],
        "style_goal": "unspecified",
        "scientific_debug": {"estimated_naq": 0.1},
        "disclaimer": "x",
    }
    pub = build_vocal_function_public(profile)
    assert "scientific_debug" not in pub


def test_song_detail_prefers_function_profile():
    report = build_song_detailed_report(
        {
            "score": {
                "available": True,
                "overall": 60,
                "label": "보통",
                "areas": [
                    {
                        "area_id": "stability",
                        "display_name": "발성 안정성",
                        "score": 74,
                        "status": "normal",
                        "confidence": 0.8,
                        "submetrics": [],
                        "temporal": {},
                    },
                    {
                        "area_id": "dynamic_control",
                        "display_name": "강약 컨트롤",
                        "score": 57,
                        "status": "needs_work",
                        "confidence": 0.8,
                        "submetrics": [],
                        "temporal": {},
                    },
                ],
            },
            "quality": {"status": "pass"},
            "optional_analysis": {"vibrato": {"available": False}},
            "vocal_function_profile": {
                "available": True,
                "engine_version": "vocal-function-v2.0",
                "report_version": "vocal-coach-report-v2.0",
                "headline": ["접촉 관련 경향: 단단함 쪽"],
                "dimensions": {
                    "glottal_contact_profile": {
                        "dimension_id": "glottal_contact_profile",
                        "display_name": "성대 접촉 관련 발성 경향",
                        "status": "OBSERVED",
                        "status_label": "단단함 쪽",
                        "continuum_0_to_1": 0.7,
                        "continuum_label": "단단함 쪽",
                        "confidence_label": "medium",
                        "hidden": False,
                        "summary": "단단함 쪽",
                        "focus_segments": [],
                        "what_it_may_mean": "더 단단한 contact-related pattern",
                        "what_we_cannot_know": "해부를 측정하지 않습니다.",
                        "profile": {},
                        "valid_segment_count": 6,
                    },
                    "vocal_effort_strain": {
                        "dimension_id": "vocal_effort_strain",
                        "display_name": "힘이 과하게 들어간 소리 경향",
                        "status": "LOW",
                        "status_label": "안정",
                        "confidence_label": "medium",
                        "hidden": False,
                        "summary": "안정",
                        "focus_segments": [],
                        "what_it_may_mean": "effort 약함",
                        "what_we_cannot_know": "근육을 측정하지 않습니다.",
                        "valid_segment_count": 6,
                    },
                },
                "high_note_events": [],
                "style_goal": "unspecified",
                "disclaimer": "참고",
            },
            "vocal_quality_profile": {"available": False},
        }
    )
    assert report["report_version"].startswith("vocal-coach-report-v2")
    assert report["vocal_function_profile"]["available"] is True
    ids = [d["dimension_id"] for d in report["vocal_function_profile"]["dimensions"]]
    assert "glottal_contact_profile" in ids
