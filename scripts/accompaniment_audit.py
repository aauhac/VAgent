#!/usr/bin/env python3
"""CSV audit: vocals vs no_vocals transitions vs register decisions (time-aligned)."""

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
    from audio_analyzer.vocal_function.alignment import slice_aligned_stems
    from audio_analyzer.vocal_function.evidence_gate import accompaniment_contamination_at
    import soundfile as sf
    import numpy as np

    rid = "accomp_audit"
    result = analyze_audio(
        str(sample),
        output_dir=str(out / "runs"),
        recording_id=rid,
        separate=True,
        analysis_mode="FUNCTIONAL",
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
    yv = np.asarray(yv, dtype=np.float32)
    yn = np.asarray(yn, dtype=np.float32)
    sr = int(srv)

    time_ctx = result.get("time_context") or (result.get("audio") or {}).get("time_context") or {}
    origin = float(time_ctx.get("analysis_time_origin_sec") or 0)
    clip_end = float(time_ctx.get("analysis_clip_end_sec") or (len(yv) / sr))
    if time_ctx.get("truncated"):
        aligned = slice_aligned_stems(
            y_vocals_full=yv,
            y_no_vocals_full=yn,
            sr=sr,
            start_sec=origin,
            end_sec=clip_end,
        )
        yv_c = aligned["vocals_clip"]
        yn_c = aligned["no_vocals_clip"]
    else:
        yv_c, yn_c = yv, yn

    vf = result.get("vocal_function_profile") or {}
    reg = (vf.get("dimensions") or {}).get("register_configuration") or {}
    events = (reg.get("profile") or {}).get("events") or []
    rejected = (reg.get("profile") or {}).get("rejected_events") or []

    rows = []
    for e in events + rejected:
        local_start = float(e.get("local_start_sec", e.get("start_sec") or 0))
        local_end = float(e.get("local_end_sec", e.get("end_sec") or local_start + 1))
        original_start = float(e.get("original_start_sec") or (origin + local_start))
        original_end = float(e.get("original_end_sec") or (origin + local_end))
        cont = accompaniment_contamination_at(yv_c, yn_c, sr, local_start, local_end)
        ve = e.get("validity") or {}
        rows.append(
            {
                "local_start": local_start,
                "local_end": local_end,
                "original_start": original_start,
                "original_end": original_end,
                "vocal_transition": cont["vocals_transition"],
                "no_vocal_transition": cont["no_vocals_transition"],
                "vocal_dominance": ve.get("vocal_dominance"),
                "accomp_match": cont["accompaniment_match"],
                "decision": "REJECT" if e.get("rejected") else "ACCEPT",
                "reject_reason": e.get("reason_code") or e.get("detail") or "",
            }
        )

    csv_path = out / "register_vs_accomp.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        if rows:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        else:
            f.write(
                "local_start,original_start,vocal_transition,no_vocal_transition,"
                "vocal_dominance,accomp_match,decision,reject_reason\n"
            )
    (out / "meta.json").write_text(
        json.dumps(
            {
                "sample": sample.name,
                "n_accepted": len(events),
                "n_rejected": len(rejected),
                "time_origin_sec": origin,
                "truncated": time_ctx.get("truncated"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print("wrote", csv_path, "accepted", len(events), "rejected", len(rejected))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
