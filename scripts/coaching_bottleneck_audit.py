#!/usr/bin/env python3
"""Audit coaching bottleneck decision for local samples (v2.1)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _ep_row(e: dict) -> dict:
    fm = e.get("feature_matrix") or {}
    return {
        "episode_id": e.get("episode_id"),
        "type": e.get("type"),
        "local_start": e.get("local_start_sec", e.get("start_sec")),
        "local_end": e.get("local_end_sec", e.get("end_sec")),
        "original_start": e.get("original_start_sec"),
        "original_end": e.get("original_end_sec"),
        "phase_method": e.get("phase_method"),
        "cause_hint": e.get("cause_hint"),
        "concern": e.get("concern"),
        "vocal_confidence": ((e.get("members") or [{}])[0].get("validity") or {}).get(
            "vocal_confidence"
        )
        if e.get("members")
        else None,
        "accomp_match": ((e.get("members") or [{}])[0].get("validity") or {}).get(
            "accompaniment_match"
        )
        if e.get("members")
        else None,
        "contact_firmness": (fm.get("source") or {}).get("contact_firmness"),
        "effort": (fm.get("effort") or {}).get("strain_like"),
        "periodicity": (fm.get("regularity") or {}).get("periodicity"),
        "roughness": (fm.get("regularity") or {}).get("roughness"),
        "resonance_delta": (fm.get("resonance") or {}).get("energy_2_4k_delta"),
        "mfdr_norm": (fm.get("source") or {}).get("estimated_mfdr_norm_proxy"),
        "naq": (fm.get("source") or {}).get("estimated_naq"),
    }


def main() -> int:
    out = ROOT / "runtime" / "coaching_bottleneck_audit"
    out.mkdir(parents=True, exist_ok=True)
    samples = [
        p
        for p in ROOT.iterdir()
        if p.suffix.lower() in {".m4a", ".mp3", ".wav"} and p.stat().st_size > 50_000
    ][:3]
    if not samples:
        print("No samples")
        return 0

    from audio_analyzer.pipeline import analyze_audio

    rows = []
    for p in samples:
        rid = f"coach_{p.stem}"[:40]
        print("analyzing", p.name)
        result = analyze_audio(
            str(p),
            output_dir=str(out / "runs"),
            recording_id=rid,
            separate=True,
            analysis_mode="FUNCTIONAL",
            build_preview=False,
        )
        vf = result.get("vocal_function_profile") or {}
        decision = vf.get("coaching_decision") or {}
        plane = vf.get("contact_effort_plane") or {}
        primary = decision.get("primary_bottleneck") or {}
        row = {
            "file": p.name,
            "PRIMARY_BOTTLENECK": primary.get("id"),
            "CAUSE_FAMILY": primary.get("cause_family"),
            "TARGET_EPISODE": decision.get("target_episode"),
            "PRESERVE": [x.get("label") for x in (decision.get("preserve") or [])],
            "MODIFY": [x.get("label") for x in (decision.get("modify") or [])],
            "VOCAL_CONFIDENCE_QUALITY": vf.get("functional_quality"),
            "ACCOMPANIMENT_REJECT_COUNT": len(
                ((vf.get("scientific_debug") or {}).get("rejected_register_events") or [])
            ),
            "SELF_REFERENCE": decision.get("best_self_reference"),
            "co_occurrence": {
                "firm_n": plane.get("firm_segments"),
                "effort_n": plane.get("effort_segments"),
                "overlap_n": plane.get("firm_effort_overlap_segments"),
                "firm_without_effort_ratio": plane.get("firm_without_effort_ratio"),
                "effort_without_firm_ratio": plane.get("effort_without_firm_ratio"),
                "firm_high_strain_high": plane.get("firm_high_strain_high"),
            },
            "time_origin_sec": result.get("analysis_time_origin_sec"),
            "episodes": [_ep_row(e) for e in (vf.get("episodes") or [])[:12]],
            "hypotheses": [
                {
                    "id": h.get("id"),
                    "supporting_episode_ids": h.get("supporting_episode_ids"),
                    "confidence": h.get("confidence_label"),
                }
                for h in (decision.get("hypotheses") or [])
            ],
        }
        rows.append(row)
        (out / f"{rid}.json").write_text(
            json.dumps(row, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    (out / "summary.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
