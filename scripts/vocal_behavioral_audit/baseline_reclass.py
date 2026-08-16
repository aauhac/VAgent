# -*- coding: utf-8 -*-
"""Reclassify baseline audit artifacts with current claim/collapse classifiers."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Optional

from scripts.vocal_behavioral_audit.artifacts import write_json
from scripts.vocal_behavioral_audit.claim_lint import (
    classify_claim_spans,
    evaluate_claim_against_axes,
)
from scripts.vocal_behavioral_audit.detectors import generic_collapse_pairs


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def reclassify_claims_from_singletons(singletons: list[dict[str, Any]]) -> dict[str, Any]:
    class_counts: Counter = Counter()
    traces: list[dict[str, Any]] = []
    for r in singletons:
        axes = r.get("canonical_axes") or {}
        blobs = [
            str((r.get("qa") or {}).get("answer") or ""),
            str(((r.get("qa") or {}).get("prescription") or {}).get("instruction") or ""),
            str(r.get("answer_summary") or ""),
        ]
        for blob in blobs:
            for span in classify_claim_spans(blob):
                evaluated = evaluate_claim_against_axes(span, axes)
                class_counts[str(evaluated.get("classification"))] += 1
                traces.append(
                    {
                        "audio": r.get("audio_id"),
                        "concern": r.get("concern_id"),
                        "classification": evaluated.get("classification"),
                        "detail": evaluated.get("detail"),
                        "axis": evaluated.get("axis"),
                        "claimed_state": evaluated.get("claimed_state"),
                        "canonical_value": evaluated.get("canonical_value"),
                        "sentence": evaluated.get("sentence"),
                    }
                )
    return {
        "classifier": "claim_lint_v1",
        "counts": dict(class_counts),
        "true_unsupported": int(class_counts.get("TRUE_POSITIVE", 0)),
        "false_positive_lint": int(class_counts.get("FALSE_POSITIVE_LINT", 0)),
        "trace_count": len(traces),
        "traces_sample": traces[:200],
    }


def reclassify_collapse_from_singletons(singletons: list[dict[str, Any]]) -> dict[str, Any]:
    rows = generic_collapse_pairs(singletons, threshold=0.88)
    counts = Counter(r.get("classification") for r in rows)
    return {
        "classifier": "generic_collapse_pairs_v_remediation",
        "counts": dict(counts),
        "expected": int(counts.get("EXPECTED_SHARED_PROTOCOL", 0)),
        "over_shared": int(counts.get("OVER_SHARED_PRESCRIPTION", 0)),
        "wrong": int(counts.get("WRONG_GENERIC_COLLAPSE", 0)),
        "pair_count": len(rows),
    }


def reclassify_baseline_dir(
    baseline_dir: Path,
    *,
    output_dir: Path,
    after_summary: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Apply current classifiers to baseline singleton artifacts (no production re-run)."""
    singles = _load_jsonl(baseline_dir / "concern_singletons.jsonl")
    # Some baselines may only have summary — still produce empty-safe output
    claims = reclassify_claims_from_singletons(singles)
    collapse = reclassify_collapse_from_singletons(singles)

    write_json(output_dir / "baseline_reclassified_claims.json", claims)
    write_json(output_dir / "baseline_reclassified_collapse.json", collapse)

    after_claims = (after_summary or {}).get("unsupported_claim_classes") or {}
    after_collapse = (after_summary or {}).get("collapse_classes") or {}
    comparison = {
        "apples_to_apples": True,
        "claim_classifier": "claim_lint_v1",
        "collapse_classifier": "generic_collapse_pairs_v_remediation",
        "baseline_singletons_n": len(singles),
        "claims": {
            "baseline": claims.get("counts"),
            "baseline_true": claims.get("true_unsupported"),
            "baseline_false_lint": claims.get("false_positive_lint"),
            "after": after_claims,
            "after_true": (after_summary or {}).get("true_unsupported_acoustic_claims"),
        },
        "collapse": {
            "baseline_expected": collapse.get("expected"),
            "baseline_over_shared": collapse.get("over_shared"),
            "baseline_wrong": collapse.get("wrong"),
            "after_expected": after_collapse.get("EXPECTED_SHARED_PROTOCOL"),
            "after_over_shared": after_collapse.get("OVER_SHARED_PRESCRIPTION"),
            "after_wrong": after_collapse.get("WRONG_GENERIC_COLLAPSE"),
        },
        "note": (
            "Baseline raw UNSUPPORTED count (282) is not comparable; "
            "use reclassified TRUE/FALSE_LINT and collapse classes only."
        ),
    }
    write_json(output_dir / "apples_to_apples_comparison.json", comparison)
    return comparison
