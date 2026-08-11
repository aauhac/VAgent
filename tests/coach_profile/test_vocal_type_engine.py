"""Vocal Type / Head–Chest Balance Engine tests."""

from __future__ import annotations

from audio_analyzer.coach_profile.bridge import compute_bridge
from audio_analyzer.coach_profile.engine import compute_vocal_type_profile
from audio_analyzer.coach_profile.head_chest import (
    index_to_ratios,
    score_segment_head_chest,
    weighted_index,
)
from audio_analyzer.coach_profile.naming import (
    classify_base_type,
    compose_display_name,
)
from audio_analyzer.song_detail.report import build_song_detailed_report


def _seg(
    start,
    end,
    *,
    f0=220.0,
    naq=0.10,
    oq=0.5,
    h1h2=4.0,
    tilt=-12.0,
    e24=0.12,
    mfdr=1.0,
    rms=0.05,
    gif=True,
):
    return {
        "start_sec": start,
        "end_sec": end,
        "valid": True,
        "voiced_ratio": 0.8,
        "rms": rms,
        "vocal_evidence": {"vocal_specific": True, "vocal_dominance": 0.8, "vocal_confidence": 0.7},
        "observations": {
            "f0_hz": f0,
            "raw_h1_h2_proxy_db": h1h2,
            "spectral_tilt_db_per_oct": tilt,
            "energy_2_4k": e24,
            "periodicity_primary_db": 12.0,
            "rms": rms,
        },
        "level2_proxies": {
            "glottal_source": {
                "valid": gif,
                "estimated_naq": naq,
                "estimated_oq_proxy": oq,
                "estimated_mfdr_norm_proxy": mfdr,
            }
            if gif
            else {"valid": False},
        },
    }


def test_ratios_sum_100():
    r = index_to_ratios(0.36)
    assert r["available"]
    assert r["chest_ratio"] + r["head_ratio"] == 100


def test_index_0_is_chest_100():
    r = index_to_ratios(0.0)
    assert r["chest_ratio"] == 100 and r["head_ratio"] == 100 - 100


def test_index_1_is_head_100():
    r = index_to_ratios(1.0)
    assert r["head_ratio"] == 100 and r["chest_ratio"] == 0


def test_unknown_no_fake_ratio():
    r = index_to_ratios(None)
    assert r["available"] is False
    assert r["chest_ratio"] is None


def test_high_f0_alone_not_head():
    # High F0 but chest-direction source evidence
    segs = [
        _seg(i, i + 2, f0=420, naq=0.05, oq=0.35, h1h2=0.5, tilt=-8, e24=0.22, mfdr=1.4)
        for i in range(0, 12, 2)
    ]
    rows = [score_segment_head_chest(s, all_segments=segs, global_baseline={"naq": 0.12, "oq": 0.5, "h1_h2": 5, "mfdr_norm": 1.0, "rms": 0.04}) for s in segs]
    idx = weighted_index(rows)
    assert idx is not None
    assert idx < 0.5  # still chest-leaning despite high F0


def test_low_f0_alone_not_chest():
    segs = [
        _seg(i, i + 2, f0=160, naq=0.20, oq=0.65, h1h2=12.0, tilt=-18, e24=0.06, mfdr=0.7)
        for i in range(0, 12, 2)
    ]
    rows = [score_segment_head_chest(s, all_segments=segs, global_baseline={"naq": 0.10, "oq": 0.45, "h1_h2": 4, "mfdr_norm": 1.0, "rms": 0.04}) for s in segs]
    idx = weighted_index(rows)
    assert idx is not None
    assert idx > 0.5


def test_chest_evidence_raises_chest_score():
    chest = _seg(0, 2, naq=0.04, oq=0.35, h1h2=0.0, tilt=-7, e24=0.25, mfdr=1.5)
    base = {"naq": 0.12, "oq": 0.55, "h1_h2": 6.0, "mfdr_norm": 1.0, "rms": 0.04}
    row = score_segment_head_chest(chest, all_segments=[chest], global_baseline=base)
    assert row["status"] == "OK"
    assert (row["chest_score"] or 0) > (row["head_score"] or 0)


def test_head_evidence_raises_head_score():
    head = _seg(0, 2, naq=0.22, oq=0.7, h1h2=14.0, tilt=-20, e24=0.05, mfdr=0.6)
    base = {"naq": 0.10, "oq": 0.45, "h1_h2": 4.0, "mfdr_norm": 1.0, "rms": 0.04}
    row = score_segment_head_chest(head, all_segments=[head], global_baseline=base)
    assert (row["head_score"] or 0) > (row["chest_score"] or 0)


def test_one_metric_family_not_high_confidence_type():
    # Only one weak observation — insufficient families
    s = {
        "start_sec": 0,
        "end_sec": 2,
        "valid": True,
        "rms": 0.05,
        "observations": {"f0_hz": 220, "rms": 0.05, "raw_h1_h2_proxy_db": 10.0},
        "level2_proxies": {"glottal_source": {"valid": False}},
        "vocal_evidence": {"vocal_specific": True},
    }
    row = score_segment_head_chest(s, all_segments=[s], global_baseline={})
    # May score with 1 family but confidence low
    if row.get("status") == "OK":
        assert row.get("confidence") in ("low", "medium")
        assert len(row.get("evidence_families") or []) < 3


def test_mix_requires_smooth_bridge():
    bridge_smooth = {"type": "SMOOTH_BRIDGE", "score": 0.75, "available": True}
    bridge_break = {
        "type": "ABRUPT_REGISTER_BREAK",
        "score": 0.25,
        "available": True,
        "split_eligibility": {"eligible": True},
    }
    assert classify_base_type(index=0.50, bridge=bridge_smooth, modifiers=[], confidence="medium") == "BALANCED_MIX"
    assert (
        classify_base_type(
            index=0.50,
            bridge=bridge_break,
            modifiers=[],
            confidence="medium",
            register_split_ok=True,
        )
        == "REGISTER_SPLIT_GLOBAL"
    )


def test_one_chest_pull_not_global_split():
    t = classify_base_type(
        index=0.48,
        bridge={
            "type": "UNSTABLE_BRIDGE",
            "score": 0.45,
            "split_eligibility": {
                "eligible": False,
                "break_prevalence": 0.1,
                "n_local_chest_pulls": 1,
            },
        },
        modifiers=["CHEST_PULL"],
        confidence="medium",
        register_split_ok=False,
    )
    assert t != "REGISTER_SPLIT_GLOBAL"
    assert t in ("CHEST_DOMINANT_MIX", "BALANCED_MIX", "HEAD_DOMINANT_MIX", "UNRESOLVED")


def test_chest_pull_does_not_rename_global_mix():
    name = compose_display_name(
        "CHEST_DOMINANT_MIX",
        ["CHEST_PULL", "EXCESS_EFFORT"],
        local_events=[{"type": "LOCAL_CHEST_PULL", "start_sec": 11, "end_sec": 23}],
    )
    assert "끌어올리는" not in name
    assert "믹스" in name


def test_chest_heavy_smooth_is_chest_dominant_mix():
    t = classify_base_type(
        index=0.28,
        bridge={"type": "SMOOTH_BRIDGE", "score": 0.8},
        modifiers=[],
        confidence="medium",
    )
    assert t == "CHEST_DOMINANT_MIX"


def test_head_heavy_smooth_is_head_dominant_mix():
    t = classify_base_type(
        index=0.72,
        bridge={"type": "SMOOTH_BRIDGE", "score": 0.8},
        modifiers=[],
        confidence="medium",
    )
    assert t == "HEAD_DOMINANT_MIX"


def test_chest_without_strain_no_effort_modifier_in_name():
    name = compose_display_name("CHEST_DOMINANT_MIX", ["GOOD_BRIDGE"])
    assert "힘" not in name
    assert "믹스" in name


def test_weak_contact_mix_naming():
    name = compose_display_name("CHEST_DOMINANT_MIX", ["WEAK_CONTACT"])
    assert "가벼운" in name


def test_chest_pull_precedence():
    # v1.2: local CHEST_PULL must not override global mix display
    name = compose_display_name("CHEST_DOMINANT_MIX", ["CHEST_PULL", "EXCESS_EFFORT"])
    assert "믹스" in name
    assert "끌어올리는" not in name

def test_korean_names():
    assert "흉성" in compose_display_name("CHEST_DOMINANT_MIX", [])
    assert "두성" in compose_display_name("HEAD_DOMINANT_MIX", [])
    assert "균형" in compose_display_name("BALANCED_MIX", [])


def test_range_missing_high_not_5050():
    segs = [_seg(i, i + 2, f0=180, naq=0.06, h1h2=1.0, tilt=-8) for i in range(0, 10, 2)]
    profile = compute_vocal_type_profile(
        segments=segs,
        dimensions={
            "register_configuration": {"status": "STABLE_LIKE", "profile": {"events": []}},
            "glottal_contact_profile": {"continuum_0_to_1": 0.7, "confidence_label": "medium"},
            "vocal_effort_strain": {"status": "LOW", "confidence_label": "medium"},
            "air_leakage_breathiness": {"status": "LOW", "confidence_label": "medium"},
            "phonation_regularity": {"status": "STABLE"},
            "onset_offset_coordination": {"status": "BALANCED_LIKE"},
            "resonance_formant_strategy": {"profile": {"mid_presence": "보통"}},
        },
        episodes=[],
        baseline={"naq": 0.12, "oq": 0.5, "h1_h2": 5, "mfdr_norm": 1.0, "rms": 0.04},
    )
    high = (profile.get("range_profiles") or {}).get("high") or {}
    assert high.get("available") is False
    assert high.get("chest_ratio") is None


def test_profile_ratios_sum_when_available():
    segs = [
        _seg(i, i + 2, f0=200 + i * 10, naq=0.07, oq=0.4, h1h2=2.0, tilt=-9, e24=0.2, mfdr=1.3)
        for i in range(0, 14, 2)
    ]
    profile = compute_vocal_type_profile(
        segments=segs,
        dimensions={
            "register_configuration": {
                "status": "TRANSITION_EVENTS",
                "profile": {
                    "events": [
                        {
                            "start_sec": 4,
                            "end_sec": 6,
                            "f0_jump_cents": 400,
                            "validity": {"vocal_specific": True},
                            "evidence": {"source_change": True},
                        }
                    ]
                },
            },
            "glottal_contact_profile": {"continuum_0_to_1": 0.7, "confidence_label": "medium"},
            "vocal_effort_strain": {"status": "LOW", "confidence_label": "medium", "hidden": False},
            "air_leakage_breathiness": {"status": "LOW", "hidden": True},
            "phonation_regularity": {"status": "STABLE"},
            "onset_offset_coordination": {"status": "BALANCED_LIKE"},
            "resonance_formant_strategy": {"profile": {"mid_presence": "보통"}},
        },
        episodes=[
            {
                "type": "REGISTER_TRANSITION",
                "start_sec": 4,
                "end_sec": 6,
                "core_evidence_span": {"start_sec": 4.5, "end_sec": 5.5, "duration_sec": 1.0},
            }
        ],
        baseline={"naq": 0.12, "oq": 0.55, "h1_h2": 6, "mfdr_norm": 1.0, "rms": 0.04},
        coaching_decision={"primary_bottleneck": None},
    )
    hc = profile["head_chest"]
    if hc.get("available"):
        assert hc["chest_ratio"] + hc["head_ratio"] == 100


def test_song_detail_includes_vocal_type_before_coaching_fields():
    report = build_song_detailed_report(
        {
            "score": {"available": False, "areas": []},
            "quality": {"status": "pass"},
            "optional_analysis": {},
            "vocal_function_profile": {
                "available": True,
                "engine_version": "vocal-function-v2.4",
                "report_version": "vocal-coach-report-v2.4",
                "headline": [],
                "dimensions": {},
                "criteria_matrix": [],
                "vocal_type_profile": {
                    "available": True,
                    "type_id": "CHEST_DOMINANT_MIX",
                    "display_name": "흉성 비율이 높은 믹스보이스",
                    "confidence": "medium",
                    "confidence_label": "중간",
                    "head_chest": {
                        "available": True,
                        "chest_ratio": 64,
                        "head_ratio": 36,
                        "index": 0.36,
                    },
                    "description": "중·고음에서도 흉성 비중이 비교적 강하게 유지됩니다.",
                    "key_traits": [{"key": "contact", "label": "접촉", "value": "단단한 편"}],
                    "modifiers": [],
                    "bridge": {"type": "SMOOTH_BRIDGE"},
                    "range_profiles": {},
                    "timeline": [],
                },
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
        analysis_id="vt",
    )
    vt = report["vocal_type_profile"]
    assert vt["available"] is True
    assert vt["head_chest"]["chest_ratio"] == 64
    assert "근육" not in str(vt)
    assert "disclaimer" not in (vt.get("description") or "")
    blob = str(vt)
    assert "실제 근육" not in blob


def test_f0_flag_never_register_vote():
    s = _seg(0, 2, f0=500, naq=0.05, h1h2=1.0)
    row = score_segment_head_chest(s, all_segments=[s], global_baseline={"naq": 0.12, "h1_h2": 5, "oq": 0.5, "mfdr_norm": 1, "rms": 0.04})
    assert row.get("f0_used_as_register_vote") is False
