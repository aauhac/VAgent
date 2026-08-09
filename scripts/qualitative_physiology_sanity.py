"""
scripts/qualitative_physiology_sanity.py
----------------------------------------
Run physiology observers + inference on a few local singing samples.
Not ground-truth physiology — qualitative DSP/rule sanity only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from audio_analyzer.preprocessing.audio_io import load_analysis_audio
from audio_analyzer.physiology.observations import observe_sustained_task
from audio_analyzer.physiology.inference import infer_mechanisms
from audio_analyzer.physiology.report import build_premium_report, public_premium_report


CANDIDATES = [
    "옥탑방.m4a",
    "drowning.m4a",
    "bluemoon.m4a",
    "movie.m4a",
    "Lyrics.mp3",
]


def _pick_samples(n: int = 4) -> list[Path]:
    found: list[Path] = []
    for name in CANDIDATES:
        p = ROOT / name
        if p.exists():
            found.append(p)
    if len(found) < n:
        for p in sorted(ROOT.glob("*.m4a")) + sorted(ROOT.glob("*.mp3")):
            if p not in found:
                found.append(p)
            if len(found) >= n:
                break
    return found[:n]


def main() -> int:
    samples = _pick_samples(4)
    if not samples:
        print("NO_SAMPLES")
        return 1

    out_dir = ROOT / "runtime" / "qualitative_sanity"
    out_dir.mkdir(parents=True, exist_ok=True)
    summaries = []

    for sample in samples:
        work = out_dir / sample.stem
        work.mkdir(parents=True, exist_ok=True)
        try:
            y, sr, _ = load_analysis_audio(str(sample), work, sample_rate=22050)
        except Exception as exc:  # noqa: BLE001
            summaries.append({"file": sample.name, "error": str(exc)})
            continue

        # Use middle 4s as pseudo sustain for sanity (not a real diagnostic task)
        n = len(y)
        if n < sr * 3:
            summaries.append({"file": sample.name, "error": "too_short"})
            continue
        start = max(0, n // 2 - 2 * sr)
        clip = y[start : start + int(4.0 * sr)].astype(np.float32)

        t_a = observe_sustained_task(clip, sr, task_id="sustain_a", attempt=1)
        t_i = observe_sustained_task(clip, sr, task_id="sustain_i", attempt=1)
        mechs = infer_mechanisms([t_a, t_i])
        report = public_premium_report(
            build_premium_report(
                session_id=f"sanity_{sample.stem}",
                task_results=[t_a, t_i],
                include_scientific_debug=False,
            )
        )

        primary = report.get("reliable_findings") or report["sections"]["B_reliable"]["items"]
        uncertain = report.get("uncertain_findings") or report["sections"].get("B_uncertain", {}).get("items") or []
        summaries.append(
            {
                "file": sample.name,
                "duration_clip_sec": round(len(clip) / sr, 2),
                "primary": [
                    {
                        "id": p["mechanism_id"],
                        "name": p["display_name"],
                        "status": p["status"],
                        "status_label": p.get("status_label"),
                        "confidence_label": p.get("confidence_label"),
                    }
                    for p in primary
                ],
                "uncertain": [x["display_name"] for x in uncertain],
                "needs_more": [x["display_name"] for x in report["sections"]["B_needs_more"]["items"]],
                "unknown_is_ok": any(p["status"] == "unknown" for p in primary) or len(uncertain) > 0,
                "contact_never_high": all(
                    p.get("confidence_label") != "높음"
                    for p in primary
                    if p["mechanism_id"] == "phonation_contact_pattern"
                ),
            }
        )
        print(sample.name, "→", [f"{p['display_name']}:{p['status_label']}" for p in primary])

    out_path = out_dir / "summary.json"
    out_path.write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
