"""Compatibility shim."""

from audio_analyzer.feedback.llm import (
    build_user_friendly_report,
    generate_feedback,
    generate_feedback_from_files,
)

__all__ = [
    "generate_feedback",
    "generate_feedback_from_files",
    "build_user_friendly_report",
]
ㅎ