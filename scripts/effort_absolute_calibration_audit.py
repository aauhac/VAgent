#!/usr/bin/env python3
"""Effort absolute calibration audit (v2.12).

Usage:
  python scripts/effort_absolute_calibration_audit.py
  python scripts/effort_absolute_calibration_audit.py --sample 목잡이
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ANCHORS = {
    "편하게": ROOT / "편하게.m4a",
    "목잡이": ROOT / "목잡이.m4a",
    "호흡많고헤드": ROOT / "호흡많고헤드.m4a",
    "편안세게": ROOT / "편안세게.m4a",
}


def _analyze(path: Path, sample_id: str) -> dict[str, Any]:
    from audio_analyzer.pipeline import analyze_audio
    from audio_analyzer.vocal_function.derived.effort_assessment import (
        check_effort_report_consistency,
    )

    rid = f"e212_{sample_id}"[:48]
    result = analyze_audio(
        str(path),
        output_dir=str(ROOT / "_tmp_effort_audit" / "runs"),
        recording_id=rid,
        separate=False,
        analysis_mode="FUNCTIONAL",
        input_mode="VOCAL_ONLY",
        build_preview=False,
    )
    vf = result.get("vocal_function_profile") or {}
    dims = vf.get("dimensions") or {}
    effort = dims.get("vocal_effort_strain") or {}
    contact = dims.get("glottal_contact_profile") or {}
    leak = dims.get("air_leakage_breathiness") or {}
    rough = dims.get("phonation_regularity") or {}
    coach = vf.get("coaching_decision") or {}
    primary = coach.get("primary_bottleneck") or coach.get("primary") or {}
    assessment = vf.get("effort_assessment") or effort.get("effort_assessment") or {}
    issues = check_effort_report_consistency(
        assessment=assessment,
        coaching_decision=coach,
        dimensions=dims,
    )
    vq_rough = ((result.get("vocal_quality_profile") or {}).get("dimensions") or {}).get(
        "rough_like"
    ) or {}
    cov = rough.get("roughness_coverage") or (vf.get("scientific_debug") or {}).get(
        "roughness_coverage"
    ) or {}

    consistency = "PASS" if not any(i.get("severity") == "WARN" for i in issues) else "FAIL"
    return {
        "sample": sample_id,
        "effort_status": effort.get("status"),
        "effort_raw_peak": (effort.get("profile") or {}).get("effort_score"),
        "effort_mean": (effort.get("profile") or {}).get("mean_segment_effort_score"),
        "hits": (effort.get("profile") or {}).get("hit_segments"),
        "core": (effort.get("profile") or {}).get("core_family_count"),
        "support": (effort.get("profile") or {}).get("support_family_count"),
        "persistent": (effort.get("profile") or {}).get("persistent_segments"),
        "prevalence": effort.get("prevalence"),
        "canonical_severity": assessment.get("global_severity"),
        "profile_label": assessment.get("label"),
        "display_continuum": assessment.get("display_continuum"),
        "primary": primary.get("id"),
        "primary_title": primary.get("user_title"),
        "consistency": consistency,
        "consistency_issues": issues,
        "contact_continuum": contact.get("continuum_0_to_1"),
        "breathiness": leak.get("status"),
        "vf_roughness": rough.get("status"),
        "vf_rough_positive": cov.get("positive"),
        "vf_rough_rejected_artifact": cov.get("rejected_tracker_artifact"),
        "vq_rough_status": vq_rough.get("status"),
        "vq_rough_summary": vq_rough.get("summary"),
        "context_note": assessment.get("context_note"),
        "engine_version": vf.get("engine_version"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", default=None)
    ap.add_argument("--json-out", default=str(ROOT / "_tmp_effort_audit" / "direction_table.json"))
    args = ap.parse_args()
    names = [args.sample] if args.sample else list(ANCHORS.keys())
    rows = []
    for name in names:
        path = ANCHORS.get(name) or Path(name)
        if not path.exists():
            print(f"NOT AVAILABLE: {name} ({path})")
            continue
        print(f"\n=== {name} ===")
        row = _analyze(path, name)
        rows.append(row)
        for k, v in row.items():
            if k == "consistency_issues":
                continue
            print(f"  {k}: {v}")
        if row["consistency_issues"]:
            print("  issues:", row["consistency_issues"])

    out = Path(args.json_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {out}")

    # Ordinal check when all four present
    by = {r["sample"]: r for r in rows}
    if all(k in by for k in ("목잡이", "편하게", "편안세게", "호흡많고헤드")):
        def score(r):
            order = {"LOW": 0, "MILD": 1, "MODERATE": 2, "HIGH": 3}
            return (order.get(r["canonical_severity"] or "LOW", 0), float(r["effort_raw_peak"] or 0))

        ok = (
            score(by["목잡이"]) > score(by["편하게"])
            and score(by["목잡이"]) > score(by["편안세게"])
            and score(by["목잡이"]) > score(by["호흡많고헤드"])
        )
        print("\nORDINAL effort(목잡이) > others:", "PASS" if ok else "FAIL")
        print(
            "ABSOLUTE:",
            {
                k: (by[k]["canonical_severity"], by[k]["profile_label"])
                for k in ("편하게", "편안세게", "호흡많고헤드", "목잡이")
            },
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
