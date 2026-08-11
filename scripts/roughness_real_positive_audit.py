#!/usr/bin/env python3
"""Roughness real-positive readiness audit (no threshold retune).

Compares clean controlled anchors vs optional --rough path.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def summarize(path: Path, out_dir: Path, label: str) -> dict:
    from audio_analyzer.pipeline import analyze_audio
    from audio_analyzer.vocal_evidence.phonation_quality import classify_rough_segment

    rid = f"rr_{label}_{path.stem}"[:48]
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
    rough = (vf.get("dimensions") or {}).get("phonation_regularity") or {}
    positives = [classify_rough_segment(s) for s in segs]
    n_pos = sum(1 for c in positives if c.get("verdict") == "POSITIVE")
    return {
        "label": label,
        "path": str(path),
        "status": rough.get("status"),
        "positive_hits": n_pos,
        "coverage": rough.get("roughness_coverage"),
        "persistence": rough.get("roughness_persistence"),
        "note": "intentional_fry_distortion_is_acoustic_pattern_not_disease",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rough", type=str, default="", help="optional real rough/fry file")
    args = ap.parse_args()
    out = ROOT / "runtime" / "audits" / "diagnostic_v12"
    out.mkdir(parents=True, exist_ok=True)
    clean = []
    for name in ("편하게", "목잡이", "호흡많고헤드", "편안세게"):
        p = ROOT / f"{name}.m4a"
        if p.exists():
            clean.append(summarize(p, out, f"clean_{name}"))
    rough = None
    if args.rough:
        rp = Path(args.rough)
        if rp.exists():
            rough = summarize(rp, out, "real_rough")
    payload = {
        "clean_anchors": clean,
        "real_rough": rough,
        "acceptance": {
            "clean_false_positive_low": all((c.get("positive_hits") or 0) == 0 for c in clean),
            "real_rough_ready": rough is not None,
            "retune_applied": False,
        },
    }
    path = out / "roughness_real_positive_readiness.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload["acceptance"], indent=2))
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
