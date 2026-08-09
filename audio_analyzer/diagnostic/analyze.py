"""
diagnostic/analyze.py
---------------------
Run physiology observers for diagnostic task audio.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from audio_analyzer.physiology import (
    observe_dynamic_swell_task,
    observe_siren_task,
    observe_sustained_task,
)


def analyze_task_audio(
    y: np.ndarray,
    sr: int,
    *,
    task_id: str,
    attempt: int = 1,
) -> dict[str, Any]:
    if task_id in ("sustain_a", "sustain_i"):
        return observe_sustained_task(y, sr, task_id=task_id, attempt=attempt)
    if task_id == "siren":
        return observe_siren_task(y, sr, attempt=attempt)
    if task_id == "dynamic_swell":
        return observe_dynamic_swell_task(y, sr, attempt=attempt)
    raise ValueError(f"unknown task_id: {task_id}")
