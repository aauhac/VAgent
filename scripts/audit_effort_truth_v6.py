"""Effort truth audit — dump raw vs canonical effort without retuning thresholds.

Usage:
  python -m scripts.audit_effort_truth_v6
  python -m scripts.audit_effort_truth_v6 --fixture pushed
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from audio_analyzer.diagnostic.song_evidence import build_song_evidence_snapshot
from audio_analyzer.vocal_function.derived.effort_assessment import build_effort_assessment


def _dim(
    *,
    status: str,
    peak: float,
    mean: float,
    hits: int,
    core: int,
    support: int,
    persistent: int,
    conf: str = "medium",
):
    return {
        "dimension_id": "vocal_effort_strain",
        "status": status,
        "confidence_label": conf,
        "continuum_0_to_1": peak,
        "profile": {
            "effort_score": peak,
            "mean_segment_effort_score": mean,
            "hit_segments": hits,
            "core_family_count": core,
            "support_family_count": support,
            "persistent_segments": persistent,
            "recovery_cost": persistent,
        },
    }


def _pack(label: str, dim: dict, register: str = "DISRUPTED", contact: float = 0.72):
    assessment = build_effort_assessment(dim, valid_segment_count=12)
    song = {
        "vocal_function_profile": {
            "effort_assessment": assessment,
            "dimensions": {
                "vocal_effort_strain": dim,
                "glottal_contact_profile": {
                    "status": "OBSERVED",
                    "continuum_0_to_1": contact,
                },
                "phonation_regularity": {"status": "UNSTABLE"},
            },
            "vocal_type_profile": {
                "register_strategy": {"status": register},
                "canonical_register": {"status": register},
            },
        }
    }
    snap = build_song_evidence_snapshot(song)
    root = "UNKNOWN"
    raw_status = str(dim.get("status") or "").upper()
    canon = str((snap.get("effort") or {}).get("level") or "").upper()
    if raw_status in ("UNKNOWN", "UNAVAILABLE", "AMBIGUOUS") and canon == "LOW":
        root = "PRESENTATION"
    elif assessment.get("global_severity") == "LOW" and int(assessment.get("hit_segments") or 0) == 0:
        root = "DETECTOR"
    elif str(assessment.get("localized_peak_severity") or "").upper() in ("HIGH", "MODERATE") and canon == "LOW":
        root = "AGGREGATION"
    elif canon == str(assessment.get("global_severity") or "").upper():
        root = "NONE" if canon != "LOW" or raw_status == "LOW" else "DETECTOR"

    return {
        "label": label,
        "raw_effort_dim": {
            "status": dim.get("status"),
            "continuum_0_to_1": dim.get("continuum_0_to_1"),
            "effort_score": (dim.get("profile") or {}).get("effort_score"),
            "peak_event_score": assessment.get("peak_event_score"),
            "mean_segment_effort_score": (dim.get("profile") or {}).get("mean_segment_effort_score"),
            "hit_segments": assessment.get("hit_segments"),
            "hit_ratio": assessment.get("hit_ratio"),
            "core_family_count": assessment.get("core_family_count"),
            "support_family_count": assessment.get("support_family_count"),
            "persistent_segments": assessment.get("persistent_segments"),
            "localized_episode_count": assessment.get("localized_episode_count"),
            "confidence_label": assessment.get("confidence_label"),
        },
        "effort_assessment": {
            "global_severity": assessment.get("global_severity"),
            "localized_peak_severity": assessment.get("localized_peak_severity"),
            "high_note_severity": assessment.get("high_note_severity"),
            "label": assessment.get("label"),
            "strength_eligible": assessment.get("strength_eligible"),
            "status": assessment.get("status"),
        },
        "canonical_effort": snap.get("effort"),
        "canonical_register": snap.get("register"),
        "canonical_contact": snap.get("contact"),
        "canonical_stability": snap.get("stability"),
        "key_features": snap.get("key_features"),
        "root_cause_if_mismatch": root,
        "threshold_changed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", default="paired", choices=("paired", "pushed", "relaxed", "unknown"))
    args = parser.parse_args()

    cases = []
    if args.fixture in ("paired", "relaxed"):
        cases.append(
            _pack(
                "RELAXED",
                _dim(status="LOW", peak=0.08, mean=0.05, hits=0, core=0, support=0, persistent=0),
                register="CONNECTED",
                contact=0.5,
            )
        )
    if args.fixture in ("paired", "pushed"):
        # Intentional push + register fail: if detector sees no hits → DETECTOR miss
        cases.append(
            _pack(
                "PUSHED_REGISTER_FAIL_DETECTOR_LOW",
                _dim(status="LOW", peak=0.12, mean=0.1, hits=0, core=0, support=0, persistent=0),
                register="DISRUPTED",
                contact=0.78,
            )
        )
        cases.append(
            _pack(
                "PUSHED_WITH_RAW_ELEVATED",
                _dim(status="OCCASIONAL", peak=0.62, mean=0.22, hits=2, core=2, support=1, persistent=1),
                register="DISRUPTED",
                contact=0.78,
            )
        )
    if args.fixture == "unknown":
        cases.append(
            _pack(
                "UNKNOWN_STATUS",
                _dim(status="UNKNOWN", peak=0.0, mean=0.0, hits=0, core=0, support=0, persistent=0, conf="low"),
                register="PARTIAL",
            )
        )

    out = {
        "audit": "effort-truth-v6",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "threshold_changed": False,
        "cases": cases,
        "notes": [
            "UNKNOWN must not present as LOW strength.",
            "If PUSHED_REGISTER_FAIL_DETECTOR_LOW shows LOW with hit_segments=0, classify DETECTOR.",
            "Do not retune thresholds in this audit.",
        ],
    }
    path = Path(f".effort_truth_audit_v6_{int(datetime.now().timestamp() * 1000)}.json")
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"wrote": str(path), "cases": [c["label"] for c in cases]}, ensure_ascii=False))
    print(path.read_text(encoding="utf-8")[:2000])


if __name__ == "__main__":
    main()
