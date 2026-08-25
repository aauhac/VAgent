"""Public FREE / history presentation for UNRESOLVED vocal types."""

from audio_analyzer.coach_profile.public_presentation import (
    INTERNAL_UNRESOLVED_LABEL,
    apply_public_vocal_type_copy,
    public_vocal_type_label,
)
from audio_analyzer.models import free_public_result


def _base_result(vocal_type_profile: dict) -> dict:
    return {
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
            "areas": [],
            "strengths": [],
            "priority_issues": [],
        },
        "vocal_function_profile": {
            "available": True,
            "vocal_type_profile": vocal_type_profile,
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


def test_insufficient_evidence_public_copy():
    pub = free_public_result(
        _base_result(
            {
                "available": False,
                "base_type": "UNRESOLVED",
                "resolution_state": "INSUFFICIENT_EVIDENCE",
                "display_name": INTERNAL_UNRESOLVED_LABEL,
                "description": "internal",
            }
        )
    )
    teaser = pub["vocal_type_teaser"]
    assert teaser["resolution_state"] == "INSUFFICIENT_EVIDENCE"
    assert INTERNAL_UNRESOLVED_LABEL not in str(teaser["display_name"])
    assert "충분히 구분하기 어려웠어요" in teaser["display_name"]
    assert "발성 구간이 더 필요" in teaser["description"]


def test_conflicted_evidence_public_copy():
    pub = free_public_result(
        _base_result(
            {
                "available": False,
                "base_type": "UNRESOLVED",
                "resolution_state": "CONFLICTED_EVIDENCE",
                "display_name": INTERNAL_UNRESOLVED_LABEL,
            }
        )
    )
    teaser = pub["vocal_type_teaser"]
    assert teaser["resolution_state"] == "CONFLICTED_EVIDENCE"
    assert "한쪽으로 단정하기 어려웠어요" in teaser["display_name"]
    assert INTERNAL_UNRESOLVED_LABEL not in str(teaser)


def test_neutral_evidence_public_copy():
    pub = free_public_result(
        _base_result(
            {
                "available": False,
                "base_type": "UNRESOLVED",
                "resolution_state": "NEUTRAL_EVIDENCE",
                "display_name": INTERNAL_UNRESOLVED_LABEL,
            }
        )
    )
    teaser = pub["vocal_type_teaser"]
    assert teaser["resolution_state"] == "NEUTRAL_EVIDENCE"
    assert "뚜렷하지 않았어요" in teaser["display_name"]
    assert INTERNAL_UNRESOLVED_LABEL not in str(teaser)


def test_resolved_keeps_display_name():
    name = "두성 비율이 높은 믹스보이스"
    pub = free_public_result(
        _base_result(
            {
                "available": True,
                "base_type": "HEAD_DOMINANT_MIX",
                "resolution_state": "RESOLVED",
                "display_name": name,
                "description": "desc",
                "head_chest": {"available": True, "chest_ratio": 40, "head_ratio": 60},
            }
        )
    )
    assert pub["vocal_type_teaser"]["display_name"] == name
    assert pub["vocal_type_teaser"]["resolution_state"] == "RESOLVED"


def test_history_label_helper_strips_internal():
    label = public_vocal_type_label(
        resolution_state="INSUFFICIENT_EVIDENCE",
        display_name=INTERNAL_UNRESOLVED_LABEL,
        available=False,
    )
    assert label is not None
    assert INTERNAL_UNRESOLVED_LABEL not in label


def test_apply_public_copy_idempotent():
    payload = apply_public_vocal_type_copy(
        {
            "available": False,
            "resolution_state": "CONFLICTED_EVIDENCE",
            "display_name": INTERNAL_UNRESOLVED_LABEL,
            "description": "x",
        }
    )
    again = apply_public_vocal_type_copy(dict(payload))
    assert again["display_name"] == payload["display_name"]
