"""Presentation-layer contract for FREE vocal type / finding teasers."""

from audio_analyzer.models import free_public_result


def test_free_includes_vocal_type_and_main_finding_teasers():
    fake = {
        "analysis_version": "2.0",
        "recording_id": "x",
        "audio": {"duration_sec": 20, "sample_rate": 44100, "source_mode": "raw", "separation": {}},
        "quality": {
            "status": "pass",
            "confidence": 0.9,
            "reasons": [],
            "codes": [],
            "metrics": {"duration_sec": 20},
        },
        "score": {
            "available": True,
            "version": "v2",
            "calibration_status": "uncalibrated",
            "overall": 70,
            "label": "좋아요",
            "areas": [
                {
                    "area_id": "stability",
                    "display_name": "안정성",
                    "score": 70,
                    "status": "ok",
                    "confidence": 0.8,
                }
            ],
            "strengths": [{"area_id": "stability", "display_name": "안정성"}],
            "priority_issues": [],
        },
        "vocal_function_profile": {
            "available": True,
            "vocal_type_profile": {
                "available": True,
                "display_name": "두성 비율이 높은 믹스보이스",
                "description": "중음부터 두성 비중이 비교적 빠르게 늘어나는 믹스보이스입니다.",
                "confidence": "medium",
                "confidence_label": "medium",
                "head_chest": {
                    "available": True,
                    "chest_ratio": 43,
                    "head_ratio": 57,
                },
                "key_traits": [
                    {"key": "resonance", "label": "공명", "value": "중역 존재감 낮은 편"},
                    {"key": "contact", "label": "접촉", "value": "가벼운 편"},
                ],
            },
            "coaching_decision": {
                "primary_bottleneck": {
                    "id": "RESONANCE_MID_PRESENCE_LOSS",
                    "user_title": "중역 존재감이 낮아지는 경향",
                    "why": "중역에서 존재감이 약해졌어요.",
                }
            },
            "dimensions": {},
        },
    }
    pub = free_public_result(fake)
    assert "vocal_type_teaser" in pub
    assert pub["vocal_type_teaser"]["available"] is True
    assert pub["vocal_type_teaser"]["head_chest"]["chest_ratio"] == 43
    assert pub["main_finding_teaser"]["none"] is False
    assert pub["main_finding_teaser"]["state"] == "FOUND"
    assert pub["main_finding_teaser"]["id"] == "RESONANCE_MID_PRESENCE_LOSS"
    assert "연습" not in pub["disclaimer"]
    assert "timeline" not in pub
    assert "criteria_matrix" not in pub


def test_free_main_finding_none_when_no_primary():
    fake = {
        "quality": {"status": "pass", "confidence": 0.9, "metrics": {}},
        "score": {"available": True, "areas": []},
        "audio": {},
        "vocal_function_profile": {
            "available": True,
            "vocal_type_profile": {"available": False},
            "coaching_decision": {},
            "dimensions": {},
        },
    }
    pub = free_public_result(fake)
    assert pub["main_finding_teaser"]["none"] is True
    assert pub["main_finding_teaser"]["state"] == "NONE"
    assert "두드러진 발성 문제" in pub["main_finding_teaser"]["title"]


def test_free_main_finding_unresolved_when_decision_missing():
    fake = {
        "quality": {"status": "pass", "confidence": 0.9, "metrics": {}},
        "score": {"available": True, "areas": []},
        "audio": {},
        "vocal_function_profile": {
            "available": True,
            "vocal_type_profile": {"available": False},
            "dimensions": {},
        },
    }
    pub = free_public_result(fake)
    assert pub["main_finding_teaser"]["state"] == "UNRESOLVED"
    assert pub["main_finding_teaser"]["none"] is False
    assert "핵심으로 정하기 어려웠어요" in pub["main_finding_teaser"]["title"]
    assert pub["vocal_type_teaser"]["resolution_state"]
