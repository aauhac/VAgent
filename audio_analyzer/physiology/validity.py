"""
physiology/validity.py
----------------------
Metric Validity Gate — invalid → unknown, never low skill.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np


def sustained_vowel_conditions(
    y: np.ndarray,
    sr: int,
    *,
    pitch_features: dict[str, Any],
    quality: dict[str, Any],
    min_voiced_sec: float = 1.5,
    max_residual_std_for_perturbation: float = 25.0,
) -> dict[str, Any]:
    """Evaluate whether sustained-vowel metrics are valid."""
    reasons: list[str] = []
    ok = True
    if quality.get("status") == "fail":
        ok = False
        reasons.append("quality_fail")
    if "CLIPPING" in (quality.get("codes") or []):
        ok = False
        reasons.append("clipping")
    voiced = float(pitch_features.get("voiced_ratio") or 0.0)
    dur = len(y) / max(sr, 1)
    voiced_sec = voiced * dur
    if voiced_sec < min_voiced_sec:
        ok = False
        reasons.append("insufficient_voiced")
    f0_mean = pitch_features.get("f0_mean_hz")
    if f0_mean is None:
        ok = False
        reasons.append("no_f0")
    return {
        "ok": ok,
        "reasons": reasons,
        "voiced_sec": voiced_sec,
        "f0_mean_hz": f0_mean,
        "max_residual_std_for_perturbation": max_residual_std_for_perturbation,
    }


def perturbation_allowed(
    residual_std_cents: Optional[float],
    vibrato_available: bool,
    conditions: dict[str, Any],
    *,
    task_id: Optional[str] = None,
) -> tuple[bool, list[str]]:
    """
    Strict gate for frame-F0 / window amplitude perturbation proxies.

    Forbidden tasks: song, siren, dynamic_swell (transition / intensity change).
    """
    notes: list[str] = []
    if task_id and task_id not in ("sustain_a", "sustain_i"):
        notes.append("task_not_standardized_sustained_vowel")
        return False, notes
    if not conditions.get("ok"):
        return False, list(conditions.get("reasons") or [])
    if vibrato_available:
        notes.append("regular_vibrato_present")
        return False, notes
    max_res = conditions.get("max_residual_std_for_perturbation", 25.0)
    if residual_std_cents is not None and residual_std_cents > max_res:
        notes.append("unstable_local_f0")
        return False, notes
    if (conditions.get("voiced_sec") or 0) < 1.5:
        notes.append("insufficient_voiced_for_perturbation")
        return False, notes
    notes.append("proxy_not_clinical_cycle_perturbation")
    return True, notes
