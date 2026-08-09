"""Compatibility."""

from audio_analyzer.feedback.user_text import AREA_COPY as USER_FACING_ISSUE_TEXT


def build_user_facing_assessment(*_args, **_kwargs) -> dict:
    return {"user_facing_issues": [], "user_facing_strengths": []}
