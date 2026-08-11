#!/usr/bin/env python3
"""Audit Vocal Type / Head–Chest profile for local audio or analysis JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _print_profile(tag: str, vt: dict, vf: dict) -> None:
    hc = vt.get("head_chest") or {}
    bridge = vt.get("bridge") or {}
    dims = vf.get("dimensions") or {}
    decision = vf.get("coaching_decision") or {}
    primary = decision.get("primary_bottleneck") or {}
    print(f"\n=== {tag} ===")
    print(f"VOCAL TYPE: {vt.get('display_name')} ({vt.get('type_id')})")
    print(f"CONFIDENCE: {vt.get('confidence')}")
    print(f"CHEST %: {hc.get('chest_ratio')}  HEAD %: {hc.get('head_ratio')}  index={hc.get('index')}")
    print(f"BRIDGE: {bridge.get('type')} score={bridge.get('score')} passaggio={bridge.get('passaggio_time')}")
    print(f"MODIFIERS: {vt.get('modifiers')}")
    rp = vt.get("range_profiles") or {}
    for band in ("low", "mid", "high"):
        r = rp.get(band) or {}
        print(f"  {band.upper()}: chest={r.get('chest_ratio')} head={r.get('head_ratio')} avail={r.get('available')}")
    contact = dims.get("glottal_contact_profile") or {}
    effort = dims.get("vocal_effort_strain") or {}
    leak = dims.get("air_leakage_breathiness") or {}
    res = dims.get("resonance_formant_strategy") or {}
    print(f"CONTACT: {contact.get('summary') or contact.get('continuum_label')} conf={contact.get('confidence_label')}")
    print(f"EFFORT: {effort.get('status')} conf={effort.get('confidence_label')}")
    print(f"BREATHINESS: {leak.get('status')} conf={leak.get('confidence_label')}")
    print(f"RESONANCE: {(res.get('profile') or {}).get('mid_presence')}")
    print(f"PRIMARY COACHING: {primary.get('id')} — {primary.get('user_title')}")
    print(f"WHY: {vt.get('description')}")
    if vt.get("coaching_link"):
        print(f"COACH LINK: {vt.get('coaching_link')}")


def analyze_file(path: Path, out_dir: Path, tag: str) -> dict:
    from audio_analyzer.pipeline import analyze_audio

    rid = f"vtype_{tag}_{path.stem}"[:40]
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
    vt = vf.get("vocal_type_profile") or {}
    _print_profile(tag, vt, vf)
    return {"file": path.name, "vocal_type_profile": vt, "primary": (vf.get("coaching_decision") or {}).get("primary_bottleneck")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", action="append", default=[])
    ap.add_argument("--json", action="append", default=[])
    ap.add_argument("--tag", action="append", default=[])
    ap.add_argument("--out", type=str, default=str(ROOT / "runtime" / "vocal_type_audit"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    results = []
    if args.json:
        for i, jp in enumerate(args.json):
            data = json.loads(Path(jp).read_text(encoding="utf-8"))
            vf = data.get("vocal_function_profile") or data
            vt = vf.get("vocal_type_profile") or data.get("vocal_type_profile") or {}
            tag = (args.tag[i] if i < len(args.tag) else Path(jp).stem)
            _print_profile(tag, vt, vf)
            results.append({"file": jp, "vocal_type_profile": vt})
    for i, apath in enumerate(args.audio):
        tag = args.tag[i] if i < len(args.tag) else Path(apath).stem
        results.append(analyze_file(Path(apath), out, tag))

    if len(results) >= 2:
        print("\n======= PAIRED DIFF =======")
        a, b = results[0], results[1]
        ha = (a.get("vocal_type_profile") or {}).get("head_chest") or {}
        hb = (b.get("vocal_type_profile") or {}).get("head_chest") or {}
        print(f"chest% {ha.get('chest_ratio')} vs {hb.get('chest_ratio')}")
        print(f"type   {(a.get('vocal_type_profile') or {}).get('type_id')} vs {(b.get('vocal_type_profile') or {}).get('type_id')}")

    (out / "summary.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {out / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
