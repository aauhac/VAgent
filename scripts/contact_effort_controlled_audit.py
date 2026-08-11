#!/usr/bin/env python3
"""Controlled four-sample contact/effort audit (v2.8).

Inference receives neutral sample ids only. Human intent is read AFTER freeze.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _analyze(path: Path, out_dir: Path, sample_id: str) -> dict[str, Any]:
    from audio_analyzer.pipeline import analyze_audio
    from audio_analyzer.vocal_evidence.phonation_quality import classify_rough_segment
    from audio_analyzer.vocal_function.evidence.effort_trajectory import (
        compute_effort_event_context,
    )
    from audio_analyzer.vocal_function.evidence.effort_contact import gif_usable
    from audio_analyzer.vocal_function.validity import dim_valid

    rid = f"ce28e_{sample_id}_{path.stem}"[:48]
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
    contact = dims.get("glottal_contact_profile") or {}
    effort = dims.get("vocal_effort_strain") or {}
    rough = dims.get("phonation_regularity") or {}
    leak = dims.get("air_leakage_breathiness") or {}
    coach = vf.get("coaching_decision") or {}
    primary = (coach.get("primary") or {}).get("id") or coach.get("primary_bottleneck_id") or "none"

    e_prof = effort.get("profile") or {}
    c_prof = contact.get("profile") or {}
    fam = e_prof.get("family_hits") or {}

    # Aggregate trajectory diagnostics over segments
    slopes, deltas, attacks, regs, specs, recs, shifts = [], [], [], [], [], [], []
    traj_rows = []
    baseline = (vf.get("scientific_debug") or {}).get("baseline") or {}
    for i, s in enumerate(segs):
        pre = segs[i - 1] if i > 0 else None
        post = segs[i + 1] if i + 1 < len(segs) else None
        ctx = compute_effort_event_context(s, pre=pre, post=post, baseline=baseline)
        inten = ctx.get("intensity") or {}
        if inten.get("slope_db_per_sec") is not None:
            slopes.append(float(inten["slope_db_per_sec"]))
        if inten.get("delta_db") is not None:
            deltas.append(float(inten["delta_db"]))
        attacks.append(1 if (ctx.get("attack") or {}).get("positive") else 0)
        regs.append(1 if (ctx.get("regularity_cost") or {}).get("positive") else 0)
        specs.append(1 if (ctx.get("spectral_cost") or {}).get("positive") else 0)
        recs.append(1 if (ctx.get("recovery") or {}).get("positive") else 0)
        shifts.append(1 if (ctx.get("contact_shift") or {}).get("positive") else 0)
        traj_rows.append(
            {
                "i": i,
                "start": s.get("start_sec"),
                "end": s.get("end_sec"),
                "intensity_db": inten.get("during_db"),
                "delta_db": inten.get("delta_db"),
                "slope": inten.get("slope_db_per_sec"),
                "status": inten.get("status"),
                "elevated": ctx.get("elevated"),
                "score": ctx.get("final_score"),
                "core": ctx.get("core_family_count"),
                "support": ctx.get("support_family_count"),
                "why": json.dumps(ctx.get("why") or {}, ensure_ascii=False),
            }
        )

    traj_csv = out_dir / f"{sample_id}_trajectory.csv"
    if traj_rows:
        with traj_csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(traj_rows[0].keys()))
            w.writeheader()
            w.writerows(traj_rows)

    rough_hits = sum(1 for s in segs if classify_rough_segment(s).get("verdict") == "POSITIVE")
    summary = {
        "sample_id": sample_id,
        "audio": str(path),
        "n_total": len(segs),
        "n_global_valid": sum(1 for s in segs if s.get("valid")),
        "n_contact_valid": sum(1 for s in segs if dim_valid(s, "glottal_contact")),
        "n_effort_valid": sum(1 for s in segs if dim_valid(s, "effort")),
        "n_gif_valid": sum(1 for s in segs if gif_usable(s)),
        "contact_score": contact.get("continuum_0_to_1"),
        "contact_status": contact.get("status"),
        "effort_score": e_prof.get("effort_score"),
        "effort_status": effort.get("status"),
        "loudness_level": e_prof.get("loudness_level"),
        "intensity_slope_median": float(np_median(slopes)) if slopes else None,
        "intensity_delta_median": float(np_median(deltas)) if deltas else None,
        "attack_cost_hits": sum(attacks),
        "regularity_cost_hits": sum(regs),
        "spectral_residual_hits": sum(specs),
        "recovery_cost_hits": sum(recs),
        "contact_shift_hits": sum(shifts),
        "core_family_count": e_prof.get("core_family_count"),
        "support_family_count": e_prof.get("support_family_count"),
        "family_hits": fam,
        "rough_hits": rough_hits,
        "rough_status": rough.get("status"),
        "breathiness_status": leak.get("status"),
        "primary": primary,
        "engine_version": vf.get("engine_version"),
        "why_effort": (effort.get("focus_segments") or [{}])[0].get("why")
        if effort.get("focus_segments")
        else None,
        "trajectory_csv": str(traj_csv),
        "contact_profile": c_prof,
    }
    (out_dir / f"{sample_id}_freeze.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def np_median(xs):
    import numpy as np

    return float(np.median(xs)) if xs else None


def _print_table(rows: list[dict[str, Any]]) -> None:
    keys = [
        ("contact_score", "Contact"),
        ("effort_score", "Effort"),
        ("loudness_level", "Loudness"),
        ("intensity_slope_median", "IntSlope"),
        ("attack_cost_hits", "Attack"),
        ("regularity_cost_hits", "RegCost"),
        ("spectral_residual_hits", "SpecRes"),
        ("contact_shift_hits", "CShift"),
        ("recovery_cost_hits", "Recovery"),
        ("core_family_count", "CoreN"),
        ("support_family_count", "SuppN"),
        ("rough_hits", "Rough"),
        ("breathiness_status", "Breath"),
        ("primary", "Primary"),
    ]
    ids = [r["sample_id"] for r in rows]
    print("\nCONTROLLED FOUR-SAMPLE TABLE")
    hdr = f"{'metric':22}" + "".join(f"{i:>14}" for i in ids)
    print(hdr)
    for k, label in keys:
        print(f"{label:22}" + "".join(f"{str(r.get(k)):>14}" for r in rows))


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--manifest",
        default=str(ROOT / "validation" / "contact_effort_controlled_v1.json"),
    )
    ap.add_argument(
        "--out",
        default=str(ROOT / "runtime" / "audits" / "contact_effort_v28"),
    )
    args = ap.parse_args()
    man = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    results = []
    intent_by_id = {}
    for item in man["samples"]:
        sid = item["sample_id"]
        path = ROOT / item["path"]
        print("=" * 60)
        print("ANALYZING", sid, path.name)
        if not path.exists():
            print("MISSING", path)
            continue
        s = _analyze(path, out, sid)
        # Read human intent AFTER inference
        intent_by_id[sid] = item.get("human_intent") or {}
        s["human_intent"] = intent_by_id[sid]
        results.append(s)
        print(
            f"  effort={s.get('effort_score')} status={s.get('effort_status')} "
            f"contact={s.get('contact_score')} rough={s.get('rough_hits')} "
            f"breath={s.get('breathiness_status')} primary={s.get('primary')}"
        )

    _print_table(results)

    by = {r["sample_id"]: r for r in results}
    checks = {}
    if "ctrl_b" in by and "ctrl_a" in by:
        checks["b_effort_gt_a"] = (by["ctrl_b"].get("effort_score") or 0) > (
            by["ctrl_a"].get("effort_score") or 0
        )
    if "ctrl_b" in by and "ctrl_d" in by:
        eb = by["ctrl_b"].get("effort_score") or 0
        ed = by["ctrl_d"].get("effort_score") or 0
        checks["b_effort_gt_d"] = eb > ed
        checks["b_minus_d"] = round(eb - ed, 3)
    if "ctrl_b" in by and "ctrl_c" in by:
        checks["b_effort_gt_c"] = (by["ctrl_b"].get("effort_score") or 0) > (
            by["ctrl_c"].get("effort_score") or 0
        )
    if "ctrl_c" in by:
        checks["c_breathiness"] = by["ctrl_c"].get("breathiness_status")
        checks["c_effort_lowish"] = by["ctrl_c"].get("effort_status") in ("LOW", "UNKNOWN", "OCCASIONAL")

    payload = {
        "before_v27": {
            "ctrl_a": 0.17,
            "ctrl_b": 0.40,
            "ctrl_c": 0.07,
            "ctrl_d": 0.52,
            "b_minus_d": -0.12,
        },
        "after": {
            sid: {
                "effort": by[sid].get("effort_score"),
                "status": by[sid].get("effort_status"),
                "contact": by[sid].get("contact_score"),
                "rough": by[sid].get("rough_hits"),
                "breath": by[sid].get("breathiness_status"),
            }
            for sid in by
        },
        "ordinal_checks": checks,
        "samples": results,
    }
    summary_path = out / "four_sample_summary.json"
    summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # CSV comparison
    csv_path = out / "four_sample_comparison.csv"
    if results:
        fields = [
            "sample_id",
            "contact_score",
            "effort_score",
            "effort_status",
            "loudness_level",
            "intensity_slope_median",
            "attack_cost_hits",
            "regularity_cost_hits",
            "spectral_residual_hits",
            "recovery_cost_hits",
            "contact_shift_hits",
            "core_family_count",
            "support_family_count",
            "rough_hits",
            "breathiness_status",
            "primary",
        ]
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            for r in results:
                w.writerow(r)

    print("\nORDINAL", json.dumps(checks, ensure_ascii=False, indent=2))
    print("wrote", summary_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
