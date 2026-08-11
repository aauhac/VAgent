"""Criteria matrix + scope + core span + primary eligibility tests."""

from __future__ import annotations

from audio_analyzer.coaching.bottleneck.ranker import select_primary
from audio_analyzer.song_detail.report import build_song_detailed_report
from audio_analyzer.vocal_function.criteria_matrix import (
    build_criteria_matrix,
    build_dimension_row,
)
from audio_analyzer.vocal_function.criteria_registry import DIMENSION_ORDER
from audio_analyzer.vocal_function.episodes.builder import finalize_episode
from audio_analyzer.vocal_function.rules.fusion import fuse_leakage
from audio_analyzer.vocal_function.validity import build_validity_by_dimension


def _seg(start, end, *, obs=None, src=None, valid=True, rms=0.05):
    observations = dict(obs or {})
    if "rms" not in observations:
        observations["rms"] = rms
    seg = {
        "start_sec": start,
        "end_sec": end,
        "valid": valid,
        "voiced_ratio": 0.7,
        "observations": observations,
        "vocal_evidence": {
            "vocal_specific": True,
            "vocal_dominance": 0.8,
            "vocal_confidence": 0.7,
        },
        "level2_proxies": {
            "glottal_source": src if src is not None else {"valid": False},
            "gif_gate": {"valid": bool((src or {}).get("valid"))},
        },
        "rms": rms,
    }
    seg["validity_by_dimension"] = build_validity_by_dimension(seg)
    return seg


def _dims_stub(**overrides):
    base = {
        did: {
            "dimension_id": did,
            "display_name": did,
            "status": "UNKNOWN",
            "hidden": True,
            "confidence_label": "low",
            "valid_segment_count": 0,
        }
        for did in DIMENSION_ORDER
    }
    base.update(overrides)
    return base


def test_all_functional_dimensions_in_matrix():
    matrix = build_criteria_matrix(dimensions=_dims_stub(), segments=[], episodes=[])
    ids = [r["dimension_id"] for r in matrix]
    assert ids == list(DIMENSION_ORDER)
    assert len(matrix) == 10


def test_low_confidence_still_in_matrix():
    dims = _dims_stub(
        air_leakage_breathiness={
            "dimension_id": "air_leakage_breathiness",
            "display_name": "기식",
            "status": "UNKNOWN",
            "hidden": True,
            "confidence_label": "low",
            "breathiness_coverage": {
                "n_total_segments": 10,
                "n_evaluable_segments": 2,
                "n_positive_segments": 0,
                "n_negative_segments": 0,
                "n_insufficient_segments": 8,
            },
        }
    )
    segs = [
        _seg(i, i + 2, obs={"periodicity_primary_db": 5.0, "raw_h1_h2_proxy_db": 2.0})
        for i in range(0, 4, 2)
    ]
    matrix = build_criteria_matrix(dimensions=dims, segments=segs, episodes=[])
    row = next(r for r in matrix if r["dimension_id"] == "air_leakage_breathiness")
    assert row["hidden_from_main_cards"] is True
    assert row["finding"] == "UNDETERMINED"


def test_insufficient_evidence_finding_undetermined():
    segs = [
        _seg(i, i + 2, obs={"periodicity_primary_db": 5.0, "raw_h1_h2_proxy_db": 2.0})
        for i in range(0, 4, 2)
    ]
    leak = fuse_leakage(segs)
    dims = _dims_stub(air_leakage_breathiness=leak)
    row = build_dimension_row(
        "air_leakage_breathiness", leak, segments=segs, episodes=[]
    )
    assert row["finding"] == "UNDETERMINED"
    assert row["measurement_sufficiency"] in ("INSUFFICIENT", "PARTIAL")


def test_zero_positive_alone_not_low_finding_when_insufficient():
    segs = [
        _seg(i, i + 2, obs={"periodicity_primary_db": 5.0, "raw_h1_h2_proxy_db": 2.0})
        for i in range(0, 12, 2)
    ]
    leak = fuse_leakage(segs)
    assert leak["status"] != "LOW"
    row = build_dimension_row(
        "air_leakage_breathiness", leak, segments=segs, episodes=[]
    )
    if row["measurement_sufficiency"] != "SUFFICIENT":
        assert row["finding"] == "UNDETERMINED"


def test_sufficient_negative_coverage_not_prominent():
    segs = [
        _seg(
            i,
            i + 2,
            obs={
                "periodicity_primary_db": 14.0,
                "raw_h1_h2_proxy_db": 1.0,
                "spectral_tilt_db_per_oct": -8.0,
            },
        )
        for i in range(0, 14, 2)
    ]
    leak = fuse_leakage(segs)
    assert leak["status"] == "LOW"
    row = build_dimension_row(
        "air_leakage_breathiness", leak, segments=segs, episodes=[]
    )
    if row["measurement_sufficiency"] == "SUFFICIENT":
        assert row["finding"] == "NOT_PROMINENT"


def test_primary_includes_satisfied_criteria_fields():
    from audio_analyzer.vocal_function.criteria_matrix import attach_primary_criteria_explanation

    matrix = build_criteria_matrix(
        dimensions=_dims_stub(
            register_configuration={
                "dimension_id": "register_configuration",
                "display_name": "register",
                "status": "TRANSITION_EVENTS",
                "hidden": False,
                "confidence_label": "medium",
                "profile": {
                    "events": [
                        {
                            "start_sec": 10,
                            "end_sec": 12,
                            "f0_jump_cents": 400,
                            "validity": {"vocal_specific": True},
                            "evidence": {"source_change": True, "naq_change": True},
                        }
                    ],
                    "rejected_events": [],
                },
            }
        ),
        segments=[],
        episodes=[
            {
                "type": "REGISTER_TRANSITION",
                "start_sec": 6,
                "end_sec": 16,
                "core_evidence_span": {"start_sec": 10.7, "end_sec": 12.2, "duration_sec": 1.5},
            }
        ],
    )
    primary = {
        "id": "REGISTER_TRANSITION_DISRUPTION",
        "user_title": "음역 전환",
        "confidence_label": "medium",
    }
    out = attach_primary_criteria_explanation(primary, matrix)
    assert out["satisfied_criteria"]
    assert "criteria_user_summary" in out


def test_primary_blocked_when_criteria_insufficient():
    matrix = build_criteria_matrix(dimensions=_dims_stub(), segments=[], episodes=[])
    hyps = [
        {
            "id": "REGISTER_TRANSITION_DISRUPTION",
            "confidence_label": "medium",
            "supporting_episode_ids": ["e1"],
            "supporting_evidence": ["x"],
            "impact": "HIGH",
        }
    ]
    primary, _, _ = select_primary(hyps, criteria_matrix=matrix)
    assert primary is None  # not eligible merely as sole candidate


def test_global_vs_target_scope_in_why():
    from audio_analyzer.coaching.bottleneck import _structured_why

    primary = {"why": "전환", "alternative_explanations": []}
    target = {
        "feature_matrix": {
            "regularity": {"periodicity": 10, "roughness": False},
            "effort": {},
            "recovery": {},
        }
    }
    profile = {
        "dimensions": {
            "phonation_regularity": {"status": "REPEATED_IRREGULAR"},
        }
    }
    why = _structured_why(primary, target, [], profile=profile)
    assert why.get("scope_note")
    assert any(
        (p.get("scope") == "TARGET_EPISODE" and "해당 전환 구간" in p.get("text", ""))
        for p in why["preserved"]
    )


def test_core_span_le_parent_episode():
    ep = finalize_episode(
        {
            "type": "REGISTER_TRANSITION",
            "start_sec": 6.0,
            "end_sec": 16.5,
            "members": [
                {"start_sec": 6.0, "end_sec": 9.0, "f0_jump_cents": 100},
                {"start_sec": 10.7, "end_sec": 12.2, "f0_jump_cents": 480},
                {"start_sec": 14.0, "end_sec": 16.5, "f0_jump_cents": 120},
            ],
        },
        all_segments=[],
    )
    core = ep["core_evidence_span"]
    assert core["start_sec"] >= ep["start_sec"]
    assert core["end_sec"] <= ep["end_sec"]
    assert core["duration_sec"] <= (ep["end_sec"] - ep["start_sec"]) + 1e-6
    assert abs(core["start_sec"] - 10.7) < 0.01


def test_song_detail_exposes_criteria_matrix():
    report = build_song_detailed_report(
        {
            "score": {"available": False, "areas": []},
            "quality": {"status": "pass"},
            "optional_analysis": {},
            "vocal_function_profile": {
                "available": True,
                "engine_version": "vocal-function-v2.3",
                "report_version": "vocal-coach-report-v2.3",
                "headline": [],
                "dimensions": {},
                "criteria_matrix": [
                    {
                        "dimension_id": did,
                        "display_name": did,
                        "measurement_sufficiency": "INSUFFICIENT",
                        "finding": "UNDETERMINED",
                        "coaching_eligibility": "NEEDS_CONFIRMATION",
                        "criteria": [],
                        "summary": "x",
                        "measurement_sufficiency_label": "부족",
                        "finding_label": "판단 보류",
                        "coaching_eligibility_label": "추가 확인 필요",
                    }
                    for did in DIMENSION_ORDER
                ],
                "criteria_matrix_note": "note",
                "coaching_decision": {
                    "primary_bottleneck": None,
                    "secondary_bottlenecks": [],
                    "no_primary_message": "없음",
                    "exercise_plan": [],
                    "modify": [],
                    "preserve": [],
                },
                "focus_segments": [],
                "training_plan": [],
                "high_note_events": [],
                "disclaimer": "x",
            },
            "vocal_quality_profile": {"available": False},
        },
        analysis_id="crit",
    )
    assert len(report["criteria_matrix"]) == 10
    assert report["show_problem_focus"] is False


def test_insufficient_row_lists_missing_criteria():
    segs = [
        _seg(0, 2, obs={"periodicity_primary_db": 5.0}, src={"valid": False}),
        _seg(2, 4, obs={"periodicity_primary_db": 5.0}, src={"valid": False}),
    ]
    leak = fuse_leakage(segs)
    row = build_dimension_row(
        "air_leakage_breathiness", leak, segments=segs, episodes=[]
    )
    missing = [
        c
        for c in row["criteria"]
        if c["required"] and c["availability"] in ("INSUFFICIENT", "NOT_AVAILABLE")
    ]
    assert missing  # user can see which criteria failed
