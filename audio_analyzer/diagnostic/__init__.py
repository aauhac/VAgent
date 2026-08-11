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
    select_diagnostic_tasks,
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
    "select_diagnostic_tasks",
    "build_final_diagnostic_profile",
    "fuse_song_and_task_evidence",
]
