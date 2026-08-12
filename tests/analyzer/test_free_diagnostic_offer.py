from audio_analyzer.models import free_public_result


def test_free_public_result_exposes_diagnostic_offer_additive():
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
            "strengths": [],
            "priority_issues": [],
        },
        "vocal_function_profile": {
            "criteria_matrix": [],
            "dimensions": {},
            "coaching_decision": {"measurement_candidates": []},
        },
    }
    pub = free_public_result(fake)
    assert "diagnostic_offer" in pub
    offer = pub["diagnostic_offer"]
    assert offer is None or isinstance(offer, dict)
    if isinstance(offer, dict):
        assert "selected_task_count" in offer
        assert "required" in offer
    assert "정확한 분석" not in (pub.get("short_summary") or "")
    assert "정확도" not in (pub.get("diagnostic_cta") or {}).get("body", "")
