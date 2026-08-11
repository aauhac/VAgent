"""Siren task → register dimension evidence (normalized continuity/dropout)."""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from audio_analyzer.diagnostic.evidence.schema import empty_evidence, make_evidence, metric_value, obs_map


def compute_siren_continuity_stats(pitch: dict[str, Any] | None) -> dict[str, Any]:
    frame_f0 = (pitch or {}).get("frame_f0") or []
    f0s = [f.get("f0_hz") for f in frame_f0]
    n_frames = len(f0s)
    voiced_idx = [i for i, v in enumerate(f0s) if v is not None and v > 0]
    n_voiced = len(voiced_idx)
    dropouts = 0
    dropout_runs = []
    run = 0
    jumps_ok = []
    for i in range(1, n_frames):
        a, b = f0s[i - 1], f0s[i]
        if a is None or b is None or a <= 0 or b <= 0:
            dropouts += 1
            run += 1
            continue
        if run:
            dropout_runs.append(run)
            run = 0
        cents = abs(1200 * np.log2((b + 1e-10) / (a + 1e-10)))
        jumps_ok.append(cents < 120.0)
    if run:
        dropout_runs.append(run)

    continuity = float(np.mean(jumps_ok)) if jumps_ok else None
    denom = max(n_frames - 1, 1)
    dropout_ratio = float(dropouts) / float(denom)
    event_count = len(dropout_runs)
    longest = max(dropout_runs) if dropout_runs else 0
    span = None
    voiced_vals = [f0s[i] for i in voiced_idx]
    if len(voiced_vals) >= 8:
        span = float(1200 * np.log2((max(voiced_vals) + 1e-10) / (min(voiced_vals) + 1e-10)))
    return {
        "n_frames": n_frames,
        "n_voiced": n_voiced,
        "f0_continuity_ratio": continuity,
        "voiced_dropout_count": dropouts,  # debug raw
        "voiced_dropout_ratio": round(dropout_ratio, 4),
        "dropout_event_count": event_count,
        "longest_dropout_run": longest,
        "valid_transition_frame_ratio": continuity,
        "pitch_span_cents": None if span is None else round(span, 1),
    }


def evidence_register(
    *,
    task_result: dict[str, Any],
    continuity_stats: dict[str, Any],
    quality_valid: bool,
    compliance_ok: bool,
) -> dict[str, Any]:
    if not quality_valid:
        return empty_evidence("register", reason="quality_fail", quality_valid=False)
    if not compliance_ok:
        return empty_evidence(
            "register",
            reason="siren_compliance_fail",
            quality_valid=True,
        )

    cont = continuity_stats.get("f0_continuity_ratio")
    drop_r = continuity_stats.get("voiced_dropout_ratio")
    span = continuity_stats.get("pitch_span_cents")
    longest = int(continuity_stats.get("longest_dropout_run") or 0)
    families = {
        "f0_continuity": cont is not None,
        "normalized_dropout": drop_r is not None,
        "pitch_span": span is not None,
    }
    n = sum(1 for v in families.values() if v)
    if n < 2 or cont is None:
        return make_evidence(
            "register",
            available=False,
            family_count=n,
            evidence_families=families,
            resolution_eligible=False,
            quality_valid=True,
            reason="insufficient_register_metrics",
            confidence_source="siren_continuity",
            extra={"debug_dropout_count": continuity_stats.get("voiced_dropout_count")},
        )

    # Continuous glide with limited normalized dropout → connected register path
    connected = float(cont) >= 0.7 and float(drop_r or 1) <= 0.35 and longest <= max(8, int(0.15 * (continuity_stats.get("n_frames") or 1)))
    disrupted = float(cont) < 0.45 or float(drop_r or 0) >= 0.5 or longest >= max(12, int(0.25 * (continuity_stats.get("n_frames") or 1)))

    if connected:
        return make_evidence(
            "register",
            available=True,
            estimate=0.8,
            status="CONNECTED",
            confidence_score=0.74,
            family_count=n,
            evidence_families=families,
            evidence_mass=0.74,
            resolution_eligible=True,
            quality_valid=True,
            reason="continuous_glide_low_dropout",
            confidence_source="normalized_siren_metrics",
            extra={
                "voiced_dropout_ratio": drop_r,
                "f0_continuity_ratio": cont,
                "pitch_span_cents": span,
                "debug_dropout_count": continuity_stats.get("voiced_dropout_count"),
                "note": "continuity_not_head_chest_physiology",
            },
        )
    if disrupted:
        return make_evidence(
            "register",
            available=True,
            estimate=0.3,
            status="DISRUPTED",
            confidence_score=0.7,
            family_count=n,
            evidence_families=families,
            evidence_mass=0.7,
            resolution_eligible=True,
            quality_valid=True,
            reason="dropout_or_discontinuity",
            confidence_source="normalized_siren_metrics",
            extra={
                "voiced_dropout_ratio": drop_r,
                "f0_continuity_ratio": cont,
                "debug_dropout_count": continuity_stats.get("voiced_dropout_count"),
            },
        )
    return make_evidence(
        "register",
        available=True,
        estimate=None,
        status="INSUFFICIENT",
        confidence_score=0.4,
        family_count=n,
        evidence_families=families,
        resolution_eligible=False,
        quality_valid=True,
        reason="ambiguous_continuity",
        confidence_source="normalized_siren_metrics",
        extra={"debug_dropout_count": continuity_stats.get("voiced_dropout_count")},
    )


def build_siren_dimension_evidence(
    task_result: dict[str, Any],
    *,
    pitch: dict[str, Any] | None,
    quality_valid: bool,
    compliance_ok: bool,
) -> dict[str, dict[str, Any]]:
    stats = compute_siren_continuity_stats(pitch)
    # Prefer live pitch stats; fall back to observation metrics if present
    omap = obs_map(task_result.get("observations"))
    if stats.get("f0_continuity_ratio") is None:
        stats["f0_continuity_ratio"] = metric_value(omap, "f0_continuity_ratio")
    if stats.get("voiced_dropout_count") is None:
        stats["voiced_dropout_count"] = metric_value(omap, "voiced_dropout_count")
    return {
        "register": evidence_register(
            task_result=task_result,
            continuity_stats=stats,
            quality_valid=quality_valid,
            compliance_ok=compliance_ok,
        )
    }
