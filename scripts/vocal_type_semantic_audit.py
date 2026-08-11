#!/usr/bin/env python3
"""Semantic Head/Chest audit with family ablation + CSV exports (v1.2)."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _write_segments_csv(path: Path, rows: list[dict]) -> None:
    fields = [
        "start_sec",
        "end_sec",
        "f0_hz",
        "rms",
        "pitch_band",
        "status",
        "head_chest_index",
        "chest_raw_evidence",
        "head_raw_evidence",
        "evidence_mass",
        "directionality",
        "family_agreement",
        "FLOW_signed",
        "HARMONIC_signed",
        "CONTACT_signed",
        "SPECTRAL_signed",
        "FLOW_status",
        "HARMONIC_status",
        "CONTACT_status",
        "SPECTRAL_status",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            fam = r.get("family_contribution") or {}
            signed = r.get("signed_family_votes") or {}
            w.writerow(
                {
                    "start_sec": r.get("start_sec"),
                    "end_sec": r.get("end_sec"),
                    "f0_hz": r.get("f0_hz"),
                    "rms": r.get("rms"),
                    "pitch_band": r.get("pitch_band"),
                    "status": r.get("status"),
                    "head_chest_index": r.get("head_chest_index"),
                    "chest_raw_evidence": r.get("chest_raw_evidence"),
                    "head_raw_evidence": r.get("head_raw_evidence"),
                    "evidence_mass": r.get("evidence_mass"),
                    "directionality": r.get("directionality"),
                    "family_agreement": r.get("family_agreement"),
                    "FLOW_signed": signed.get("SOURCE_FLOW"),
                    "HARMONIC_signed": signed.get("HARMONIC_SOURCE"),
                    "CONTACT_signed": signed.get("CONTACT"),
                    "SPECTRAL_signed": signed.get("SPECTRAL_WEIGHT"),
                    "FLOW_status": (fam.get("SOURCE_FLOW") or {}).get("status"),
                    "HARMONIC_status": (fam.get("HARMONIC_SOURCE") or {}).get("status"),
                    "CONTACT_status": (fam.get("CONTACT") or {}).get("status"),
                    "SPECTRAL_status": (fam.get("SPECTRAL_WEIGHT") or {}).get("status"),
                }
            )


def analyze(path: Path, sample_id: str, out: Path) -> dict:
    from audio_analyzer.coach_profile.head_chest import family_ablation
    from audio_analyzer.pipeline import analyze_audio

    rid = f"anchor_{sample_id}"[:40]
    result = analyze_audio(
        str(path),
        output_dir=str(out / "runs"),
        recording_id=rid,
        separate=False,
        analysis_mode="FUNCTIONAL",
        input_mode="VOCAL_ONLY",
        build_preview=False,
    )
    vf = result.get("vocal_function_profile") or {}
    vt = vf.get("vocal_type_profile") or {}
    # freeze before any human notes
    freeze = {
        "sample_id": sample_id,
        "audio_path": str(path),
        "vocal_type_profile": vt,
        "dimensions": vf.get("dimensions") or {},
        "criteria_matrix": vf.get("criteria_matrix") or [],
        "coaching_decision": vf.get("coaching_decision") or {},
    }
    (out / f"{sample_id}_freeze.json").write_text(
        json.dumps(freeze, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    segs = vt.get("segment_scores") or []
    _write_segments_csv(out / f"{sample_id}_segments.csv", segs)

    abl = {}
    if segs:
        from audio_analyzer.coach_profile.head_chest import index_to_ratios, weighted_index

        def _ablate(disable: set[str]):
            rows = []
            for r in segs:
                rr = dict(r)
                fam = dict(rr.get("family_contribution") or {})
                chest = head = 0.0
                for fid, info in fam.items():
                    if fid in disable:
                        continue
                    chest += float(info.get("chest") or 0)
                    head += float(info.get("head") or 0)
                mass = chest + head
                rr["chest_raw_evidence"] = chest
                rr["head_raw_evidence"] = head
                rr["evidence_mass"] = mass
                src_left = any(
                    fid not in disable and fam.get(fid, {}).get("status") in ("CHEST", "HEAD")
                    for fid in ("SOURCE_FLOW", "HARMONIC_SOURCE")
                )
                if mass >= 0.55 and src_left:
                    rr["head_chest_index"] = head / mass
                else:
                    rr["head_chest_index"] = None
                rows.append(rr)
            return index_to_ratios(weighted_index(rows))

        abl = {"FULL": index_to_ratios(weighted_index(segs))}
        for fid in ("SOURCE_FLOW", "HARMONIC_SOURCE", "CONTACT", "SPECTRAL_WEIGHT"):
            abl[f"without_{fid}"] = _ablate({fid})

    with (out / f"{sample_id}_family_ablation.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["condition", "available", "chest_ratio", "head_ratio", "index"])
        for k, v in abl.items():
            w.writerow([k, v.get("available"), v.get("chest_ratio"), v.get("head_ratio"), v.get("index")])

    br = vt.get("bridge") or {}
    with (out / f"{sample_id}_transitions.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["kind", "type", "start_sec", "end_sec"])
        for e in vt.get("local_register_events") or []:
            w.writerow(["local_event", e.get("type"), e.get("start_sec"), e.get("end_sec")])
        for o in br.get("transition_opportunities") or []:
            w.writerow(["opportunity", "TRANSITION_OPP", o.get("start_sec"), o.get("end_sec")])

    hc = vt.get("head_chest") or {}
    ev = vt.get("evidence") or {}
    print(f"\n=== {sample_id} ===")
    print(f"TYPE {vt.get('global_type') or vt.get('type_id')} | {vt.get('display_name')}")
    print(f"Chest/Head {hc.get('chest_ratio')}/{hc.get('head_ratio')} conf={vt.get('confidence')}")
    print(
        f"mass={ev.get('mass')} global_ratio_dir={ev.get('global_ratio_directionality')} "
        f"agree={ev.get('family_agreement')}"
    )
    print(f"signed={ev.get('mean_signed_family_votes')}")
    print(f"bridge={br.get('type')} split_ok={(br.get('split_eligibility') or {}).get('eligible')}")
    print(f"local={vt.get('local_register_events')}")
    print(f"ablation={abl}")
    return freeze


def contrast(a: dict, b: dict, out: Path) -> None:
    def pack(f):
        vt = f.get("vocal_type_profile") or {}
        hc = vt.get("head_chest") or {}
        ev = vt.get("evidence") or {}
        br = vt.get("bridge") or {}
        fam = ev.get("family_summary") or {}
        signed = ev.get("mean_signed_family_votes") or {}
        local = vt.get("local_register_events") or []
        return {
            "id": f.get("sample_id"),
            "chest": hc.get("chest_ratio"),
            "head": hc.get("head_ratio"),
            "mass": ev.get("mass"),
            "gdir": ev.get("global_ratio_directionality"),
            "agree": ev.get("family_agreement"),
            "flow": signed.get("SOURCE_FLOW"),
            "harm": signed.get("HARMONIC_SOURCE"),
            "contact": signed.get("CONTACT"),
            "spec": signed.get("SPECTRAL_WEIGHT"),
            "flow_dom": (fam.get("SOURCE_FLOW") or {}).get("dominant"),
            "harm_dom": (fam.get("HARMONIC_SOURCE") or {}).get("dominant"),
            "bridge": br.get("type"),
            "type": vt.get("global_type") or vt.get("type_id"),
            "n_pull": sum(1 for e in local if e.get("type") == "LOCAL_CHEST_PULL"),
            "n_break": sum(1 for e in local if e.get("type") == "LOCAL_ABRUPT_BREAK"),
            "n_opp": br.get("n_transition_opportunities"),
            "prev": br.get("break_prevalence"),
        }

    pa, pb = pack(a), pack(b)
    rows = [
        ("Global Chest", "chest"),
        ("Global Head", "head"),
        ("Mass", "mass"),
        ("Global directionality", "gdir"),
        ("Family agreement", "agree"),
        ("FLOW signed vote", "flow"),
        ("HARMONIC signed vote", "harm"),
        ("CONTACT signed vote", "contact"),
        ("SPECTRAL signed vote", "spec"),
        ("FLOW dominant", "flow_dom"),
        ("HARMONIC dominant", "harm_dom"),
        ("Bridge global", "bridge"),
        ("Local chest-pull count", "n_pull"),
        ("Local break count", "n_break"),
        ("Transition opportunities", "n_opp"),
        ("Break prevalence", "prev"),
        ("Global type", "type"),
    ]
    print("\nHEAD/CHEST SEMANTIC CONTRAST")
    print(f"{'':28} {pa['id']:>18} {pb['id']:>18}")
    with (out / "contrast.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["metric", pa["id"], pb["id"]])
        for lab, k in rows:
            print(f"{lab:28} {str(pa[k]):>18} {str(pb[k]):>18}")
            w.writerow([lab, pa[k], pb[k]])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", action="append", default=[])
    ap.add_argument("--sample-id", action="append", default=[])
    ap.add_argument("--out", default=str(ROOT / "runtime" / "audits" / "vocal_type"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    freezes = []
    for i, audio in enumerate(args.audio):
        sid = args.sample_id[i] if i < len(args.sample_id) else f"s{i}"
        freezes.append(analyze(Path(audio), sid, out))
    if len(freezes) >= 2:
        contrast(freezes[0], freezes[1], out)
    (out / "summary.json").write_text(json.dumps(freezes, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
