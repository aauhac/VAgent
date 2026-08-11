#!/usr/bin/env python3
"""
Vocal Type Anchor Audit (v1.1)

Workflow (label leakage prevention):
1) Audio inference with sample_id only (no artist / filename into engine)
2) Freeze result
3) Optionally read human_notes from manifest
4) Compare externally

Usage:
  python scripts/vocal_type_anchor_audit.py --audio path.m4a --sample-id psh_001
  python scripts/vocal_type_anchor_audit.py --manifest validation/vocal_type_anchor_manifest.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _family_line(summary: dict) -> str:
    parts = []
    for fid in ("SOURCE_FLOW", "HARMONIC_SOURCE", "CONTACT", "SPECTRAL_WEIGHT"):
        info = (summary or {}).get(fid) or {}
        parts.append(f"{fid}={info.get('dominant', 'UNAVAILABLE')}")
    return " | ".join(parts)


def analyze_audio(path: Path, out_dir: Path, sample_id: str) -> dict:
    from audio_analyzer.pipeline import analyze_audio as run

    # Engine sees only a neutral recording_id — never artist name
    rid = f"anchor_{sample_id}"[:40]
    result = run(
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
    # --- FREEZE inference result before any human annotation ---
    freeze = {
        "sample_id": sample_id,
        "audio_path": str(path),
        "vocal_type_profile": vt,
        "dimensions": vf.get("dimensions") or {},
        "criteria_matrix": vf.get("criteria_matrix") or [],
        "coaching_decision": vf.get("coaching_decision") or {},
        "engine_version": vf.get("engine_version"),
        "report_version": vf.get("report_version"),
    }
    freeze_path = out_dir / f"{sample_id}_freeze.json"
    freeze_path.write_text(json.dumps(freeze, indent=2, ensure_ascii=False), encoding="utf-8")
    return freeze


def print_audit(freeze: dict, human_notes: dict | None = None) -> None:
    vt = freeze.get("vocal_type_profile") or {}
    hc = vt.get("head_chest") or {}
    ev = vt.get("evidence") or {}
    bridge = vt.get("bridge") or {}
    dims = freeze.get("dimensions") or {}
    matrix = freeze.get("criteria_matrix") or []
    reg_row = next(
        (r for r in matrix if r.get("dimension_id") == "register_configuration"),
        {},
    )

    print("\nVOCAL TYPE ANCHOR AUDIT")
    print(f"Sample:\n{freeze.get('sample_id')}")
    print(f"\nTYPE\n{vt.get('type_id')} — {vt.get('display_name')}")
    print(f"\nChest / Head\n{hc.get('chest_ratio')} / {hc.get('head_ratio')}")
    print(f"\nTYPE CONFIDENCE\n{vt.get('confidence')}")
    print(f"\nEvidence mass\n{ev.get('mass') or hc.get('evidence_mass')}")
    print(f"\nDirectionality\n{ev.get('directionality') or hc.get('directionality')}")
    print(f"\n{_family_line(ev.get('family_summary'))}")
    print(f"\nBridge\n{bridge.get('type')} score={bridge.get('score')}")
    print(f"\nPassaggio\n{bridge.get('passaggio_time')}")
    print(f"\nRegister evidence:\n{reg_row.get('measurement_sufficiency') or bridge.get('register_sufficiency')}")
    print("\nRange:")
    for band in ("low", "mid", "high"):
        r = (vt.get("range_profiles") or {}).get(band) or {}
        print(
            f"  {band.upper()}  Chest {r.get('chest_ratio')} / Head {r.get('head_ratio')} "
            f"avail={r.get('available')}"
        )
    contact = dims.get("glottal_contact_profile") or {}
    effort = dims.get("vocal_effort_strain") or {}
    leak = dims.get("air_leakage_breathiness") or {}
    res = dims.get("resonance_formant_strategy") or {}
    rough = dims.get("phonation_regularity") or {}
    print(f"\nCONTACT\n{contact.get('summary') or contact.get('continuum_label')}")
    print(f"\nEFFORT\n{effort.get('status')}")
    print(f"\nBREATHINESS\n{leak.get('status')}")
    print(f"\nRESONANCE\n{(res.get('profile') or {}).get('mid_presence')}")
    print(f"\nROUGHNESS\n{rough.get('status')}")
    print(f"\nModifiers:\n{vt.get('modifiers')}")
    print(f"\nWarnings:\n{vt.get('warnings')}")
    timeline = vt.get("timeline") or []
    if timeline:
        print("\nTimeline:")
        for t in timeline:
            if t.get("available") is False:
                print(f"  {t.get('start_sec')}–{t.get('end_sec')}s  측정 부족")
            else:
                print(
                    f"  {t.get('start_sec')}–{t.get('end_sec')}s  "
                    f"Chest {t.get('chest_ratio')} / Head {t.get('head_ratio')}"
                )

    # Human notes are read ONLY after freeze
    if human_notes:
        print("\n--- HUMAN NOTES (post-freeze) ---")
        for k, v in human_notes.items():
            print(f"  {k}: {v}")


def contrast_table(a: dict, b: dict) -> None:
    def pack(f):
        vt = f.get("vocal_type_profile") or {}
        hc = vt.get("head_chest") or {}
        ev = vt.get("evidence") or {}
        br = vt.get("bridge") or {}
        dims = f.get("dimensions") or {}
        fam = ev.get("family_summary") or {}
        return {
            "id": f.get("sample_id"),
            "chest": hc.get("chest_ratio"),
            "head": hc.get("head_ratio"),
            "index": hc.get("index"),
            "mass": ev.get("mass") or hc.get("evidence_mass"),
            "dir": ev.get("directionality"),
            "bridge": br.get("type"),
            "type": vt.get("type_id"),
            "flow": (fam.get("SOURCE_FLOW") or {}).get("dominant"),
            "harm": (fam.get("HARMONIC_SOURCE") or {}).get("dominant"),
            "contact_f": (fam.get("CONTACT") or {}).get("dominant"),
            "spec": (fam.get("SPECTRAL_WEIGHT") or {}).get("dominant"),
            "contact": (dims.get("glottal_contact_profile") or {}).get("continuum_label"),
            "effort": (dims.get("vocal_effort_strain") or {}).get("status"),
            "breath": (dims.get("air_leakage_breathiness") or {}).get("status"),
            "res": ((dims.get("resonance_formant_strategy") or {}).get("profile") or {}).get(
                "mid_presence"
            ),
        }

    pa, pb = pack(a), pack(b)
    print("\n======= CONTRAST =======")
    print(f"{'':28} {pa['id']:>14} {pb['id']:>14}")
    for key, label in (
        ("chest", "Chest %"),
        ("head", "Head %"),
        ("mass", "Evidence mass"),
        ("dir", "Directionality"),
        ("flow", "FLOW"),
        ("harm", "HARMONIC"),
        ("contact_f", "CONTACT fam"),
        ("spec", "SPECTRAL"),
        ("bridge", "Bridge"),
        ("type", "Type"),
        ("contact", "Contact"),
        ("effort", "Effort"),
        ("breath", "Breathiness"),
        ("res", "Resonance"),
    ):
        print(f"{label:28} {str(pa[key]):>14} {str(pb[key]):>14}")
    ia, ib = pa.get("index"), pb.get("index")
    if ia is not None and ib is not None:
        print(f"\ndelta_head_chest_index = {abs(float(ia) - float(ib)):.3f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", action="append", default=[])
    ap.add_argument("--sample-id", action="append", default=[])
    ap.add_argument("--manifest", type=str, default="")
    ap.add_argument("--out", type=str, default=str(ROOT / "runtime" / "vocal_type_anchor"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    jobs = []
    human_by_id: dict[str, dict] = {}

    if args.manifest:
        man = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        for s in man.get("samples") or []:
            sid = s["sample_id"]
            # Do NOT pass human_notes into inference
            jobs.append((Path(s["path"]), sid))
            if s.get("human_notes"):
                human_by_id[sid] = s["human_notes"]

    for i, audio in enumerate(args.audio):
        sid = args.sample_id[i] if i < len(args.sample_id) else f"sample_{i+1:03d}"
        jobs.append((Path(audio), sid))

    if not jobs:
        print("Provide --audio/--sample-id or --manifest", file=sys.stderr)
        return 2

    freezes = []
    for path, sid in jobs:
        if not path.exists():
            print(f"SKIP missing: {path}")
            continue
        freeze = analyze_audio(path, out, sid)
        # freeze complete — now safe to attach human notes for display only
        print_audit(freeze, human_notes=human_by_id.get(sid))
        freezes.append(freeze)

    if len(freezes) >= 2:
        contrast_table(freezes[0], freezes[1])

    (out / "summary.json").write_text(
        json.dumps(freezes, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nWrote {out / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
