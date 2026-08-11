"""Vocal Type Engine v1.1 — evidence mass, gates, consistency."""

from __future__ import annotations

from audio_analyzer.audit.consistency import (
    core_span_label,
    validate_report_consistency,
)
from audio_analyzer.coach_profile.bridge import compute_bridge, register_split_global_eligibility
from audio_analyzer.coach_profile.head_chest import (
    score_segment_head_chest,
    weighted_index,
)
from audio_analyzer.coach_profile.naming import classify_base_type
from audio_analyzer.coaching.bottleneck.preserve import build_preserve_modify
from audio_analyzer.song_detail.explain_v3 import explain_area


def _row(*, idx, mass, directionality=0.5, conf="medium", n_fam=3, n_src=2):
    return {
        "head_chest_index": idx,
        "evidence_mass": mass,
        "directionality": directionality,
        "confidence": conf,
        "n_families": n_fam,
        "n_source_families": n_src,
        "evidence_families": ["SOURCE_FLOW", "HARMONIC_SOURCE"][:n_src],
        "start_sec": 0,
        "end_sec": 1,
    }


def test_weak_equal_mass_not_5050():
    # C≈H≈0.05 → filtered by MIN_EVIDENCE_MASS
    rows = [_row(idx=0.5, mass=0.10) for _ in range(5)]
    assert weighted_index(rows) is None


def test_strong_equal_mass_can_be_5050():
    rows = [_row(idx=0.5, mass=1.6, directionality=0.05) for _ in range(6)]
    idx = weighted_index(rows)
    assert idx is not None
    assert abs(idx - 0.5) < 0.02


def test_chest_dominant_mass():
    rows = [_row(idx=0.25, mass=1.5, directionality=0.6) for _ in range(5)]
    assert weighted_index(rows) < 0.4


def test_head_dominant_mass():
    rows = [_row(idx=0.78, mass=1.5, directionality=0.6) for _ in range(5)]
    assert weighted_index(rows) > 0.6


def test_unknown_family_does_not_vote_neutral():
    s = {
        "start_sec": 0,
        "end_sec": 2,
        "valid": True,
        "rms": 0.05,
        "observations": {"f0_hz": 220, "rms": 0.05},
        "level2_proxies": {"glottal_source": {"valid": False}},
        "vocal_evidence": {"vocal_specific": True},
    }
    row = score_segment_head_chest(s, all_segments=[s], global_baseline={})
    assert row.get("head_chest_index") is None
    assert row.get("status") in ("UNAVAILABLE", "INSUFFICIENT")


def test_invalid_segment_excluded():
    s = {
        "start_sec": 0,
        "end_sec": 1,
        "rms": 0.0,
        "observations": {"rms": 0.0},
        "level2_proxies": {"glottal_source": {"valid": False}},
        "vocal_evidence": {},
    }
    row = score_segment_head_chest(s, all_segments=[s])
    assert row["head_chest_index"] is None
    assert row["status"] == "UNAVAILABLE"


def test_missing_range_not_5050_via_weighted():
    # fewer than MIN_SEGMENTS → None
    rows = [_row(idx=0.5, mass=2.0) for _ in range(2)]
    assert weighted_index(rows) is None


def test_all_source_missing_unresolved_type():
    t = classify_base_type(
        index=None,
        bridge={"type": "UNDETERMINED", "score": None},
        modifiers=[],
        confidence="low",
    )
    assert t == "UNRESOLVED"


def test_high_f0_alone_not_head_segment():
    s = {
        "start_sec": 0,
        "end_sec": 2,
        "valid": True,
        "rms": 0.05,
        "observations": {"f0_hz": 480, "rms": 0.05},
        "level2_proxies": {"glottal_source": {"valid": False}},
        "vocal_evidence": {"vocal_specific": True},
    }
    row = score_segment_head_chest(s, all_segments=[s], global_baseline={})
    assert row.get("head_chest_index") is None


def test_contact_alone_not_head_or_chest():
    s = {
        "start_sec": 0,
        "end_sec": 2,
        "valid": True,
        "rms": 0.05,
        "contact_hint": "lighter_like",
        "observations": {"f0_hz": 220, "rms": 0.05},
        "level2_proxies": {"glottal_source": {"valid": False}},
        "vocal_evidence": {"vocal_specific": True},
    }
    row = score_segment_head_chest(s, all_segments=[s], global_baseline={})
    assert row.get("head_chest_index") is None
    contact = (row.get("family_contribution") or {}).get("CONTACT") or {}
    assert contact.get("applied") is False


def test_firm_contact_alone_not_chest():
    s = {
        "start_sec": 0,
        "end_sec": 2,
        "valid": True,
        "rms": 0.05,
        "contact_hint": "firmer_like",
        "observations": {"f0_hz": 220, "rms": 0.05},
        "level2_proxies": {"glottal_source": {"valid": False}},
        "vocal_evidence": {"vocal_specific": True},
    }
    row = score_segment_head_chest(s, all_segments=[s], global_baseline={})
    assert row.get("head_chest_index") is None


def test_breathiness_alone_not_head():
    s = {
        "start_sec": 0,
        "end_sec": 2,
        "valid": True,
        "rms": 0.05,
        "observations": {
            "f0_hz": 300,
            "rms": 0.05,
            "periodicity_primary_db": 4.0,
            "raw_h1_h2_proxy_db": 14.0,
        },
        "level2_proxies": {"glottal_source": {"valid": False}},
        "vocal_evidence": {"vocal_specific": True},
    }
    row = score_segment_head_chest(s, all_segments=[s], global_baseline={})
    # H1-H2 suppressed under breathiness contamination
    harm = (row.get("family_contribution") or {}).get("HARMONIC_SOURCE") or {}
    assert harm.get("status") == "UNAVAILABLE" or row.get("head_chest_index") is None


def test_register_insufficient_forbids_split():
    gate = register_split_global_eligibility(
        bridge_score=0.2,
        register_dim={"confidence_label": "low", "status": "UNKNOWN"},
        criteria_matrix=[
            {
                "dimension_id": "register_configuration",
                "measurement_sufficiency": "INSUFFICIENT",
            }
        ],
        transition_events=[{}, {}],
        concern_episodes=[],
        opportunities=[{}, {}, {}],
        local_events=[{"type": "LOCAL_ABRUPT_BREAK"}, {"type": "LOCAL_ABRUPT_BREAK"}],
        components={"f0_continuity": 0.2, "index_continuity": 0.2},
        vocal_specific_ok=True,
        roughness_dominant=False,
        breathiness_dominant=False,
    )
    assert gate["eligible"] is False
    t = classify_base_type(
        index=0.5,
        bridge={"type": "ABRUPT_REGISTER_BREAK", "score": 0.2, "split_eligibility": gate},
        modifiers=[],
        confidence="medium",
        register_split_ok=False,
    )
    assert t != "REGISTER_SPLIT_GLOBAL"


def test_smooth_trajectory_forbids_split():
    gate = register_split_global_eligibility(
        bridge_score=0.8,
        register_dim={"confidence_label": "high", "status": "STABLE_LIKE"},
        criteria_matrix=[
            {"dimension_id": "register_configuration", "measurement_sufficiency": "SUFFICIENT"}
        ],
        transition_events=[],
        concern_episodes=[],
        opportunities=[{}, {}, {}],
        local_events=[],
        components={"f0_continuity": 0.9, "index_continuity": 0.9},
        vocal_specific_ok=True,
        roughness_dominant=False,
        breathiness_dominant=False,
    )
    assert gate["eligible"] is False


def test_isolated_break_not_automatic_global_split():
    gate = register_split_global_eligibility(
        bridge_score=0.2,
        register_dim={"confidence_label": "high"},
        criteria_matrix=[
            {"dimension_id": "register_configuration", "measurement_sufficiency": "SUFFICIENT"}
        ],
        transition_events=[{}],
        concern_episodes=[],
        opportunities=[{}, {}, {}, {}],
        local_events=[{"type": "LOCAL_ABRUPT_BREAK"}],
        components={"f0_continuity": 0.2, "index_continuity": 0.2},
        vocal_specific_ok=True,
        roughness_dominant=False,
        breathiness_dominant=False,
    )
    assert gate["isolated_event_only"] is True
    assert gate["eligible"] is False


def test_repeated_breaks_eligible():
    gate = register_split_global_eligibility(
        bridge_score=0.2,
        register_dim={"confidence_label": "high"},
        criteria_matrix=[
            {"dimension_id": "register_configuration", "measurement_sufficiency": "SUFFICIENT"}
        ],
        transition_events=[{}, {}],
        concern_episodes=[],
        opportunities=[{}, {}, {}, {}, {}],
        local_events=[
            {"type": "LOCAL_ABRUPT_BREAK"},
            {"type": "LOCAL_ABRUPT_BREAK"},
        ],
        components={"f0_continuity": 0.2, "index_continuity": 0.2},
        vocal_specific_ok=True,
        roughness_dominant=False,
        breathiness_dominant=False,
    )
    assert gate["eligible"] is True


def test_air_leakage_primary_modify_first():
    preserve, modify = build_preserve_modify(
        {
            "dimensions": {
                "vibrato_control": {"status": "UNKNOWN"},
                "glottal_contact_profile": {},
                "vocal_effort_strain": {"status": "LOW"},
                "phonation_regularity": {"status": "STABLE"},
            },
            "criteria_matrix": [
                {"dimension_id": "vibrato_control", "measurement_sufficiency": "INSUFFICIENT"}
            ],
        },
        [],
        {"id": "AIR_LEAKAGE"},
        target_episode={
            "episode_id": "e1",
            "feature_matrix": {
                "effort": {"strain_like": 0.7},
                "source": {"contact_firmness": 0.2},
                "regularity": {},
            },
        },
    )
    assert modify[0]["id"] == "air_leakage"
    assert modify[0]["triggered_by"] == "AIR_LEAKAGE"


def test_vibrato_insufficient_no_preserve():
    preserve, _ = build_preserve_modify(
        {
            "dimensions": {
                "vibrato_control": {"status": "OBSERVED", "confidence_label": "low"},
                "glottal_contact_profile": {},
                "vocal_effort_strain": {"status": "LOW"},
                "phonation_regularity": {},
            },
            "criteria_matrix": [
                {"dimension_id": "vibrato_control", "measurement_sufficiency": "INSUFFICIENT"}
            ],
        },
        [],
        None,
        None,
    )
    assert not any(p["id"] == "vibrato" for p in preserve)


def test_consistency_register_split_vs_insufficient():
    result = validate_report_consistency(
        vocal_type={
            "type_id": "REGISTER_SPLIT_GLOBAL",
            "bridge": {"type": "ABRUPT_REGISTER_BREAK"},
        },
        criteria_matrix=[
            {"dimension_id": "register_configuration", "measurement_sufficiency": "INSUFFICIENT"}
        ],
    )
    assert result["ok"] is False
    assert any(i["id"] == "type_vs_register_insufficient" for i in result["issues"])


def test_consistency_no_passaggio_stable_when_insufficient():
    result = validate_report_consistency(
        vocal_type={
            "type_id": "BALANCED_MIX",
            "bridge": {"type": "SMOOTH_BRIDGE"},
            "key_traits": [{"key": "passaggio", "label": "파사지오", "value": "비교적 안정"}],
        },
        criteria_matrix=[
            {"dimension_id": "register_configuration", "measurement_sufficiency": "INSUFFICIENT"}
        ],
    )
    assert any(i["id"] == "smooth_bridge_vs_register_insufficient" for i in result["issues"])


def test_episode_heading_matches_family():
    assert core_span_label({"id": "AIR_LEAKAGE"}, {"type": "AIR_LEAKAGE"}) == "핵심 기식 구간"
    assert (
        core_span_label({"id": "REGISTER_TRANSITION_DISRUPTION"}, {"type": "REGISTER_TRANSITION"})
        == "핵심 전환 구간"
    )


def test_high_score_not_mid_wording():
    area = {
        "area_id": "projection",
        "display_name": "목소리 전달력",
        "score": 80,
        "status": "ok",
        "submetrics": [
            {"submetric_id": "spectral_projection", "score": 82, "confidence": 0.8},
            {"submetric_id": "presence_prominence", "score": 78, "confidence": 0.8},
        ],
    }
    explained = explain_area(area)
    text = (explained.get("headline") or "") + (explained.get("interpretation") or "")
    assert "중간 수준" not in text


def test_anchor_runner_order_is_inference_then_manifest():
    """Architecture guard: audit script must freeze inference before reading human notes."""
    from pathlib import Path

    src = Path("scripts/vocal_type_anchor_audit.py").read_text(encoding="utf-8")
    # Markers placed in executable flow (not module docstring)
    i_inf = src.index("--- FREEZE inference result before any human annotation ---")
    i_man = src.index("Human notes are read ONLY after freeze")
    assert i_inf < i_man


def test_bridge_insufficient_undetermined():
    bridge = compute_bridge(
        segments=[],
        hc_rows=[],
        register_dim={"confidence_label": "low", "status": "UNKNOWN", "profile": {}},
        criteria_matrix=[
            {"dimension_id": "register_configuration", "measurement_sufficiency": "INSUFFICIENT"}
        ],
    )
    assert bridge["type"] in ("UNDETERMINED",)
    assert bridge.get("available") is False or bridge["type"] == "UNDETERMINED"


def test_neutral_collapse_blocks_balanced_mix():
    t = classify_base_type(
        index=0.5,
        bridge={"type": "SMOOTH_BRIDGE", "score": 0.8},
        modifiers=[],
        confidence="medium",
        neutral_collapse=True,
    )
    assert t == "UNRESOLVED"
