#!/usr/bin/env python3
"""Paired breathiness audit — AIRY vs CLOSED directional sanity (labels for audit only).

Does NOT hardcode labels into inference. Pass paths via CLI:

  python scripts/breathiness_paired_audit.py --airy path.m4a --closed path.m4a

Or a manifest JSON:
  {"airy": "...", "closed": "..."}
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


def _median(xs: list[float]) -> float | None:
    if not xs:
        return None
    import numpy as np

    return float(np.median(xs))


def _seg_row(sample: str, seg: dict[str, Any], idx: int) -> dict[str, Any]:
    from audio_analyzer.vocal_evidence.phonation_quality import (
        classify_breathy_segment,
        classify_rough_segment,
        breathy_family_flags,
        rough_family_flags,
    )
    from audio_analyzer.vocal_function.validity import dim_valid

    obs = seg.get("observations") or {}
    src = ((seg.get("level2_proxies") or {}).get("glottal_source") or {})
    ve = seg.get("vocal_evidence") or {}
    vbd = seg.get("validity_by_dimension") or {}
    b = classify_breathy_segment(seg)
    r = classify_rough_segment(seg)
    bf = breathy_family_flags(seg)
    rf = rough_family_flags(seg)

    return {
        "sample": sample,
        "segment_id": idx,
        "start_sec": seg.get("start_sec"),
        "end_sec": seg.get("end_sec"),
        "voiced_ratio": seg.get("voiced_ratio"),
        "vocal_dominance": ve.get("vocal_dominance"),
        "vocal_specific": ve.get("vocal_specific"),
        "global_valid": seg.get("valid"),
        "valid_for_breathiness": dim_valid(seg, "breathiness"),
        "valid_for_roughness": dim_valid(seg, "roughness"),
        "valid_for_contact": dim_valid(seg, "glottal_contact"),
        "valid_for_effort": dim_valid(seg, "effort"),
        "valid_for_register": dim_valid(seg, "register"),
        "valid_for_resonance": dim_valid(seg, "resonance"),
        "valid_for_glottal_source": bool(src.get("valid")),
        "CPP": obs.get("periodicity_primary_db"),
        "HNR_proxy": obs.get("periodicity_primary_db"),
        "H1H2": obs.get("raw_h1_h2_proxy_db"),
        "spectral_tilt": obs.get("spectral_tilt_db_per_oct"),
        "spectral_centroid": obs.get("spectral_centroid_hz"),
        "F0_perturbation": obs.get("f0_frame_period_perturbation_proxy_percent"),
        "F0_dropout": obs.get("f0_dropout_ratio"),
        "onset_slope": obs.get("onset_slope_db_per_sec"),
        "GIF_valid": bool(src.get("valid")),
        "GIF_reject_reason": src.get("reason") or ((seg.get("level2_proxies") or {}).get("gif_gate") or {}).get("reason"),
        "estimated_NAQ": src.get("estimated_naq"),
        "estimated_OQ": src.get("estimated_oq_proxy"),
        "estimated_ClQ": src.get("estimated_clq_proxy"),
        "estimated_MFDR_norm": src.get("estimated_mfdr_norm_proxy"),
        "breathy_periodicity": bf.get("periodicity_noise"),
        "breathy_spectral": bf.get("harmonic_spectral"),
        "breathy_source": bf.get("glottal_source"),
        "breathy_noise": bf.get("periodicity_noise"),
        "rough_periodicity": rf.get("periodicity_loss"),
        "rough_irregularity": rf.get("irregularity"),
        "rough_dropout": rf.get("dropout"),
        "breathy_verdict": b.get("verdict"),
        "breathy_reason": b.get("reason"),
        "rough_verdict": r.get("verdict"),
        "rough_reason": r.get("reason"),
        "leakage_like": b.get("verdict") == "POSITIVE",
        "rough_like": r.get("verdict") == "POSITIVE",
        "breathiness_dim": json.dumps(vbd.get("breathiness") or {}, ensure_ascii=False),
    }


def _analyze(path: Path, out_dir: Path, tag: str) -> dict[str, Any]:
    from audio_analyzer.pipeline import analyze_audio
    from audio_analyzer.vocal_evidence.phonation_quality import classify_breathy_segment, classify_rough_segment
    from audio_analyzer.vocal_function.validity import dim_valid

    rid = f"breath_{tag}_{path.stem}"[:40]
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
    # Fallback: re-read from internal if not in debug
    if not segs:
        segs = vf.get("segments") or []
    leak = (vf.get("dimensions") or {}).get("air_leakage_breathiness") or {}
    rough = (vf.get("dimensions") or {}).get("phonation_regularity") or {}
    contact = (vf.get("dimensions") or {}).get("glottal_contact_profile") or {}

    # If segments absent from public profile, rebuild lightly via engine path stored in result
    if not segs and result.get("_segments"):
        segs = result["_segments"]

    rows = [_seg_row(tag, s, i) for i, s in enumerate(segs)]
    breathy_eval = [r for r in rows if r["valid_for_breathiness"]]
    breathy_pos = [r for r in breathy_eval if r["breathy_verdict"] == "POSITIVE"]
    breathy_neg = [r for r in breathy_eval if r["breathy_verdict"] == "NEGATIVE"]
    breathy_ins = [r for r in breathy_eval if r["breathy_verdict"] == "INSUFFICIENT"]
    rough_hits = [r for r in rows if r["rough_like"]]
    gif_valid = [r for r in rows if r["GIF_valid"]]

    # Rough FP audit lines
    rough_fp = []
    for r in rows:
        if r["rough_periodicity"] and not r["rough_irregularity"] and not r["rough_dropout"]:
            rough_fp.append(
                {
                    "start": r["start_sec"],
                    "end": r["end_sec"],
                    "CPP_low": r["breathy_periodicity"] or r["rough_periodicity"],
                    "perturbation_high": r["rough_irregularity"],
                    "dropout": r["rough_dropout"],
                    "verdict": r["rough_verdict"],
                    "reason": r["rough_reason"],
                }
            )

    summary = {
        "sample": tag,
        "file": path.name,
        "n_segments": len(rows),
        "usable_breathy_segments": len(breathy_eval),
        "breathy_hit_segments": len(breathy_pos),
        "breathy_hit_ratio": (len(breathy_pos) / len(breathy_eval)) if breathy_eval else 0.0,
        "breathy_negative": len(breathy_neg),
        "breathy_insufficient": len(breathy_ins),
        "CPP_median": _median([float(r["CPP"]) for r in breathy_eval if r["CPP"] is not None]),
        "H1H2_median": _median([float(r["H1H2"]) for r in breathy_eval if r["H1H2"] is not None]),
        "tilt_median": _median(
            [float(r["spectral_tilt"]) for r in breathy_eval if r["spectral_tilt"] is not None]
        ),
        "OQ_median": _median(
            [float(r["estimated_OQ"]) for r in rows if r["GIF_valid"] and r["estimated_OQ"] is not None]
        ),
        "rough_hit_segments": len(rough_hits),
        "rough_hit_ratio": (len(rough_hits) / len(rows)) if rows else 0.0,
        "GIF_valid_ratio": (len(gif_valid) / len(rows)) if rows else 0.0,
        "final_leakage_status": leak.get("status"),
        "final_leakage_confidence": leak.get("confidence_label"),
        "breathiness_coverage": leak.get("breathiness_coverage") or leak.get("profile"),
        "final_rough_status": rough.get("status"),
        "final_rough_confidence": rough.get("confidence_label"),
        "contact_status": contact.get("status"),
        "contact_confidence": contact.get("confidence_label"),
        "rough_periodicity_only_rejects": rough_fp,
        "rows": rows,
        "functional_quality": vf.get("functional_quality"),
        "primary": ((vf.get("coaching_decision") or {}).get("primary_bottleneck") or {}).get("id"),
    }
    return summary


def _root_cause(airy: dict[str, Any]) -> str:
    """Explain why AIRY might still be false-negative — no threshold guessing."""
    cov = airy.get("breathiness_coverage") or {}
    n_eval = cov.get("n_evaluable_segments") or airy.get("usable_breathy_segments") or 0
    n_pos = cov.get("n_positive_segments") or airy.get("breathy_hit_segments") or 0
    n_neg = cov.get("n_negative_segments") or airy.get("breathy_negative") or 0
    status = airy.get("final_leakage_status")
    causes = []
    rows = airy.get("rows") or []
    n_global = sum(1 for r in rows if r.get("global_valid"))
    n_breath = sum(1 for r in rows if r.get("valid_for_breathiness"))
    if n_global < n_breath:
        causes.append(
            f"A. dimension gate: global_valid={n_global} < breathiness_valid={n_breath} "
            "(old gate would have dropped breathy-evaluable segments)"
        )
    elif n_breath < max(3, 0.3 * len(rows)):
        causes.append(
            f"A. few breathiness-evaluable segments ({n_breath}/{len(rows)})"
        )
    if n_pos == 0 and n_eval >= 3:
        # check family availability
        single = sum(
            1
            for r in rows
            if r.get("breathy_reason") == "single_family_only"
        )
        if single:
            causes.append(
                f"B. 2-family requirement: {single} segments had only one breathy family"
            )
    if status == "LOW" and n_pos == 0:
        causes.append("C/F. fuse_leakage → LOW via negative coverage (or legacy zero-hit)")
    if status == "UNKNOWN":
        causes.append("coverage/evidence insufficient → UNKNOWN (not false LOW)")
    gif_fail = sum(1 for r in rows if not r.get("GIF_valid"))
    if gif_fail and n_breath:
        causes.append(
            f"D. GIF failed on {gif_fail} segments but breathiness still evaluable={n_breath} "
            "(GIF no longer required)"
        )
    rough_steal = [
        r for r in (airy.get("rough_periodicity_only_rejects") or []) if r.get("verdict") == "REJECTED"
    ]
    if rough_steal:
        causes.append(
            f"E. roughness no longer steals CPP-only: {len(rough_steal)} REJECTED "
            "periodicity_loss_without_irregularity"
        )
    if not causes:
        causes.append("F. mixed / unclear — inspect CSV")
    lines = [
        "BREATHY_FALSE_NEGATIVE_ROOT_CAUSE:",
        f"- status={status} conf={airy.get('final_leakage_confidence')}",
        f"- evaluable={n_eval} positive={n_pos} negative={n_neg}",
    ]
    lines.extend(f"- {c}" for c in causes)
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--airy", type=str, default=None)
    ap.add_argument("--closed", type=str, default=None)
    ap.add_argument("--manifest", type=str, default=None)
    ap.add_argument("--out", type=str, default=str(ROOT / "runtime" / "breathiness_paired_audit"))
    args = ap.parse_args()

    airy_p = args.airy
    closed_p = args.closed
    if args.manifest:
        man = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        airy_p = airy_p or man.get("airy")
        closed_p = closed_p or man.get("closed")
    if not airy_p or not closed_p:
        print("Provide --airy and --closed (or --manifest). Labels are audit-only.")
        return 2

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    airy = _analyze(Path(airy_p), out, "AIRY")
    closed = _analyze(Path(closed_p), out, "CLOSED")

    # CSV
    csv_path = out / "segments.csv"
    fieldnames = list((airy.get("rows") or [{}])[0].keys()) if airy.get("rows") else []
    if not fieldnames and closed.get("rows"):
        fieldnames = list(closed["rows"][0].keys())
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames or ["sample"])
        w.writeheader()
        for r in (airy.get("rows") or []) + (closed.get("rows") or []):
            w.writerow(r)

    def _print_side(name: str, s: dict[str, Any]) -> None:
        print(f"\n=== {name} ({s.get('file')}) ===")
        for k in (
            "usable_breathy_segments",
            "breathy_hit_segments",
            "breathy_hit_ratio",
            "breathy_negative",
            "breathy_insufficient",
            "CPP_median",
            "H1H2_median",
            "tilt_median",
            "OQ_median",
            "rough_hit_segments",
            "rough_hit_ratio",
            "GIF_valid_ratio",
            "final_leakage_status",
            "final_leakage_confidence",
            "final_rough_status",
            "contact_status",
            "contact_confidence",
        ):
            print(f"  {k}: {s.get(k)}")

    print("\n======= PAIRED SUMMARY (AIRY vs CLOSED) =======")
    print(f"{'metric':32} {'AIRY':>12} {'CLOSED':>12}")
    for k in (
        "usable_breathy_segments",
        "breathy_hit_segments",
        "breathy_hit_ratio",
        "CPP_median",
        "H1H2_median",
        "tilt_median",
        "OQ_median",
        "rough_hit_segments",
        "rough_hit_ratio",
        "GIF_valid_ratio",
        "final_leakage_status",
        "final_leakage_confidence",
        "final_rough_status",
        "final_rough_confidence",
    ):
        print(f"{k:32} {str(airy.get(k)):>12} {str(closed.get(k)):>12}")

    _print_side("AIRY", airy)
    _print_side("CLOSED", closed)

    # Directional sanity (audit expectation only — not scored into engine)
    airy_ev = airy.get("breathy_hit_ratio") or 0
    closed_ev = closed.get("breathy_hit_ratio") or 0
    print("\nDIRECTIONAL SANITY (audit expectation, not hardcoded in inference):")
    if airy_ev > closed_ev:
        print("  AIRY breathy evidence > CLOSED: YES")
    elif (airy.get("final_leakage_status") == "UNKNOWN") and airy_ev <= closed_ev:
        print("  AIRY breathy evidence > CLOSED: NO — but AIRY is UNKNOWN (not false LOW)")
    else:
        print("  AIRY breathy evidence > CLOSED: NO / PARTIAL")

    print("\n" + _root_cause(airy))

    payload = {
        "airy": {k: v for k, v in airy.items() if k != "rows"},
        "closed": {k: v for k, v in closed.items() if k != "rows"},
        "root_cause": _root_cause(airy),
        "threshold_retuning": "NO THRESHOLD RETUNING",
    }
    (out / "summary.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {csv_path}")
    print(f"Wrote {out / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
