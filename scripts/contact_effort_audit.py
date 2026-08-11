#!/usr/bin/env python3
"""Contact / Effort measurement audit (v2.7).

Usage:
  python scripts/contact_effort_audit.py --audio path.m4a --sample-id sample_001
  python scripts/contact_effort_audit.py --audio A.m4a --sample-id comfortable \\
      --audio-b B.m4a --sample-id-b squeezed
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _analyze(path: Path, out_dir: Path, sample_id: str) -> dict[str, Any]:
    from audio_analyzer.pipeline import analyze_audio
    from audio_analyzer.vocal_evidence.phonation_quality import (
        classify_rough_segment,
    )
    from audio_analyzer.vocal_function.evidence.effort_contact import (
        contact_evidence_packet,
        effort_evidence_packet,
        effort_like,
        firmer_like,
        gif_usable,
    )
    from audio_analyzer.vocal_function.validity import dim_valid

    rid = f"ce_{sample_id}_{path.stem}"[:48]
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
    segs = (vf.get("scientific_debug") or {}).get("segments") or vf.get("segments") or []
    dims = vf.get("dimensions") or {}
    contact = dims.get("glottal_contact_profile") or {}
    effort = dims.get("vocal_effort_strain") or {}
    rough = dims.get("phonation_regularity") or {}
    coach = vf.get("coaching_decision") or result.get("coaching_decision") or {}
    primary = (coach.get("primary") or {}).get("id") or coach.get("primary_bottleneck_id") or "none"

    n_total = len(segs)
    n_global = sum(1 for s in segs if s.get("valid"))
    n_contact = sum(1 for s in segs if dim_valid(s, "glottal_contact"))
    n_effort = sum(1 for s in segs if dim_valid(s, "effort"))
    n_gif = sum(1 for s in segs if gif_usable(s))

    rough_hits = sum(1 for s in segs if classify_rough_segment(s).get("verdict") == "POSITIVE")
    pressed_hits = 0
    vq = result.get("vocal_quality_profile") or {}
    for d in (vq.get("dimensions") or {}).values():
        if "pressed" in str(d.get("dimension_id") or "").lower() or "pressed" in str(
            d.get("display_name") or ""
        ).lower():
            pressed_hits = int(d.get("hit_segment_count") or 0)
    # Fallback: look for pressed-like in VQ focus / headlines
    if pressed_hits == 0:
        for fs in vq.get("focus_segments") or []:
            blob = f"{fs.get('headline','')}{fs.get('state','')}".lower()
            if "press" in blob or "압착" in blob:
                pressed_hits += 1

    c_prof = contact.get("profile") or {}
    e_prof = effort.get("profile") or {}
    fam_hits = e_prof.get("family_hits") or {}

    # Segment CSV
    csv_path = out_dir / f"{sample_id}_segments.csv"
    rows = []
    baseline = vf.get("scientific_debug", {}).get("baseline") or {}
    for i, s in enumerate(segs):
        cp = contact_evidence_packet(s, baseline)
        ep = effort_evidence_packet(s, baseline)
        fam = ep.get("families") or {}
        obs = s.get("observations") or {}
        rows.append(
            {
                "time": f"{s.get('start_sec')}-{s.get('end_sec')}",
                "global_valid": s.get("valid"),
                "contact_valid": dim_valid(s, "glottal_contact"),
                "effort_valid": dim_valid(s, "effort"),
                "gif_valid": gif_usable(s),
                "contact_score": cp.get("final_score"),
                "effort_score": ep.get("effort_score"),
                "intensity_family": fam.get("intensity"),
                "temporal_family": fam.get("temporal"),
                "regularity_family": fam.get("regularity"),
                "spectral_family": fam.get("spectral"),
                "contact_family": fam.get("contact"),
                "recovery_family": fam.get("recovery"),
                "roughness": classify_rough_segment(s).get("verdict") == "POSITIVE",
                "pressed_like": False,
                "f0_hz": obs.get("f0_hz"),
                "periodicity_db": obs.get("periodicity_primary_db"),
                "firmer_like": firmer_like(s, baseline),
                "effort_like": effort_like(s, baseline),
            }
        )
    if rows:
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    summary = {
        "sample_id": sample_id,
        "audio": str(path),
        "n_total": n_total,
        "n_global_valid": n_global,
        "n_contact_valid": n_contact,
        "n_effort_valid": n_effort,
        "n_gif_valid": n_gif,
        "contact": {
            "score": contact.get("continuum_0_to_1"),
            "status": contact.get("status"),
            "confidence": contact.get("confidence_label"),
            "profile": c_prof,
        },
        "effort": {
            "score": e_prof.get("effort_score"),
            "status": effort.get("status"),
            "confidence": effort.get("confidence_label"),
            "family_hits": fam_hits,
            "hit_segments": e_prof.get("effort_hit_segments"),
        },
        "roughness": {"status": rough.get("status"), "hits": rough_hits},
        "pressed_observation_hits": pressed_hits,
        "primary": primary,
        "engine_version": vf.get("engine_version"),
        "segments_csv": str(csv_path),
        "vocal_type": (result.get("vocal_type") or {}).get("type_id")
        or (result.get("coach_profile") or {}).get("vocal_type"),
    }

    freeze_path = out_dir / f"{sample_id}_freeze.json"
    freeze_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    summary["freeze_path"] = str(freeze_path)
    return summary


def _print_audit(s: dict[str, Any]) -> None:
    c = s["contact"]
    e = s["effort"]
    cp = c.get("profile") or {}
    fh = e.get("family_hits") or {}
    print("\nCONTACT / EFFORT AUDIT")
    print(f"sample: {s['sample_id']}")
    print(f"n total={s['n_total']}  global_valid={s['n_global_valid']}  "
          f"contact_valid={s['n_contact_valid']}  effort_valid={s['n_effort_valid']}  "
          f"GIF_valid={s['n_gif_valid']}")
    print("\nCONTACT")
    print(f"  score={c.get('score')}  status={c.get('status')}  confidence={c.get('confidence')}")
    print(f"  FLOW/gif_supported={cp.get('gif_supported')}  fallback={cp.get('fallback_supported')}")
    print(f"  evidence_mass={cp.get('evidence_mass')}  family_count={cp.get('family_count')}")
    print("\nEFFORT")
    print(f"  score={e.get('score')}  status={e.get('status')}  confidence={e.get('confidence')}")
    print(
        f"  INTENSITY={fh.get('intensity', 0)}  TEMPORAL={fh.get('temporal', 0)}  "
        f"REGULARITY={fh.get('regularity', 0)}  SPECTRAL={fh.get('spectral', 0)}  "
        f"RECOVERY={fh.get('recovery', 0)}  CONTACT={fh.get('contact', 0)}"
    )
    print(f"  hit_segments={e.get('hit_segments')}")
    print(f"\nROUGHNESS  status={s['roughness'].get('status')}  hits={s['roughness'].get('hits')}")
    print(f"PRESSED OBSERVATION  hits={s.get('pressed_observation_hits')}")
    print(f"PRIMARY  {s.get('primary')}")
    print(f"engine  {s.get('engine_version')}")


def _print_pair(a: dict[str, Any], b: dict[str, Any]) -> None:
    print("\nPAIR COMPARISON")
    hdr = f"{'':28} {a['sample_id']:>14} {b['sample_id']:>14}"
    print(hdr)

    def row(label, va, vb):
        print(f"{label:28} {str(va):>14} {str(vb):>14}")

    def pct(n, d):
        return f"{(100.0 * n / d):.1f}%" if d else "n/a"

    row("Global valid %", pct(a["n_global_valid"], a["n_total"]), pct(b["n_global_valid"], b["n_total"]))
    row("Contact valid %", pct(a["n_contact_valid"], a["n_total"]), pct(b["n_contact_valid"], b["n_total"]))
    row("Effort valid %", pct(a["n_effort_valid"], a["n_total"]), pct(b["n_effort_valid"], b["n_total"]))
    row("Contact score", a["contact"].get("score"), b["contact"].get("score"))
    row("Effort score", a["effort"].get("score"), b["effort"].get("score"))
    row(
        "Effort family count",
        sum(1 for v in (a["effort"].get("family_hits") or {}).values() if v),
        sum(1 for v in (b["effort"].get("family_hits") or {}).values() if v),
    )
    row("Roughness hits", a["roughness"].get("hits"), b["roughness"].get("hits"))
    row("Pressed hits", a.get("pressed_observation_hits"), b.get("pressed_observation_hits"))
    row("Primary", a.get("primary"), b.get("primary"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Contact/Effort measurement audit")
    ap.add_argument("--audio", required=True, help="Primary audio path")
    ap.add_argument("--sample-id", default="sample_001")
    ap.add_argument("--audio-b", default=None, help="Optional pair audio")
    ap.add_argument("--sample-id-b", default="sample_002")
    ap.add_argument(
        "--out",
        default=str(ROOT / "runtime" / "audits" / "contact_effort"),
    )
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    a = _analyze(Path(args.audio), out_dir, args.sample_id)
    _print_audit(a)

    if args.audio_b:
        b = _analyze(Path(args.audio_b), out_dir, args.sample_id_b)
        _print_audit(b)
        _print_pair(a, b)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
