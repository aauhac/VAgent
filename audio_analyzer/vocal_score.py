"""Compatibility shim — v2 scoring lives in audio_analyzer.scoring."""

from audio_analyzer.scoring.score_v2 import (
    clamp,
    compute_score_v2,
    score_higher_is_better,
    score_lower_is_better,
    score_target_range,
)

# Legacy name
compute_vocal_score = compute_score_v2

__all__ = [
    "compute_vocal_score",
    "compute_score_v2",
    "clamp",
    "score_lower_is_better",
    "score_higher_is_better",
    "score_target_range",
]
