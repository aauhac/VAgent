"""Compatibility — artifact filtering replaced by UNKNOWN status in v2 scoring."""


def filter_preprocessing_artifacts(analysis_result: dict) -> dict:
    return {
        "feedback_eligible": [],
        "artifact_warnings": [],
        "demucs_hf_loss": False,
        "artifact_notes": analysis_result.get("analysis_notes") or [],
    }
