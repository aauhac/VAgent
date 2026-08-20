"""Coach Profile package — Vocal Type / Head–Chest Balance."""

from .engine import (
    build_vocal_type_public,
    classify_vocal_type_resolution_state,
    compute_vocal_type_profile,
)

__all__ = [
    "compute_vocal_type_profile",
    "build_vocal_type_public",
    "classify_vocal_type_resolution_state",
]
