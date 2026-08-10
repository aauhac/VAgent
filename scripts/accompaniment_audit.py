#!/usr/bin/env python3
"""CSV audit: vocals vs no_vocals transitions vs register decisions."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    out = ROOT / "runtime" / "accompaniment_audit"
    out.mkdir(parents=True, exist_ok=True)
    sample = next(
        (
            p
            for p in ROOT.iterdir()
            if p.suffix.lower() in {".m4a", ".mp3", ".wav"} and p.stat().st_size > 50_000
        ),
        None,
    )
    if not sample:
        print("No sample")
        return 0

    from audio_analyzer.pipeline import analyze_audio
    from audio_analyzer.vocal_function.evidence_gate import (
        accompaniment_contamination_at,
        spectral_transition_score,
    )
    import soundfile as sf
    import numpy as np

    rid = "accomp_audit"
    result = analyze_audio(
        str(sample),
        output_dir=str(out / "runs"),
        recording_id=rid,
        separate=True,
        build_preview=False,
    )
    sep = (result.get("audio") or {}).get("separation") or {}
    vocals = sep.get("vocals_path") or (result.get("audio") or {}).get("analysis_wav_path")
    no_v = sep.get("no_vocals_path")
    if not vocals or not no_v:
        print("missing stems", vocals, no_v)
        return 1
    yv, srv = sf.read(vocals, always_2d=False)
    yn, srn = sf.read(no_v, always_2d=False)
    if getattr(yv, "ndim", 1) > 1:
        yv = np.mean(yv, axis=1)
    if getattr(yn, "ndim", 1) > 1:
        yn = np.mean(yn, axis=1)

    vf = result.get("vocal_function_profile") or {}
    reg = (vf.get("dimensions") or {}).get("register_configuration") or {}
    events = (reg.get("profile") or {}).get("events") or []
    rejected = (reg.get("profile") or {}).get("rejected_events") or []

    rows = []
    for e in events + rejected:
        start = float(e.get("start_sec") or 0)
        end = float(e.get("end_sec") or start + 1)
        cont = accompaniment_contamination_at(yv, yn, int(srv), start, end)
        rows.append(
            {
                "start_sec": start,
                "end_sec": end,
                "rejected": e.get("rejected", False),
                "reason_code": e.get("reason_code") or ("ACCEPTED" if not e.get("rejected") else ""),
                "detail": e.get("detail"),
                "vocals_transition": cont["vocals_transition"],
                "no_vocals_transition": cont["no_vocals_transition"],
                "accompaniment_match": cont["accompaniment_match"],
                "contamination": cont["possible_accompaniment_contamination"],
            }
        )

    csv_path = out / "register_vs_accomp.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        if rows:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    (out / "meta.json").write_text(
        json.dumps(
            {"sample": sample.name, "n_accepted": len(events), "n_rejected": len(rejected)},
            indent=2,
        ),
        encoding="utf-8",
    )
    print("wrote", csv_path, "accepted", len(events), "rejected", len(rejected))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
