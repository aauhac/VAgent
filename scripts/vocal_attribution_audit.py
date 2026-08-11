#!/usr/bin/env python3
"""Vocal attribution / Primary target audit (v2.10)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True)
    ap.add_argument("--sample-id", default="sample")
    ap.add_argument("--out", default=str(ROOT / "runtime" / "audits" / "vocal_attribution_v210"))
    args = ap.parse_args()

    from audio_analyzer.pipeline import analyze_audio

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rid = f"va210_{args.sample_id}"[:48]
    result = analyze_audio(
        args.audio,
        output_dir=str(out / "runs"),
        recording_id=rid,
        separate=False,
        analysis_mode="FUNCTIONAL",
        input_mode="VOCAL_ONLY",
        build_preview=False,
    )
    vf = result.get("vocal_function_profile") or {}
    segs = (vf.get("scientific_debug") or {}).get("segments") or []
    eps = vf.get("episodes") or (vf.get("scientific_debug") or {}).get("episodes") or []
    coach = vf.get("coaching_decision") or {}
    dims = vf.get("dimensions") or {}

    seg_rows = []
    n_effort_valid = 0
    n_legacy_false = 0
    n_confirmed = n_uncertain = n_rejected = 0
    for s in segs:
        ve = s.get("vocal_evidence") or {}
        attr = ve.get("vocal_attribution") or {}
        state = attr.get("state") or ("VOCAL_CONFIRMED" if ve.get("vocal_specific") else "VOCAL_UNCERTAIN")
        from audio_analyzer.vocal_function.validity import dim_valid

        effort_ok = dim_valid(s, "effort")
        if effort_ok:
            n_effort_valid += 1
            if not ve.get("vocal_specific"):
                n_legacy_false += 1
        if state == "VOCAL_CONFIRMED":
            n_confirmed += 1
        elif state == "NON_VOCAL_REJECTED":
            n_rejected += 1
        else:
            n_uncertain += 1
        seg_rows.append(
            {
                "start": s.get("start_sec"),
                "end": s.get("end_sec"),
                "legacy_valid": s.get("valid"),
                "legacy_vocal_specific": ve.get("vocal_specific"),
                "attribution_state": state,
                "attribution_confidence": attr.get("confidence_score") or ve.get("vocal_attribution_confidence"),
                "vocal_dominance": ve.get("vocal_dominance"),
                "f0_conf": ve.get("f0_confidence"),
                "voicing_conf": ve.get("voicing_confidence"),
                "accompaniment_match": ve.get("accompaniment_match"),
                "positive_families": (attr.get("positive_families") or []),
                "negative_families": (attr.get("negative_families") or []),
                "effort_dim_valid": effort_ok,
            }
        )

    ep_rows = []
    for e in eps:
        v = (e.get("feature_matrix") or {}).get("validity") or {}
        ep_rows.append(
            {
                "episode_id": e.get("episode_id"),
                "type": e.get("type"),
                "legacy_vocal_specific": v.get("vocal_specific"),
                "attribution_state": v.get("vocal_attribution_state"),
                "episode_vocal_attribution": v.get("episode_vocal_attribution"),
                "claim_suitability": v.get("claim_suitability"),
            }
        )

    primary = coach.get("primary_bottleneck")
    payload = {
        "sample_id": args.sample_id,
        "engine_version": vf.get("engine_version"),
        "effort": (dims.get("vocal_effort_strain") or {}).get("profile"),
        "effort_status": (dims.get("vocal_effort_strain") or {}).get("status"),
        "breathiness": (dims.get("air_leakage_breathiness") or {}).get("status"),
        "roughness": (dims.get("phonation_regularity") or {}).get("status"),
        "selection_bias": {
            "n_effort_valid": n_effort_valid,
            "n_effort_valid_but_legacy_vocal_false": n_legacy_false,
            "n_members_new_confirmed": n_confirmed,
            "n_members_new_uncertain": n_uncertain,
            "n_members_rejected": n_rejected,
        },
        "segments": seg_rows,
        "episodes": ep_rows,
        "primary": (primary or {}).get("id") if isinstance(primary, dict) else primary,
        "primary_rejection_trace": coach.get("primary_rejection_trace") or [],
        "vocal_type": (vf.get("vocal_type_profile") or {}).get("engine_version"),
    }
    path = out / f"{args.sample_id}_attribution.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("sample_id", "effort_status", "primary", "selection_bias")}, indent=2, ensure_ascii=False))
    print("reject trace:")
    for r in payload["primary_rejection_trace"][:6]:
        print(" ", r.get("id"), r.get("reason"), r.get("episode_vocal_attribution"))
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
