#!/usr/bin/env python3
"""Roughness precision audit for controlled samples (v2.9).

Prints per-positive root-cause fields BEFORE relying on threshold retunes.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SAMPLES = [
    ("편하게", ROOT / "편하게.m4a"),
    ("목잡이", ROOT / "목잡이.m4a"),
    ("호흡많고헤드", ROOT / "호흡많고헤드.m4a"),
    ("편안세게", ROOT / "편안세게.m4a"),
]


def _analyze(path: Path, out_dir: Path, sample_id: str) -> dict[str, Any]:
    from audio_analyzer.pipeline import analyze_audio
    from audio_analyzer.vocal_evidence.phonation_quality import (
        classify_breathy_segment,
        classify_rough_segment,
        disambiguate_breathy_vs_rough,
    )

    rid = f"rg29_{sample_id}_{path.stem}"[:48]
    result = analyze_audio(
        str(path),
        output_dir=str(out_dir / "runs"),
        recording_id=rid,
        separate=False,
        analysis_mode="FUNCTIONAL",
        input_mode="VOCAL_ONLY",
        build_preview=False,
    )
    vf = result.get("vocal_function_profile") or {}
    segs = (vf.get("scientific_debug") or {}).get("segments") or []
    dims = vf.get("dimensions") or {}
    rough = dims.get("phonation_regularity") or {}
    positives = []
    for i, s in enumerate(segs):
        c = classify_rough_segment(s)
        if c.get("verdict") != "POSITIVE":
            continue
        obs = s.get("observations") or {}
        art = obs.get("f0_tracker_artifact") or {}
        fam = c.get("families") or {}
        positives.append(
            {
                "i": i,
                "start": s.get("start_sec") or s.get("start"),
                "end": s.get("end_sec") or s.get("end"),
                "periodicity_loss": fam.get("periodicity_loss"),
                "irregularity": fam.get("irregularity"),
                "dropout": fam.get("dropout"),
                "raw_perturbation": obs.get("f0_frame_period_perturbation_proxy_percent"),
                "periodicity_db": obs.get("periodicity_primary_db"),
                "f0_confidence": obs.get("f0_confidence") or obs.get("pitch_confidence"),
                "voiced_ratio": s.get("voiced_ratio"),
                "pitch_frame_count": obs.get("pitch_frame_count") or art.get("n_frames"),
                "octave_jump_ratio": obs.get("f0_octave_jump_ratio"),
                "tracker_artifact_candidate": fam.get("tracker_artifact_suspect"),
                "vocal_presence": (s.get("vocal_evidence") or {}).get("vocal_dominance"),
                "vocal_specificity": (s.get("vocal_evidence") or {}).get("vocal_specific"),
                "breathiness_verdict": classify_breathy_segment(s).get("verdict"),
                "roughness_verdict": c.get("verdict"),
                "reason": c.get("reason"),
                "roughness_score": c.get("roughness_score"),
                "disambiguation": disambiguate_breathy_vs_rough(s).get("label"),
            }
        )
    return {
        "sample": sample_id,
        "path": str(path),
        "engine_version": vf.get("engine_version"),
        "status": rough.get("status"),
        "rough_hits": len(positives),
        "roughness_coverage": rough.get("roughness_coverage"),
        "roughness_persistence": rough.get("roughness_persistence"),
        "roughness_score": rough.get("roughness_score"),
        "roughness_confidence": rough.get("roughness_confidence"),
        "positives": positives,
        "effort": (dims.get("vocal_effort_strain") or {}).get("status"),
        "effort_score": ((dims.get("vocal_effort_strain") or {}).get("profile") or {}).get(
            "score"
        ),
        "breathiness": (dims.get("air_leakage_breathiness") or {}).get("status"),
        "primary": (
            ((vf.get("coaching_decision") or {}).get("primary") or {}).get("id")
            or (vf.get("coaching_decision") or {}).get("primary_bottleneck_id")
            or "none"
        ),
    }


def main() -> int:
    out = ROOT / "runtime" / "audits" / "roughness_v29"
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for label, path in SAMPLES:
        if not path.exists():
            print(f"MISSING {label}: {path}")
            continue
        print(f"\n=== {label} ===")
        summary = _analyze(path, out, label)
        rows.append(summary)
        print(
            f"hits={summary['rough_hits']} status={summary['status']} "
            f"persist={summary.get('roughness_persistence')} "
            f"effort={summary.get('effort_score')} breath={summary.get('breathiness')}"
        )
        for p in summary["positives"]:
            print(
                f"  [{p['i']}] {p['start']}-{p['end']} reason={p['reason']} "
                f"art={p['tracker_artifact_candidate']} pert={p['raw_perturbation']} "
                f"oct={p['octave_jump_ratio']} breath={p['breathiness_verdict']}"
            )
        (out / f"{label}_rough.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    (out / "summary.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (out / "summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "sample",
                "rough_hits",
                "status",
                "n_events",
                "effort_score",
                "breathiness",
                "primary",
            ],
        )
        w.writeheader()
        for r in rows:
            pers = r.get("roughness_persistence") or {}
            w.writerow(
                {
                    "sample": r["sample"],
                    "rough_hits": r["rough_hits"],
                    "status": r["status"],
                    "n_events": pers.get("n_events"),
                    "effort_score": r.get("effort_score"),
                    "breathiness": r.get("breathiness"),
                    "primary": r.get("primary"),
                }
            )
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
