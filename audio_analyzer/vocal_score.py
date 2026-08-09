"""Compatibility shim — primary scoring is v3; v2 helpers kept for legacy imports."""

from audio_analyzer.scoring.score_v2 import (
    clamp,
    compute_score_v2,
    score_higher_is_better,
    score_lower_is_better,
    score_target_range,
)
from audio_analyzer.scoring.score_v3 import compute_score_v3

compute_vocal_score = compute_score_v3

__all__ = [
    "compute_vocal_score",
    "compute_score_v3",
    "compute_score_v2",
    "clamp",
    "score_lower_is_better",
    "score_higher_is_better",
    "score_target_range",
]
