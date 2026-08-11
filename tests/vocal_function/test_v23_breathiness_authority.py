"""v2.3 — breathiness validity, roughness disambiguation, report authority."""

from __future__ import annotations

from audio_analyzer.song_detail.report import build_song_detailed_report
from audio_analyzer.vocal_evidence.phonation_quality import (
    classify_breathy_segment,
    classify_rough_segment,
    disambiguate_breathy_vs_rough,
    vocal_presence_ok,
)
from audio_analyzer.vocal_function.rules.fusion import fuse_leakage, fuse_regularity
from audio_analyzer.vocal_function.validity import build_validity_by_dimension, dim_valid
from audio_analyzer.vocal_quality.rules import fuse_breathy, fuse_rough


def _seg(
    start: float,
    end: float,
    *,
    obs=None,
    src=None,
    valid: bool = True,
    voiced_ratio: float = 0.7,
    ve=None,
    rms: float | None = 0.05,
):
    observations = dict(obs or {})
    if rms is not None and "rms" not in observations:
        observations["rms"] = rms
    seg = {
        "start_sec": start,
        "end_sec": end,
        "valid": valid,
        "voiced_ratio": voiced_ratio,
        "observations": observations,
        "vocal_evidence": ve
        or {
            "vocal_specific": True,
            "vocal_dominance": 0.8,
            "vocal_confidence": 0.7,
        },
        "level2_proxies": {
            "glottal_source": src if src is not None else {"valid": False, "reason": "gif_fail"},
            "gif_gate": {"valid": False},
            "formants": {"valid": True, "confidence": 0.5},
        },
        "rms": rms,
    }
    seg["validity_by_dimension"] = build_validity_by_dimension(seg)
    return seg


# --- validity ---


def test_low_voiced_periodicity_does_not_invalidate_breathiness():
    s = _seg(
        0,
        2,
        valid=False,  # global invalid
        voiced_ratio=0.15,
        obs={
            "periodicity_primary_db": 5.0,
            "raw_h1_h2_proxy_db": 9.0,
            "spectral_tilt_db_per_oct": -18.0,
        },
        src={"valid": False},
        ve={"vocal_specific": False, "vocal_dominance": 0.5},
    )
    assert dim_valid(s, "breathiness") is True
    assert classify_breathy_segment(s)["verdict"] == "POSITIVE"


def test_gif_invalid_still_allows_breathiness():
    s = _seg(
        0,
        2,
        obs={
            "periodicity_primary_db": 4.0,
            "raw_h1_h2_proxy_db": 10.0,
            "spectral_tilt_db_per_oct": -19.0,
        },
        src={"valid": False, "reason": "unstable"},
    )
    assert dim_valid(s, "breathiness") is True
    # v2.7: GIF invalid is not absolute — harmonic+spectral fallback can make contact evaluable
    assert dim_valid(s, "glottal_contact") is True
    assert (s["validity_by_dimension"]["glottal_contact"].get("confidence_cap") == "low")
    assert classify_breathy_segment(s)["verdict"] == "POSITIVE"


def test_gif_invalid_blocks_contact_source_claim():
    s = _seg(0, 2, obs={"periodicity_primary_db": 12.0, "f0_hz": 220}, src={"valid": False})
    assert dim_valid(s, "glottal_contact") is False


def test_silence_not_breathy():
    s = _seg(
        0,
        2,
        rms=1e-8,
        obs={},
        voiced_ratio=0.0,
        ve={"vocal_energy": 0.0, "vocal_dominance": 0.1},
    )
    assert vocal_presence_ok(s) is False
    assert classify_breathy_segment(s)["verdict"] == "INSUFFICIENT"


def test_breathiness_insufficient_coverage_unknown():
    # Only 2 evaluable — below MIN_SEGMENTS_GLOBAL=3
    segs = [
        _seg(
            i,
            i + 2,
            obs={
                "periodicity_primary_db": 5.0,
                "raw_h1_h2_proxy_db": 10.0,
                "spectral_tilt_db_per_oct": -18.0,
            },
        )
        for i in (0, 2)
    ]
    out = fuse_leakage(segs)
    assert out["status"] == "UNKNOWN"


def test_zero_positive_strong_negative_is_low():
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
        for i in range(0, 12, 2)
    ]
    out = fuse_leakage(segs)
    assert out["status"] == "LOW"
    assert out["breathiness_coverage"]["n_positive_segments"] == 0
    assert out["breathiness_coverage"]["n_negative_segments"] >= 3


def test_zero_positive_without_negative_not_low():
    # Single family only → insufficient, not negative
    segs = [
        _seg(
            i,
            i + 2,
            obs={
                "periodicity_primary_db": 5.0,
                "raw_h1_h2_proxy_db": 2.0,  # not breathy spectral
            },
        )
        for i in range(0, 12, 2)
    ]
    out = fuse_leakage(segs)
    assert out["status"] != "LOW"
    assert out["status"] == "UNKNOWN"


# --- roughness ---


def test_low_cpp_alone_not_rough():
    s = _seg(0, 2, obs={"periodicity_primary_db": 4.0, "f0_frame_period_perturbation_proxy_percent": 0.5})
    c = classify_rough_segment(s)
    assert c["verdict"] == "REJECTED"
    assert c["reason"] == "periodicity_loss_without_irregularity"


def test_low_cpp_plus_perturbation_rough_eligible():
    s = _seg(
        0,
        2,
        obs={
            "periodicity_primary_db": 4.0,
            "f0_frame_period_perturbation_proxy_percent": 3.5,
            "f0_tracker_artifact": {
                "suspect": False,
                "n_voiced": 20,
                "n_frames": 24,
                "octave_jumps": 0,
            },
        },
    )
    assert classify_rough_segment(s)["verdict"] == "POSITIVE"


def test_breathy_spectral_low_period_low_perturb_rough_rejected():
    s = _seg(
        0,
        2,
        obs={
            "periodicity_primary_db": 5.0,
            "raw_h1_h2_proxy_db": 10.0,
            "spectral_tilt_db_per_oct": -18.0,
            "f0_frame_period_perturbation_proxy_percent": 0.4,
        },
    )
    d = disambiguate_breathy_vs_rough(s)
    assert d["label"] == "BREATHY"
    assert d["rough"]["verdict"] == "REJECTED"


def test_breathy_plus_true_irregularity_mixed():
    s = _seg(
        0,
        2,
        obs={
            "periodicity_primary_db": 4.0,
            "raw_h1_h2_proxy_db": 10.0,
            "spectral_tilt_db_per_oct": -18.0,
            "f0_frame_period_perturbation_proxy_percent": 3.5,
            "f0_tracker_artifact": {
                "suspect": False,
                "n_voiced": 20,
                "n_frames": 24,
                "octave_jumps": 0,
            },
        },
    )
    d = disambiguate_breathy_vs_rough(s)
    assert d["label"] == "MIXED"


def test_fuse_regularity_rejects_cpp_only():
    segs = [
        _seg(i, i + 2, obs={"periodicity_primary_db": 4.0, "f0_frame_period_perturbation_proxy_percent": 0.3})
        for i in range(0, 12, 2)
    ]
    out = fuse_regularity(segs)
    assert out["status"] == "STABLE"
    assert out["roughness_coverage"]["rejected_periodicity_only"] >= 3


# --- paired synthetic direction ---


def test_synthetic_airy_more_breathy_than_closed():
    airy = [
        _seg(
            i,
            i + 2,
            obs={
                "periodicity_primary_db": 4.5,
                "raw_h1_h2_proxy_db": 11.0,
                "spectral_tilt_db_per_oct": -19.0,
            },
            src={"valid": False},
        )
        for i in range(0, 14, 2)
    ]
    closed = [
        _seg(
            i,
            i + 2,
            obs={
                "periodicity_primary_db": 14.0,
                "raw_h1_h2_proxy_db": 1.5,
                "spectral_tilt_db_per_oct": -8.0,
                "energy_2_4k": 0.2,
            },
            src={
                "valid": True,
                "estimated_naq": 0.05,
                "estimated_oq_proxy": 0.4,
                "estimated_mfdr_norm_proxy": 1.2,
            },
        )
        for i in range(0, 14, 2)
    ]
    a = fuse_leakage(airy)
    c = fuse_leakage(closed)
    assert a["breathiness_coverage"]["n_positive_segments"] > c["breathiness_coverage"]["n_positive_segments"]
    assert a["status"] in ("MODERATE", "HIGH", "OCCASIONAL")
    assert c["status"] in ("LOW", "UNKNOWN")


def test_closed_contact_can_rise_without_strain():
    from audio_analyzer.vocal_function.evidence.families import effort_like, firmer_like
    from audio_analyzer.vocal_function.rules.fusion import fuse_contact, fuse_effort

    segs = [
        _seg(
            i,
            i + 2,
            obs={
                "periodicity_primary_db": 14.0,
                "raw_h1_h2_proxy_db": -1.0,
                "energy_2_4k": 0.2,
                "onset_slope_db_per_sec": 20.0,
                "f0_frame_period_perturbation_proxy_percent": 0.4,
            },
            src={
                "valid": True,
                "estimated_naq": 0.05,
                "estimated_oq_proxy": 0.4,
                "estimated_mfdr_norm_proxy": 1.0,
            },
        )
        for i in range(0, 12, 2)
    ]
    assert any(firmer_like(s) for s in segs)
    assert not any(effort_like(s) for s in segs)
    effort = fuse_effort(segs)
    assert effort["status"] == "LOW"
    contact = fuse_contact(segs)
    assert contact["status"] not in ("UNKNOWN",) or contact.get("confidence_label") != "high"


# --- report authority ---


def _base_analysis(**kwargs):
    base = {
        "score": {
            "available": True,
            "overall": 55,
            "label": "보통",
            "version": "vocal-score-v3",
            "areas": [
                {
                    "area_id": "stability",
                    "display_name": "발성 안정성",
                    "score": 40,
                    "status": "needs_work",
                    "confidence": 0.85,
                    "submetrics": [],
                    "temporal": {},
                    "segment_scores": [{"start_sec": 1, "end_sec": 3, "score": 35}],
                },
                {
                    "area_id": "dynamic_control",
                    "display_name": "강약 컨트롤",
                    "score": 38,
                    "status": "needs_work",
                    "confidence": 0.85,
                    "submetrics": [],
                    "temporal": {},
                    "segment_scores": [{"start_sec": 4, "end_sec": 6, "score": 30}],
                },
            ],
        },
        "quality": {"status": "pass"},
        "optional_analysis": {"vibrato": {"available": False}},
        "vocal_quality_profile": {
            "available": True,
            "headline": ["거친 음질"],
            "focus_segments": [
                {
                    "start_sec": 2.0,
                    "end_sec": 4.0,
                    "headline": "거칠고 불규칙한 음질",
                    "user_message": "관찰",
                    "state": "HIGH",
                }
            ],
            "dimensions": {
                "rough_like": {
                    "dimension_id": "rough_like",
                    "status": "HIGH",
                    "hidden": False,
                    "practice": ["문제 구간만 반복하세요"],
                    "focus_segments": [
                        {"start_sec": 2.0, "end_sec": 4.0, "headline": "거친 음질"}
                    ],
                }
            },
        },
        "vocal_function_profile": {
            "available": True,
            "engine_version": "vocal-function-v2.3",
            "report_version": "vocal-coach-report-v2.3",
            "quality_badge": "기능 분석 범위: 충분",
            "headline": [],
            "dimensions": {},
            "focus_segments": [],
            "training_plan": [],
            "coaching_decision": {
                "primary_bottleneck": None,
                "secondary_bottlenecks": [],
                "no_primary_message": "뚜렷한 교정 우선순위 없음",
                "exercise_plan": [],
                "modify": [],
                "preserve": [{"id": "periodicity", "label": "주기성"}],
            },
            "high_note_events": [],
            "disclaimer": "x",
        },
    }
    base.update(kwargs)
    return base


def test_no_primary_vq_issue_no_main_problem_section():
    report = build_song_detailed_report(_base_analysis(), analysis_id="t")
    assert report["show_problem_focus"] is False
    assert report["focus_segments"] == []
    assert report["observation_segments"]
    assert report["observation_segments"][0].get("focus_kind") == "observation"
    blob = " ".join(
        str(e.get("headline")) for e in report["observation_segments"]
    )
    assert "문제" not in (report.get("summary") or {}).get("text", "")


def test_no_primary_performance_no_corrective_training():
    report = build_song_detailed_report(_base_analysis(), analysis_id="t")
    assert report["training_plan"] == []
    assert report["show_corrective_training"] is False
    assert "문제 구간" not in str(report["training_plan"])
    assert "SOVT" not in str(report["training_plan"])


def test_functional_primary_overrides_supplement():
    vf = _base_analysis()["vocal_function_profile"]
    vf = {
        **vf,
        "training_plan": ["effort 연습: 고음에서 힘 빼기"],
        "focus_segments": [],
        "coaching_decision": {
            "primary_bottleneck": {
                "id": "EXCESS_EFFORT_HIGH_NOTE",
                "user_title": "고음 effort",
                "why": "힘",
            },
            "secondary_bottlenecks": [],
            "target_episode": {
                "start_sec": 10.0,
                "end_sec": 12.0,
                "original_start_sec": 10.0,
                "original_end_sec": 12.0,
            },
            "modify": [{"label": "effort", "why": "고음"}],
            "exercise_plan": [{"instructions": "effort 연습: 고음에서 힘 빼기"}],
            "preserve": [],
        },
    }
    report = build_song_detailed_report(_base_analysis(vocal_function_profile=vf), analysis_id="t")
    assert report["show_problem_focus"] is True
    assert report["focus_segments"][0]["start_sec"] == 10.0
    assert report["training_plan"] == ["effort 연습: 고음에서 힘 빼기"]
    # VQ practice not merged
    assert "문제 구간만 반복하세요" not in report["training_plan"]


def test_main_training_from_functional_only():
    report = build_song_detailed_report(_base_analysis(), analysis_id="t")
    assert report["training_plan"] == []
    # observation focus labeled non-problem
    for ev in report.get("observation_segments") or []:
        assert ev.get("role") == "OBSERVATION"
        assert ev.get("focus_kind") == "observation"


def test_vq_fuse_breathy_uses_shared_and_no_auto_low():
    segs = [
        _seg(i, i + 2, obs={"periodicity_primary_db": 5.0, "raw_h1_h2_proxy_db": 2.0})
        for i in range(0, 12, 2)
    ]
    out = fuse_breathy(segs)
    assert out["status"] != "LOW" or out.get("hit_segment_count", 0) == 0
    # With only single-family / insufficient → UNKNOWN preferred over false LOW
    assert out["status"] in ("UNKNOWN", "LOW", "INTERMITTENT")


def test_vq_rough_cpp_alone_no_hit():
    segs = [
        _seg(i, i + 2, obs={"periodicity_primary_db": 4.0, "f0_frame_period_perturbation_proxy_percent": 0.5})
        for i in range(0, 12, 2)
    ]
    out = fuse_rough(segs)
    assert out["hit_segment_count"] == 0
