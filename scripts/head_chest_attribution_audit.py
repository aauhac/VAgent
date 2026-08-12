#!/usr/bin/env python3
"""Read-only Head/Chest attribution audit (no production mutation)."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ANCHORS = {
    "편하게": ROOT / "편하게.m4a",
    "목잡이": ROOT / "목잡이.m4a",
    "호흡많고헤드": ROOT / "호흡많고헤드.m4a",
    "편안세게": ROOT / "편안세게.m4a",
}


def _fam_dir(info: dict[str, Any]) -> str:
    st = (info.get("status") or "UNAVAILABLE").upper()
    if st == "CHEST":
        return "CHEST"
    if st == "HEAD":
        return "HEAD"
    if st in ("NEUTRAL", "NO_DIRECTION"):
        return "NONE"
    return "NONE"


def _fam_why(fid: str, info: dict[str, Any]) -> str:
    ev = info.get("evidence") or []
    if ev:
        return ",".join(ev[:4])
    extra = info.get("extra") or {}
    if extra.get("firm"):
        return "firm_contact"
    if extra.get("light"):
        return "light_contact"
    raw = info.get("raw_value")
    if isinstance(raw, dict):
        parts = []
        for k, v in raw.items():
            if v is not None:
                parts.append(f"{k}={v}")
        return ";".join(parts[:3])
    if raw is not None:
        return str(raw)
    return info.get("status") or ""


def _conflict_type(row: dict[str, Any]) -> str | None:
    fc = row.get("family_contribution") or {}
    sf = _fam_dir(fc.get("SOURCE_FLOW") or {})
    hf = _fam_dir(fc.get("HARMONIC_SOURCE") or {})
    if sf == "CHEST" and hf == "HEAD":
        return "SOURCE_CHEST_HARMONIC_HEAD"
    if sf == "HEAD" and hf == "CHEST":
        return "SOURCE_HEAD_HARMONIC_CHEST"
    spec = fc.get("SPECTRAL_WEIGHT") or {}
    if spec.get("applied") and spec.get("status") in ("CHEST", "HEAD"):
        tilt = (spec.get("raw_value") or {}).get("tilt")
        e24 = (spec.get("raw_value") or {}).get("e24")
        if tilt is not None and e24 is not None:
            # both can vote opposite directions internally
            if float(tilt) >= -10 and float(e24) <= 0.08:
                return "SPECTRAL_TILT_CHEST_E24_HEAD"
            if float(tilt) <= -16 and float(e24) >= 0.18:
                return "SPECTRAL_TILT_HEAD_E24_CHEST"
    return None


def analyze_sample(path: Path, sample_id: str) -> dict[str, Any]:
    from audio_analyzer.coach_profile.head_chest import (
        detect_neutral_collapse,
        family_ablation,
        index_to_ratios,
        score_all_segments,
        song_evidence_stats,
        weighted_index,
        aggregate_range_profiles,
    )
    from audio_analyzer.pipeline import analyze_audio

    rid = f"hca_{sample_id}"[:40]
    result = analyze_audio(
        str(path),
        output_dir=str(ROOT / "runtime" / "audits" / "head_chest" / "runs"),
        recording_id=rid,
        separate=False,
        analysis_mode="FUNCTIONAL",
        input_mode="VOCAL_ONLY",
        build_preview=False,
    )
    vf = result.get("vocal_function_profile") or {}
    segs = (vf.get("scientific_debug") or {}).get("segments") or []
    baseline = (vf.get("scientific_debug") or {}).get("baseline") or {}
    vt = vf.get("vocal_type_profile") or {}
    effort = vf.get("effort_assessment") or {}
    reg_dim = (vf.get("dimensions") or {}).get("register_configuration") or {}

    rows = score_all_segments(segs, baseline=baseline)
    stats = song_evidence_stats(rows)
    idx = weighted_index(rows)
    ratios = index_to_ratios(idx)
    ranges = aggregate_range_profiles(rows)
    collapse = detect_neutral_collapse(rows, ranges, index=idx, stats=stats)
    ablation = family_ablation(segs, baseline=baseline)

    usable = [r for r in rows if r.get("head_chest_index") is not None]
    total_usable = len(usable)

    # Family mass sums
    fam_mass = {
        fid: {"head": 0.0, "chest": 0.0}
        for fid in ("SOURCE_FLOW", "HARMONIC_SOURCE", "SPECTRAL_WEIGHT", "CONTACT")
    }
    for r in usable:
        for fid in fam_mass:
            info = (r.get("family_contribution") or {}).get(fid) or {}
            fam_mass[fid]["head"] += float(info.get("head") or 0)
            fam_mass[fid]["chest"] += float(info.get("chest") or 0)

    total_head = sum(fam_mass[f]["head"] for f in fam_mass)
    total_chest = sum(fam_mass[f]["chest"] for f in fam_mass)

    # Segment counts
    src_head = sum(
        1
        for r in usable
        if _fam_dir((r.get("family_contribution") or {}).get("SOURCE_FLOW") or {}) == "HEAD"
        or _fam_dir((r.get("family_contribution") or {}).get("HARMONIC_SOURCE") or {}) == "HEAD"
    )
    high_conf_head = sum(
        1
        for r in usable
        if float(r.get("head_chest_index") or 0) >= 0.65 and (r.get("confidence") or "") == "high"
    )
    high_conf_head_alt = sum(
        1
        for r in usable
        if float(r.get("head_chest_index") or 0) >= 0.55
        and float(r.get("family_agreement") or 0) >= 0.55
    )

    conflicts = []
    for r in usable:
        ct = _conflict_type(r)
        if ct:
            conflicts.append(
                {
                    "start": r.get("start_sec"),
                    "end": r.get("end_sec"),
                    "type": ct,
                    "agreement": r.get("family_agreement"),
                }
            )

    # Register episodes
    episodes = vf.get("episodes") or []
    reg_trans = [
        e
        for e in episodes
        if (e.get("type") or "").upper() in ("REGISTER_TRANSITION", "REGISTER_SHIFT")
    ]
    reg_conf_head = 0  # no separate register-confirmed head in HC engine

    # Baseline modes from first usable segment modes
    baseline_modes = {}
    if usable:
        avr = usable[0].get("absolute_vs_relative") or {}
        baseline_modes = avr

    segment_rows = []
    for i, r in enumerate(usable):
        fc = r.get("family_contribution") or {}
        segment_rows.append(
            {
                "segment_id": i,
                "start_sec": r.get("start_sec"),
                "end_sec": r.get("end_sec"),
                "f0_hz": r.get("f0_hz"),
                "pitch_band": r.get("pitch_band"),
                "head_chest_index": r.get("head_chest_index"),
                "confidence": r.get("confidence"),
                "evidence_mass": r.get("evidence_mass"),
                "family_agreement": r.get("family_agreement"),
                "directionality": r.get("directionality"),
                "n_families": r.get("n_families"),
                "n_source_families": r.get("n_source_families"),
                "SOURCE_FLOW": _fam_dir(fc.get("SOURCE_FLOW") or {}),
                "HARMONIC_SOURCE": _fam_dir(fc.get("HARMONIC_SOURCE") or {}),
                "SPECTRAL_WEIGHT": _fam_dir(fc.get("SPECTRAL_WEIGHT") or {}),
                "CONTACT": _fam_dir(fc.get("CONTACT") or {}),
                "why_SOURCE_FLOW": _fam_why("SOURCE_FLOW", fc.get("SOURCE_FLOW") or {}),
                "why_HARMONIC": _fam_why("HARMONIC_SOURCE", fc.get("HARMONIC_SOURCE") or {}),
                "why_SPECTRAL": _fam_why("SPECTRAL_WEIGHT", fc.get("SPECTRAL_WEIGHT") or {}),
                "why_CONTACT": _fam_why("CONTACT", fc.get("CONTACT") or {}),
            }
        )

    # Top head segments
    top_head = sorted(
        usable,
        key=lambda r: float(r.get("head_raw_evidence") or 0),
        reverse=True,
    )[:10]

    f0s = [float(r.get("f0_hz") or 0) for r in usable if r.get("f0_hz")]

    return {
        "sample": sample_id,
        "usable_segments": total_usable,
        "total_segments": len(segs),
        "f0_range": (min(f0s), max(f0s)) if f0s else None,
        "index": idx,
        "chest_display": ratios.get("chest_ratio"),
        "head_display": ratios.get("head_ratio"),
        "vt_display": vt.get("display_name"),
        "vt_type_id": vt.get("type_id"),
        "source_balance": (vt.get("source_balance") or {}).get("balance_class"),
        "register_strategy": (vt.get("register_strategy") or {}).get("status"),
        "register_sufficiency": (vt.get("bridge") or {}).get("register_sufficiency"),
        "register_transitions": len(reg_trans),
        "effort_severity": effort.get("severity"),
        "family_mass": fam_mass,
        "total_head_mass": round(total_head, 3),
        "total_chest_mass": round(total_chest, 3),
        "stats": stats,
        "neutral_collapse": collapse,
        "baseline_modes_sample": baseline_modes,
        "source_family_head_segments": src_head,
        "high_confidence_head_like": high_conf_head,
        "high_confidence_head_like_alt": high_conf_head_alt,
        "register_confirmed_head_segments": reg_conf_head,
        "conflicting_segments": len(conflicts),
        "conflict_details": conflicts[:8],
        "ablation": ablation,
        "segments": segment_rows,
        "top_head_segments": [
            {
                "time": f"{r.get('start_sec')}-{r.get('end_sec')}",
                "f0": r.get("f0_hz"),
                "band": r.get("pitch_band"),
                "index": r.get("head_chest_index"),
                "head_mass": r.get("head_raw_evidence"),
                "why": _fam_why(
                    "HARMONIC",
                    (r.get("family_contribution") or {}).get("HARMONIC_SOURCE") or {},
                )
                or _fam_why(
                    "SOURCE",
                    (r.get("family_contribution") or {}).get("SOURCE_FLOW") or {},
                ),
            }
            for r in top_head
        ],
    }


def _primary_head_contributor(fam_mass: dict[str, Any]) -> str:
    best = max(
        fam_mass.items(),
        key=lambda kv: float(kv[1].get("head") or 0),
    )
    return best[0] if float(best[1].get("head") or 0) > 0 else "NONE"


def print_report(data: dict[str, Any]) -> None:
    print(f"\n{'='*60}")
    print(f"SAMPLE: {data['sample']}")
    print(f"usable segments: {data['usable_segments']} / {data['total_segments']}")
    if data.get("f0_range"):
        print(f"F0 range: {data['f0_range'][0]:.1f} – {data['f0_range'][1]:.1f}")
    print(f"index: {data['index']}")
    print(f"Chest/Head display: {data['chest_display']} / {data['head_display']}")
    print(f"VT: {data['vt_display']} ({data['vt_type_id']})")
    st = data.get("stats") or {}
    print(f"mean_family_agreement: {st.get('mean_family_agreement')}")
    print(f"global_ratio_directionality: {st.get('global_ratio_directionality')}")
    print(f"neutral_collapse: {data.get('neutral_collapse')}")
    print(f"register transitions: {data.get('register_transitions')}")
    print(f"source-family HEAD segments: {data['source_family_head_segments']}/{data['usable_segments']}")
    print(f"high-confidence HEAD-like: {data['high_confidence_head_like']}/{data['usable_segments']}")
    print(f"register-confirmed HEAD: {data['register_confirmed_head_segments']}")
    print(f"conflicting segments: {data['conflicting_segments']}/{data['usable_segments']}")

    fm = data["family_mass"]
    th = data["total_head_mass"]
    print("\nHEAD MASS BY FAMILY:")
    for fid in ("SOURCE_FLOW", "HARMONIC_SOURCE", "SPECTRAL_WEIGHT", "CONTACT"):
        h = fm[fid]["head"]
        c = fm[fid]["chest"]
        share = (h / th * 100) if th > 0 else 0
        print(f"  {fid}: head={h:.3f} chest={c:.3f} head_share={share:.1f}%")
    print(f"PRIMARY HEAD CONTRIBUTOR: {_primary_head_contributor(fm)}")

    print("\nABLATION:")
    for k, v in data.get("ablation", {}).items():
        print(f"  {k}: index={v.get('index')} chest={v.get('chest_ratio')} head={v.get('head_ratio')}")

    print("\nSEGMENTS (summary):")
    for s in data.get("segments", []):
        print(
            f"  {s['start_sec']:.1f}-{s['end_sec']:.1f}s "
            f"f0={s['f0_hz']:.0f} idx={s['head_chest_index']:.3f} "
            f"SF={s['SOURCE_FLOW']} HF={s['HARMONIC_SOURCE']} "
            f"SP={s['SPECTRAL_WEIGHT']} CT={s['CONTACT']} "
            f"agree={s['family_agreement']}"
        )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", default="목잡이")
    ap.add_argument("--compare", default="호흡많고헤드")
    ap.add_argument("--all-anchors", action="store_true")
    args = ap.parse_args()

    out_dir = ROOT / "runtime" / "audits" / "head_chest"
    out_dir.mkdir(parents=True, exist_ok=True)

    names = list(ANCHORS.keys()) if args.all_anchors else [args.sample]
    if args.compare and args.compare not in names:
        names.append(args.compare)

    results = []
    for name in names:
        path = ANCHORS.get(name)
        if not path or not path.exists():
            print(f"NOT AVAILABLE: {name}")
            continue
        data = analyze_sample(path, name)
        results.append(data)
        print_report(data)

        # CSV
        csv_path = out_dir / f"{name}_segments.csv"
        if data.get("segments"):
            with csv_path.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(data["segments"][0].keys()))
                w.writeheader()
                w.writerows(data["segments"])
        json_path = out_dir / f"{name}_summary.json"
        json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    if len(results) >= 2:
        a = next((r for r in results if r["sample"] == args.sample), results[0])
        b = next((r for r in results if r["sample"] == args.compare), results[-1])
        print(f"\n{'='*60}")
        print(f"COMPARE: {a['sample']} vs {b['sample']}")
        print(f"  index: {a['index']} vs {b['index']}")
        print(f"  head mass: {a['total_head_mass']} vs {b['total_head_mass']}")
        print(f"  agreement: {a['stats'].get('mean_family_agreement')} vs {b['stats'].get('mean_family_agreement')}")
        pa = _primary_head_contributor(a["family_mass"])
        pb = _primary_head_contributor(b["family_mass"])
        print(f"  primary head contributor: {pa} vs {pb}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
