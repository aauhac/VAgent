"""
scripts/song_score_sanity.py
----------------------------
Compare song scoring on local samples (v2 vs v3) and warn on saturation.
Not ground-truth evaluation.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from audio_analyzer.preprocessing.audio_io import load_analysis_audio
from audio_analyzer.features.pitch import extract_pitch_features
from audio_analyzer.features.phonation import extract_phonation_features
from audio_analyzer.features.waveform import extract_waveform_features
from audio_analyzer.legacy.acoustic_metrics import compute_core_acoustic_metrics
from audio_analyzer.quality import evaluate_quality
from audio_analyzer.scoring.score_v2 import compute_score_v2
from audio_analyzer.scoring.score_v3 import compute_score_v3


CANDIDATES = ["옥탑방.m4a", "drowning.m4a", "bluemoon.m4a", "movie.m4a", "Lyrics.mp3"]


def _pick(n=4):
    found = []
    for name in CANDIDATES:
        p = ROOT / name
        if p.exists():
            found.append(p)
    for p in sorted(ROOT.glob("*.m4a")) + sorted(ROOT.glob("*.mp3")):
        if p not in found:
            found.append(p)
        if len(found) >= n:
            break
    return found[:n]


def _run_one(path: Path, work: Path):
    work.mkdir(parents=True, exist_ok=True)
    y, sr, _ = load_analysis_audio(str(path), work, sample_rate=22050)
    # Sanity uses up to ~45s mid clip for speed (full song still scored in product pipeline)
    max_samples = int(sr * 45)
    if len(y) > max_samples:
        start = max(0, len(y) // 2 - max_samples // 2)
        y = y[start : start + max_samples]
    pitch = extract_pitch_features(y, sr)
    phonation = extract_phonation_features(y, sr, pitch)
    waveform = extract_waveform_features(y, sr)
    acoustic = compute_core_acoustic_metrics(y, sr)
    quality = evaluate_quality(
        y,
        sr,
        voiced_ratio=pitch.get("voiced_ratio"),
        voiced_duration_sec=(pitch.get("voiced_ratio") or 0) * (len(y) / sr),
        rumble_ratio_db=acoustic.get("rumble_ratio_db"),
    )
    if quality["status"] == "fail":
        return {"file": path.name, "quality": "fail"}
    v2 = compute_score_v2(
        phonation=phonation,
        acoustic=acoustic,
        waveform=waveform,
        quality=quality,
        source_mode="raw",
    )
    v3 = compute_score_v3(
        phonation=phonation,
        acoustic=acoustic,
        waveform=waveform,
        quality=quality,
        source_mode="raw",
        y=y,
        sr=sr,
    )
    return {
        "file": path.name,
        "quality": quality.get("status"),
        "before_v2": {
            "overall": v2.get("overall"),
            "areas": {
                a["area_id"]: {"score": a.get("score"), "status": a.get("status")}
                for a in v2.get("areas") or []
            },
        },
        "after_v3": {
            "overall": v3.get("overall"),
            "overall_coverage": v3.get("overall_coverage"),
            "areas": {
                a["area_id"]: {
                    "score": a.get("score"),
                    "status": a.get("status"),
                    "coverage": a.get("coverage"),
                    "worst": (a.get("temporal") or {}).get("worst"),
                    "ceiling": a.get("score_ceiling"),
                }
                for a in v3.get("areas") or []
            },
        },
    }


def main() -> int:
    samples = _pick(4)
    if not samples:
        print("NO_SAMPLES")
        return 1
    out_dir = ROOT / "runtime" / "song_score_sanity"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for p in samples:
        try:
            rows.append(_run_one(p, out_dir / p.stem))
            print("ok", p.name)
        except Exception as exc:  # noqa: BLE001
            rows.append({"file": p.name, "error": str(exc)})
            print("err", p.name, exc)

    # Saturation stats
    def count_axes(key_path, pred):
        n = 0
        for r in rows:
            block = r.get(key_path) or {}
            for a in (block.get("areas") or {}).values():
                if pred(a):
                    n += 1
        return n

    before_100 = count_axes("before_v2", lambda a: a.get("score") == 100)
    after_100 = count_axes("after_v3", lambda a: a.get("score") == 100)
    before_95 = count_axes("before_v2", lambda a: (a.get("score") or 0) >= 95)
    after_95 = count_axes("after_v3", lambda a: (a.get("score") or 0) >= 95)
    unknown = count_axes("after_v3", lambda a: a.get("status") == "unknown" or a.get("score") is None)

    warnings = []
    n_samples = max(1, len([r for r in rows if "after_v3" in r]))
    if after_100 >= n_samples * 2:
        warnings.append("SCORE_SATURATION_WARNING: axis 100 too frequent")
    if after_95 >= n_samples * 3:
        warnings.append("SCORE_SATURATION_WARNING: 95+ too frequent")

    summary = {
        "samples": rows,
        "counts": {
            "before_100": before_100,
            "after_100": after_100,
            "before_95_plus": before_95,
            "after_95_plus": after_95,
            "after_unknown": unknown,
        },
        "warnings": warnings,
    }
    path = out_dir / "summary.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary["counts"], ensure_ascii=False))
    print("warnings", warnings)
    print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
