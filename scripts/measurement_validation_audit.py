#!/usr/bin/env python3
"""Primary rejection + four-sample regression audit (Measurement Validation v1)."""

from __future__ import annotations

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

    rid = f"mv1_{sample_id}_{path.stem}"[:48]
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
    dims = vf.get("dimensions") or {}
    coach = vf.get("coaching_decision") or {}
    effort = dims.get("vocal_effort_strain") or {}
    leak = dims.get("air_leakage_breathiness") or {}
    rough = dims.get("phonation_regularity") or {}
    eps = vf.get("episodes") or (vf.get("scientific_debug") or {}).get("episodes") or []
    effort_eps = [e for e in eps if (e.get("type") or e.get("episode_type")) in (
        "GENERAL_EFFORT",
        "HIGH_NOTE_EFFORT",
        "EXCESS_EFFORT",
    ) or "EFFORT" in str(e.get("type") or "").upper()]
    hyps = coach.get("hypotheses") or []
    effort_hyps = [
        h
        for h in hyps
        if "EFFORT" in str(h.get("id") or "").upper()
    ]
    primary = coach.get("primary_bottleneck") or coach.get("primary")
    return {
        "sample": sample_id,
        "engine_version": vf.get("engine_version"),
        "effort_status": effort.get("status"),
        "effort_score": (effort.get("profile") or {}).get("effort_score"),
        "breathiness": leak.get("status"),
        "roughness": rough.get("status"),
        "rough_hits": (rough.get("roughness_coverage") or {}).get("positive"),
        "rejected_tracker_artifact": (rough.get("roughness_coverage") or {}).get(
            "rejected_tracker_artifact"
        ),
        "effort_episode_count": len(effort_eps),
        "effort_hypotheses": [
            {
                "id": h.get("id"),
                "confidence_label": h.get("confidence_label"),
                "n_episodes": len(h.get("supporting_episode_ids") or []),
                "eligibility": h.get("eligibility"),
            }
            for h in effort_hyps
        ],
        "primary_id": (primary or {}).get("id") if isinstance(primary, dict) else primary,
        "primary_rejection_trace": coach.get("primary_rejection_trace") or [],
        "vocal_type": (vf.get("vocal_type_profile") or {}).get("version")
        or (vf.get("vocal_type_profile") or {}).get("type_version"),
    }


def main() -> int:
    out = ROOT / "runtime" / "audits" / "diagnostic_v12"
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for label, path in SAMPLES:
        if not path.exists():
            print(f"MISSING {label}")
            continue
        print(f"\n=== {label} ===")
        row = _analyze(path, out, label)
        rows.append(row)
        print(
            f"effort={row['effort_score']} ({row['effort_status']}) "
            f"breath={row['breathiness']} rough={row['roughness']} "
            f"primary={row['primary_id']} episodes={row['effort_episode_count']}"
        )
        for r in row["primary_rejection_trace"][:8]:
            print(f"  reject {r.get('id')}: {r.get('reason')}")
        (out / f"primary_trace_{label}.json").write_text(
            json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    (out / "four_sample_regression.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # Focus dump for 목잡이
    mok = next((r for r in rows if r["sample"] == "목잡이"), None)
    if mok:
        (out / "primary_rejection_trace.json").write_text(
            json.dumps(mok, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
