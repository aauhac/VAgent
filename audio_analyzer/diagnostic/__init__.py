"""Diagnostic protocol package."""

from .protocol import (
    TASKS,
    SAFETY_QUESTIONS,
    VOCAL_DIAGNOSTIC_PROTOCOL_VERSION,
    get_task,
    tasks_for_ids,
)
from .analyze import analyze_task_audio
from .task_registry import PLANNER_VERSION, PROTOCOL_VERSION, TASK_REGISTRY
from .planner import (
    build_uncertainty_profile,
    explain_task_selection,
    plan_from_song_analysis,
    plan_precision_protocol,
    select_diagnostic_tasks,
)
from .concerns import (
    build_personalized_qa,
    has_pain_safety_flag,
    normalize_diagnostic_mode,
    normalize_user_concerns,
    public_concern_catalog,
)
from .fusion import build_final_diagnostic_profile, fuse_song_and_task_evidence

__all__ = [
    "TASKS",
    "SAFETY_QUESTIONS",
    "VOCAL_DIAGNOSTIC_PROTOCOL_VERSION",
    "get_task",
    "tasks_for_ids",
    "analyze_task_audio",
    "PLANNER_VERSION",
    "PROTOCOL_VERSION",
    "TASK_REGISTRY",
    "build_uncertainty_profile",
    "explain_task_selection",
    "plan_from_song_analysis",
    "plan_precision_protocol",
    "select_diagnostic_tasks",
    "build_final_diagnostic_profile",
    "fuse_song_and_task_evidence",
    "build_personalized_qa",
    "normalize_user_concerns",
    "normalize_diagnostic_mode",
    "has_pain_safety_flag",
    "public_concern_catalog",
]
