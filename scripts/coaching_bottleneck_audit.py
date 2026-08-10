#!/usr/bin/env python3
"""Audit coaching bottleneck decision for one analysis or local sample."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    out = ROOT / "runtime" / "coaching_bottleneck_audit"
    out.mkdir(parents=True, exist_ok=True)
    samples = [
        p
        for p in ROOT.iterdir()
        if p.suffix.lower() in {".m4a", ".mp3", ".wav"} and p.stat().st_size > 50_000
    ][:2]
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
            build_preview=False,
        )
        vf = result.get("vocal_function_profile") or {}
        decision = vf.get("coaching_decision") or {}
        row = {
            "file": p.name,
            "primary_bottleneck": (decision.get("primary_bottleneck") or {}).get("id"),
            "secondary": [
                b.get("id") for b in (decision.get("secondary_bottlenecks") or [])
            ],
            "preserve": [p_.get("label") for p_ in (decision.get("preserve") or [])],
            "modify": [m.get("label") for m in (decision.get("modify") or [])],
            "top_episode": decision.get("target_episode"),
            "best_self": decision.get("best_self_reference"),
            "exercises": [
                e.get("exercise_id") for e in (decision.get("exercise_plan") or [])
            ],
            "success_criteria": decision.get("success_criteria"),
            "n_episodes": len(vf.get("episodes") or []),
            "n_high_note_public": len(vf.get("high_note_events") or []),
            "rejected_register": len(
                ((vf.get("scientific_debug") or {}).get("rejected_register_events") or [])
            ),
            "has_no_vocals": (vf.get("scientific_debug") or {}).get("has_no_vocals_contrast"),
        }
        rows.append(row)
        (out / f"{rid}.json").write_text(
            json.dumps(
                {
                    "decision": decision,
                    "focus_episodes": vf.get("focus_episodes"),
                    "high_note_events": vf.get("high_note_events"),
                    "register": (vf.get("dimensions") or {}).get("register_configuration"),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    (out / "summary.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
