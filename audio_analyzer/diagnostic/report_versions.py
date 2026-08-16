"""Explicit report/QA logic versions for stale-report detection.

These are presentation/composition versions. They must never retune
acoustic thresholds or rewrite historical production reports.
"""

from __future__ import annotations

from audio_analyzer.diagnostic.goal_planner import GOAL_VERSION
from audio_analyzer.diagnostic.coaching_protocol import PROTOCOL_VERSION as COACHING_PROTOCOL_VERSION

QA_GUIDANCE_VERSION = "precision-qa-coaching-ux-v9"
REPORT_LOGIC_VERSION = "precision-report-v10"

__all__ = [
    "QA_GUIDANCE_VERSION",
    "GOAL_VERSION",
    "REPORT_LOGIC_VERSION",
    "COACHING_PROTOCOL_VERSION",
]
