"""Scoring package — v3 primary, v2 retained for migration/debug."""

from .score_v2 import compute_score_v2
from .score_v3 import compute_score_v3

__all__ = ["compute_score_v3", "compute_score_v2"]
