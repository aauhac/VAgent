"""Song Detail v3 evidence-aware report tests."""

from __future__ import annotations

from audio_analyzer.song_detail.copy import join_summary, submetric_display_name
from audio_analyzer.song_detail.explain_v3 import (
    build_overall_assessment,
    explain_area,
)
from audio_analyzer.song_detail.report import build_song_detailed_report
from audio_analyzer.song_detail.segments import build_focus_segments_from_v3


def _area(
    area_id: str,
    score,
    status: str,
    *,
    confidence: float = 0.8,
    coverage: float = 0.85,
    subs=None,
    segments=None,
    worst=None,
    bad_ratio=None,
    ceiling_reasons=None,
):
    return {
        "area_id": area_id,
        "display_name": {
            "stability": "발성 안정성",
            "projection": "목소리 전달력",
            "resonance": "공명 균형",
            "dynamic_control": "강약 컨트롤",
        }[area_id],
        "score": score,
        "status": status,
        "status_label": "판단 어려움" if status == "unknown" else status,
        "confidence": confidence,
        "coverage": coverage,
        "ceiling_reasons": ceiling_reasons or [],
        "submetrics": subs or [],
        "segment_scores": segments or [],
        "temporal": {"worst": worst, "bad_segment_ratio": bad_ratio},
    }


def _sub(sid, score, conf=0.8, name=None):
    return {
        "submetric_id": sid,
        "display_name": name or sid,
        "score": score,
        "status": "good" if score and score >= 70 else "needs_work",
        "confidence": conf,
        "coverage": 0.8,
    }


def test_case1_stability_pitch_strong_level_weak():
    area = _area(
        "stability",
        62,
        "needs_work",
        worst=49,
        subs=[
            _sub("sustain_pitch_stability", 96, name="지속음 안정성"),
            _sub("sustain_level_stability", 51, name="음량 유지"),
            _sub("region_consistency", 77, name="구간 일관성"),
            _sub("unstable_region_ratio", 100, name="구간 안정 유지"),
            _sub("stability_worst_region", 49, name="최악 구간"),
        ],
    )
    ex = explain_area(area)
    blob = ex["headline"] + ex["interpretation"] + str(ex["why_this_score"])
    assert "음높이" in blob or "음 중심" in blob or "지속음 안정성" in blob
    assert "음량" in blob
    assert "길게 뻗는 음에서 소리가 흔들" not in blob
    assert any("지속음 안정성" in w for w in ex["why_this_score"])
    assert any("음량 유지" in w for w in ex["why_this_score"])


def test_case2_dynamic_worst_not_flat_copy():
    area = _area(
        "dynamic_control",
        58,
        "needs_work",
        worst=40,
        bad_ratio=0.1,
        subs=[
            _sub("global_dynamic_range", 70),
            _sub("local_dynamic_variation", 82),
            _sub("smoothness", 84),
            _sub("phrase_consistency", 72),
            _sub("abrupt_change_ratio", 84),
            _sub("dynamic_worst_segment", 40),
        ],
        segments=[
            {"start_sec": 10, "end_sec": 13, "score": 80, "confidence": 0.8},
            {"start_sec": 42, "end_sec": 45, "score": 40, "confidence": 0.75},
        ],
    )
    ex = explain_area(area)
    blob = ex["interpretation"] + ex["headline"]
    assert "평평" not in blob
    assert "구간" in blob or "무너" in blob or "흔들" in blob


def test_case3_unknown_shows_partial_submetrics():
    analysis = {
        "score": {
            "available": True,
            "version": "vocal-score-v3.0",
            "overall": 59.8,
            "label": "개선 여지가 있어요",
            "overall_coverage": 0.5,
            "areas": [
                _area(
                    "projection",
                    None,
                    "unknown",
                    confidence=0.25,
                    coverage=0.7,
                    ceiling_reasons=["confidence_below_unknown"],
                    subs=[
                        _sub("spectral_projection", 100, conf=0.15),
                        _sub("presence_prominence", 30, conf=0.55),
                        _sub("projection_consistency", 65, conf=0.5),
                    ],
                ),
                _area("stability", 62, "needs_work", worst=49, subs=[_sub("sustain_pitch_stability", 90)]),
                _area("resonance", None, "unknown", confidence=0.2, subs=[]),
                _area("dynamic_control", 58, "needs_work", worst=40, subs=[_sub("smoothness", 84)]),
            ],
        },
        "quality": {"status": "warn"},
        "timeline": [],
        "optional_analysis": {"vibrato": {"available": False}},
    }
    report = build_song_detailed_report(analysis, analysis_id="x")
    proj = next(a for a in report["areas"] if a["area_id"] == "projection")
    assert proj["status"] == "unknown"
    assert any(s.get("score") is not None for s in proj["submetrics"])
    assert "신뢰" in proj["interpretation"] or "충분" in proj["interpretation"]


def test_case4_positive_oriented_names():
    assert submetric_display_name("unstable_region_ratio") == "구간 안정 유지"
    assert submetric_display_name("weak_projection_segment_ratio") == "전달 유지력"
    assert submetric_display_name("extreme_resonance_ratio") == "공명 균형 유지력"
    assert submetric_display_name("abrupt_change_ratio") == "강약 변화 안정성"


def test_case5_worst_segment_timeline_non_empty():
    score = {
        "areas": [
            _area(
                "dynamic_control",
                58,
                "needs_work",
                worst=40,
                segments=[
                    {"start_sec": 42.0, "end_sec": 45.0, "score": 40, "confidence": 0.8},
                    {"start_sec": 10.0, "end_sec": 13.0, "score": 82, "confidence": 0.8},
                ],
            )
        ]
    }
    focus = build_focus_segments_from_v3(score)
    assert len(focus) >= 1
    assert focus[0]["start_sec"] == 42.0
    assert focus[0]["end_sec"] == 45.0


def test_case6_focus_seek_fields_preserved():
    score = {
        "areas": [
            _area(
                "stability",
                62,
                "needs_work",
                worst=49,
                segments=[{"start_sec": 18.2, "end_sec": 21.1, "score": 49, "confidence": 0.7}],
            )
        ]
    }
    focus = build_focus_segments_from_v3(score)
    assert focus[0]["start_sec"] == 18.2
    assert focus[0]["end_sec"] == 21.1


def test_case7_partial_overall_state():
    score = {
        "available": True,
        "overall": 59.8,
        "label": "개선 여지가 있어요",
        "overall_coverage": 0.55,
        "areas": [
            _area("stability", 62, "needs_work"),
            _area("dynamic_control", 58, "needs_work"),
            _area("projection", None, "unknown", confidence=0.2),
            _area("resonance", None, "unknown", confidence=0.2),
        ],
    }
    oa = build_overall_assessment(score)
    assert oa["overall_display_state"] == "PARTIAL"
    assert "부분 분석" in oa["text"]


def test_case8_full_overall_possible():
    score = {
        "available": True,
        "overall": 70.0,
        "label": "좋은 편",
        "overall_coverage": 0.8,
        "areas": [
            _area("stability", 72, "good"),
            _area("dynamic_control", 68, "normal"),
            _area("projection", 66, "normal"),
            _area("resonance", 64, "normal"),
        ],
    }
    oa = build_overall_assessment(score)
    assert oa["overall_display_state"] == "FULL"


def test_case9_vibrato_no_dash_cents():
    report = build_song_detailed_report(
        {
            "score": {
                "available": True,
                "overall": 60,
                "label": "보통이에요",
                "areas": [_area("stability", 70, "good")],
            },
            "quality": {"status": "pass"},
            "optional_analysis": {
                "vibrato": {"available": True, "rate_hz": 6.24, "depth_cents": None}
            },
        }
    )
    blob = str(report["vibrato"])
    assert "— cents" not in blob
    assert "extent —" not in blob
    assert any("깊이" in (x.get("value") or "") or "깊이" in (x.get("label") or "") for x in report["vibrato"].get("lines") or [])


def test_case10_summary_no_double_iyo():
    text = join_summary(59.8, "개선 여지가 있어요", partial=True)
    assert "있어요이에요" not in text
    report = build_song_detailed_report(
        {
            "score": {
                "available": True,
                "overall": 59.8,
                "label": "개선 여지가 있어요",
                "overall_coverage": 0.5,
                "areas": [
                    _area("stability", 62, "needs_work"),
                    _area("dynamic_control", 58, "needs_work"),
                    _area("projection", None, "unknown", confidence=0.2),
                    _area("resonance", None, "unknown", confidence=0.2),
                ],
            },
            "quality": {"status": "pass"},
            "optional_analysis": {"vibrato": {"available": False}},
        }
    )
    assert "있어요이에요" not in report["summary"]["text"]


def test_case11_unknown_has_concrete_reason():
    area = _area(
        "projection",
        None,
        "unknown",
        confidence=0.22,
        coverage=0.4,
        ceiling_reasons=["confidence_below_unknown"],
        subs=[_sub("presence_prominence", 30, conf=0.5)],
    )
    ex = explain_area(area)
    assert "또렷한 녹음" not in ex["interpretation"] or "신뢰" in ex["interpretation"]
    assert "신뢰" in ex["interpretation"] or "충분" in ex["interpretation"]


def test_case12_low_conf_100_not_perfect_copy():
    report = build_song_detailed_report(
        {
            "score": {
                "available": True,
                "overall": 60,
                "label": "보통이에요",
                "areas": [
                    _area(
                        "projection",
                        None,
                        "unknown",
                        confidence=0.2,
                        subs=[_sub("spectral_projection", 100, conf=0.15)],
                    )
                ],
            },
            "quality": {"status": "pass"},
            "optional_analysis": {"vibrato": {"available": False}},
        }
    )
    proj = report["areas"][0]
    sm = next(s for s in proj["submetrics"] if s["submetric_id"] == "spectral_projection")
    # score hidden or marked low confidence — not presented as perfect certainty
    assert sm["score"] is None or sm.get("display_note")
    assert "완벽" not in (proj.get("interpretation") or "")


def test_case13_14_no_physiology_in_song_detail():
    report = build_song_detailed_report(
        {
            "score": {
                "available": True,
                "overall": 60,
                "label": "보통이에요",
                "areas": [
                    _area(
                        "stability",
                        62,
                        "needs_work",
                        worst=49,
                        segments=[{"start_sec": 1, "end_sec": 3, "score": 49, "confidence": 0.8}],
                        subs=[_sub("sustain_level_stability", 51)],
                    )
                ],
            },
            "quality": {"status": "pass"},
            "optional_analysis": {"vibrato": {"available": False}},
            "physiology_assessments": [{"mechanism_id": "x"}],
        }
    )
    assert "physiology_assessments" not in report
    assert "reliable_findings" not in report
    blob = str(report)
    assert "glottal_closure" not in blob
    assert report["focus_segments"]


def test_report_version_bump():
    report = build_song_detailed_report(
        {
            "score": {"available": False, "areas": []},
            "quality": {"status": "fail"},
            "optional_analysis": {},
        }
    )
    assert report["report_version"].startswith("song-detail-v1.1")
