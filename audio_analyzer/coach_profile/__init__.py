"""Coach Profile package — Vocal Type / Head–Chest Balance."""

from .engine import (
    build_vocal_type_public,
    classify_vocal_type_resolution_state,
    compute_vocal_type_profile,
)
from .public_presentation import (
    apply_public_vocal_type_copy,
    public_vocal_type_label,
)

__all__ = [
    "compute_vocal_type_profile",
    "build_vocal_type_public",
    "classify_vocal_type_resolution_state",
    "apply_public_vocal_type_copy",
    "public_vocal_type_label",
]
