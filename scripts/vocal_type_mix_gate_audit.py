#!/usr/bin/env python3
"""v2.13 Vocal Type semantic audit — balance vs Mix separation.

Usage:
  python scripts/vocal_type_mix_gate_audit.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ANCHORS = {
    "편하게": ROOT / "편하게.m4a",
    "목잡이": ROOT / "목잡이.m4a",
    "호흡많고헤드": ROOT / "호흡많고헤드.m4a",
    "편안세게": ROOT / "편안세게.m4a",
}


def analyze(path: Path, sample_id: str) -> dict:
    from audio_analyzer.pipeline import analyze_audio

    r = analyze_audio(
        str(path),
        output_dir=str(ROOT / "_tmp_effort_audit" / "runs"),
        recording_id=f"vt213_{sample_id}"[:40],
        separate=False,
        analysis_mode="FUNCTIONAL",
        input_mode="VOCAL_ONLY",
        build_preview=False,
    )
    vf = r.get("vocal_function_profile") or {}
    vt = vf.get("vocal_type_profile") or {}
    hc = vt.get("head_chest") or {}
    sb = vt.get("source_balance") or {}
    rs = vt.get("register_strategy") or {}
    br = vt.get("bridge") or {}
    ea = vf.get("effort_assessment") or {}
    return {
        "sample": sample_id,
        "chest": hc.get("chest_ratio") or sb.get("chest_percent"),
        "head": hc.get("head_ratio") or sb.get("head_percent"),
        "source_balance": sb.get("balance_class"),
        "source_label": sb.get("label") or vt.get("display_name"),
        "register_status": rs.get("status"),
        "mix_evidence": rs.get("mix_evidence"),
        "register_title": rs.get("title"),
        "bridge_type": br.get("type"),
        "bridge_score": br.get("score"),
        "register_sufficiency": br.get("register_sufficiency"),
        "n_opportunities": br.get("n_transition_opportunities"),
        "break_prevalence": br.get("break_prevalence"),
        "split_eligible": (br.get("split_eligibility") or {}).get("eligible"),
        "type_id": vt.get("type_id"),
        "display_name": vt.get("display_name"),
        "description": vt.get("description"),
        "modifiers": vt.get("modifiers"),
        "effort": ea.get("severity"),
        "has_compound_firm_mix": "단단한 믹스" in str(vt.get("display_name") or ""),
        "has_mix_in_title": "믹스" in str(vt.get("display_name") or ""),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", default=None)
    args = ap.parse_args()
    names = [args.sample] if args.sample else list(ANCHORS)
    rows = []
    for name in names:
        path = ANCHORS.get(name)
        if not path or not path.exists():
            print(f"NOT AVAILABLE: {name}")
            continue
        print(f"\n=== {name} ===")
        row = analyze(path, name)
        rows.append(row)
        for k, v in row.items():
            print(f"  {k}: {v}")

    out = ROOT / "_tmp_effort_audit" / "vocal_type_mix_gate.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {out}")

    mok = next((r for r in rows if r["sample"] == "목잡이"), None)
    if mok:
        ok = (
            not mok["has_compound_firm_mix"]
            and mok["mix_evidence"] != "SUFFICIENT"
            and "MIX" not in str(mok["type_id"] or "")
        )
        print("\n목잡이 Mix-gate:", "PASS" if ok else "FAIL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
