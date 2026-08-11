#!/usr/bin/env python3
"""Roughness FP root-cause audit on controlled samples (Track A)."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from audio_analyzer.vocal_evidence.phonation_quality import (  # noqa: E402
    classify_rough_segment,
    disambiguate_breathy_vs_rough,
)


def audit_analysis(analysis_path: Path, sample_id: str) -> dict:
    d = json.loads(analysis_path.read_text(encoding="utf-8"))
    vf = d.get("vocal_function_profile") or {}
    segs = (vf.get("scientific_debug") or {}).get("segments") or []
    rows = []
    for s in segs:
        c = classify_rough_segment(s)
        obs = s.get("observations") or {}
        art = obs.get("f0_tracker_artifact") or {}
        dis = disambiguate_breathy_vs_rough(s)
        rows.append(
            {
                "start": s.get("start_sec"),
                "end": s.get("end_sec"),
                "verdict": c.get("verdict"),
                "reason": c.get("reason"),
                "periodicity_db": obs.get("periodicity_primary_db"),
                "perturb": obs.get("f0_frame_period_perturbation_proxy_percent"),
                "dropout": obs.get("f0_dropout_ratio"),
                "octave_jump": obs.get("f0_octave_jump_ratio"),
                "n_voiced": art.get("n_voiced"),
                "n_frames": art.get("n_frames"),
                "octave_jumps": art.get("octave_jumps"),
                "art_suspect": art.get("suspect"),
                "voiced_ratio": s.get("voiced_ratio"),
                "intensity_db": obs.get("intensity_db"),
                "families": c.get("families"),
                "disambig": dis.get("label"),
                "rough_score": c.get("roughness_score"),
                "rough_conf": c.get("roughness_confidence"),
            }
        )
    pos = [r for r in rows if r["verdict"] == "POSITIVE"]
    return {
        "sample_id": sample_id,
        "path": str(analysis_path),
        "n_segments": len(segs),
        "verdicts": dict(Counter(r["verdict"] for r in rows)),
        "reasons": dict(Counter(r["reason"] for r in rows)),
        "n_positive": len(pos),
        "positives": pos,
        "engine_version": vf.get("engine_version"),
    }


def main() -> int:
    runs = ROOT / "runtime" / "audits" / "contact_effort" / "runs"
    mapping = {
        "comfortable": "ce_comfortable_",
        "squeezed": "ce_squeezed_",
        "breathy_head": "ce_breathy_head_",
        "firm_mix": "ce_firm_mix_",
    }
    out_dir = ROOT / "runtime" / "audits" / "roughness_v29"
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {}
    for sid, prefix in mapping.items():
        paths = sorted(runs.glob(f"{prefix}*/analysis.json"))
        if not paths:
            print(sid, "NO analysis.json")
            continue
        a = audit_analysis(paths[0], sid)
        report[sid] = a
        print("=" * 60)
        print(sid, "n_pos", a["n_positive"], "verdicts", a["verdicts"])
        print("reasons", a["reasons"])
        for p in a["positives"]:
            print(
                f"  {p['start']}-{p['end']} reason={p['reason']} "
                f"per={p['periodicity_db']} pert={p['perturb']} drop={p['dropout']} "
                f"oct={p['octave_jump']} n_v={p['n_voiced']}/{p['n_frames']} "
                f"art={p['art_suspect']} dis={p['disambig']}"
            )
    path = out_dir / "root_cause_before.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
