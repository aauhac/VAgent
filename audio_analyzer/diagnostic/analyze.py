"""
diagnostic/analyze.py
---------------------
Run physiology observers + task-specific dimension evidence (protocol v1.2).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from audio_analyzer.diagnostic.evidence.compliance import check_task_compliance
from audio_analyzer.diagnostic.evidence.dynamic_swell import (
    build_dynamic_swell_dimension_evidence,
)
from audio_analyzer.diagnostic.evidence.siren import (
    build_siren_dimension_evidence,
    compute_siren_continuity_stats,
)
from audio_analyzer.diagnostic.evidence.sustain import build_sustain_dimension_evidence
from audio_analyzer.diagnostic.task_registry import TASK_REGISTRY
from audio_analyzer.features.pitch import extract_pitch_features
from audio_analyzer.physiology import (
    observe_dynamic_swell_task,
    observe_siren_task,
    observe_sustained_task,
)
from audio_analyzer.physiology import metrics as M


def _quality_ok(result: dict[str, Any]) -> bool:
    q = result.get("quality") or {}
    if q.get("status") == "fail":
        return False
    if result.get("invalid") or result.get("quality_fail"):
        return False
    return True


def _attach_normalized_siren_obs(result: dict[str, Any], pitch: dict[str, Any]) -> None:
    stats = compute_siren_continuity_stats(pitch)
    obs = list(result.get("observations") or [])
    # Keep raw count as debug; add normalized metrics
    for mid, val, unit, conf in (
        ("voiced_dropout_ratio", stats.get("voiced_dropout_ratio"), "ratio", 0.75),
        ("dropout_event_count", float(stats.get("dropout_event_count") or 0), "count", 0.7),
        ("longest_dropout_run", float(stats.get("longest_dropout_run") or 0), "frames", 0.7),
        (
            "valid_transition_frame_ratio",
            stats.get("valid_transition_frame_ratio"),
            "ratio",
            0.75,
        ),
    ):
        obs.append(
            M._metric(
                mid,
                None if val is None else float(val),
                unit=unit,
                valid=val is not None,
                confidence=conf if val is not None else 0.1,
                source_task="siren",
                measurement_condition="pitch_glide_task_normalized",
                attempts_used=[result.get("attempt") or 1],
                notes=["normalized_not_raw_frame_count"],
            )
        )
    result["observations"] = obs
    result["siren_continuity_stats"] = stats


def analyze_task_audio(
    y: np.ndarray,
    sr: int,
    *,
    task_id: str,
    attempt: int = 1,
) -> dict[str, Any]:
    pitch = extract_pitch_features(y, sr)
    if task_id in ("sustain_a", "sustain_i", "high_note_sustain_a"):
        result = observe_sustained_task(
            y,
            sr,
            task_id="sustain_a" if task_id == "high_note_sustain_a" else task_id,
            attempt=attempt,
        )
        if task_id == "high_note_sustain_a":
            result["task_id"] = "high_note_sustain_a"
    elif task_id == "siren":
        result = observe_siren_task(y, sr, attempt=attempt)
        _attach_normalized_siren_obs(result, pitch)
    elif task_id == "dynamic_swell":
        result = observe_dynamic_swell_task(y, sr, attempt=attempt)
    else:
        raise ValueError(f"unknown task_id: {task_id}")

    compliance = check_task_compliance(task_id, y, sr, pitch=pitch)
    quality_valid = _quality_ok(result)
    usable = quality_valid and bool(compliance.get("ok"))

    if task_id in ("sustain_a", "sustain_i", "high_note_sustain_a"):
        dim_ev = build_sustain_dimension_evidence(
            result, quality_valid=quality_valid, compliance_ok=bool(compliance.get("ok"))
        )
        # Task ID alone never resolves — require compliance (+ elevation when known)
        if task_id == "high_note_sustain_a" and not compliance.get("ok"):
            for _k, ev in (dim_ev or {}).items():
                if isinstance(ev, dict):
                    ev["resolution_eligible"] = False
                    ev["reason"] = ev.get("reason") or "high_note_compliance_failed"
    elif task_id == "siren":
        dim_ev = build_siren_dimension_evidence(
            result,
            pitch=pitch,
            quality_valid=quality_valid,
            compliance_ok=bool(compliance.get("ok")),
        )
    else:
        dim_ev = build_dynamic_swell_dimension_evidence(
            y, sr, quality_valid=quality_valid, compliance_ok=bool(compliance.get("ok"))
        )

    actual_coverage = sorted(
        [
            d
            for d, ev in dim_ev.items()
            if isinstance(ev, dict) and ev.get("resolution_eligible")
        ]
    )
    unresolved_from_task = sorted(
        [
            d
            for d in ((TASK_REGISTRY.get(task_id) or {}).get("covers") or [])
            if d not in actual_coverage
        ]
    )
    task_dimension_validity = {
        d: bool(isinstance(ev, dict) and ev.get("available") and ev.get("quality_valid"))
        for d, ev in dim_ev.items()
    }

    result["compliance"] = compliance
    result["dimension_evidence"] = dim_ev
    result["actual_coverage"] = actual_coverage
    result["expected_coverage"] = list((TASK_REGISTRY.get(task_id) or {}).get("covers") or [])
    result["unresolved_from_task"] = unresolved_from_task
    result["task_dimension_validity"] = task_dimension_validity
    result["task_usable"] = usable
    # Never invent mechanisms for fusion fallback
    result.setdefault("mechanisms", [])
    return result
