#!/usr/bin/env python3
"""Run Vocal Quality sanity on local root audio samples."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from audio_analyzer.pipeline import analyze_audio  # noqa: E402


def main() -> int:
    out = ROOT / "runtime" / "vocal_quality_sanity"
    out.mkdir(parents=True, exist_ok=True)
    samples = sorted(
        [
            p
            for p in ROOT.iterdir()
            if p.suffix.lower() in {".m4a", ".mp3", ".wav"} and p.stat().st_size > 100_000
        ]
    )[:4]
    if not samples:
        print("No local samples found")
        return 0
    rows = []
    for p in samples:
        rid = f"vq_{p.stem}"[:40]
        print("analyzing", p.name)
        try:
            result = analyze_audio(
                str(p),
                output_dir=str(out / "runs"),
                recording_id=rid,
                separate=False,
                build_preview=False,
            )
        except Exception as exc:  # noqa: BLE001
            print("fail", p.name, exc)
            continue
        vq = result.get("vocal_quality_profile") or {}
        dims = vq.get("dimensions") or {}
        row = {
            "file": p.name,
            "available": vq.get("available"),
            "valid_segments": vq.get("valid_segment_count"),
            "warnings": vq.get("warnings"),
        }
        for k, d in dims.items():
            row[k] = d.get("status")
            row[f"{k}_conf"] = d.get("confidence_label")
        rows.append(row)
        (out / f"{rid}_profile.json").write_text(
            json.dumps(
                {k: v for k, v in vq.items() if k != "scientific_debug"},
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
