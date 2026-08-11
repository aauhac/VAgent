"""Contact vs effort evidence flags (independent axes).

v2.7: implementation lives in effort_contact.py; this module re-exports
legacy names used across the engine.
"""

from __future__ import annotations

from typing import Any

from audio_analyzer.vocal_function.evidence.effort_contact import (
    contact_direction_score,
    contact_evidence_packet,
    contact_family_availability,
    contact_multi_family_fallback_ok,
    effort_evidence_packet,
    effort_family_hits,
    effort_like,
    effort_score,
    effort_secondary_signs,
    firmer_like,
    gif_usable,
    lighter_like,
)


def contact_flags(seg: dict[str, Any]) -> dict[str, bool]:
    """Legacy presence flags (not directional)."""
    avail = contact_family_availability(seg)
    obs = seg.get("observations") or {}
    period = obs.get("periodicity_primary_db")
    return {
        "glottal_flow": avail["glottal_source"],
        "harmonic": avail["harmonic"],
        "periodicity": period is not None and period > 0,
        "spectral": avail["spectral"],
    }


def leakage_like(seg: dict[str, Any]) -> bool:
    """Legacy boolean — prefer classify_breathy_segment for fusion."""
    from audio_analyzer.vocal_evidence.phonation_quality import classify_breathy_segment

    return classify_breathy_segment(seg).get("verdict") == "POSITIVE"


def rough_like(seg: dict[str, Any]) -> bool:
    from audio_analyzer.vocal_evidence.phonation_quality import classify_rough_segment

    return classify_rough_segment(seg).get("verdict") == "POSITIVE"


__all__ = [
    "contact_flags",
    "contact_direction_score",
    "contact_evidence_packet",
    "contact_family_availability",
    "contact_multi_family_fallback_ok",
    "effort_evidence_packet",
    "effort_family_hits",
    "effort_like",
    "effort_score",
    "effort_secondary_signs",
    "firmer_like",
    "gif_usable",
    "leakage_like",
    "lighter_like",
    "rough_like",
]
