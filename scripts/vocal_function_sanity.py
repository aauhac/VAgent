#!/usr/bin/env python3
"""Vocal Function v2 sanity on local samples (or synthetic fallback)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from audio_analyzer.vocal_function import compute_vocal_function_profile  # noqa: E402


def _synth(name: str, y: np.ndarray, sr: int = 22050) -> dict:
    pitch = {
        "frame_f0": [
            {"time_sec": float(t), "f0_hz": 220.0 + (40 if "high" in name else 0)}
            for t in np.linspace(0, len(y) / sr - 0.01, 80)
        ],
        "voiced_ratio": 0.9,
    }
    return compute_vocal_function_profile(
        y=y.astype(np.float32),
        sr=sr,
        pitch=pitch,
        acoustic={},
        quality={"status": "pass"},
        optional_analysis={"vibrato": {"available": False}},
    )


def main() -> int:
    out = ROOT / "runtime" / "vocal_function_sanity"
    out.mkdir(parents=True, exist_ok=True)
    samples = []
    for p in ROOT.iterdir():
        if p.suffix.lower() in {".m4a", ".mp3", ".wav"} and p.stat().st_size > 50_000:
            samples.append(p)
    rows = []
    if samples:
        from audio_analyzer.pipeline import analyze_audio

        for p in samples[:3]:
            rid = f"vf_{p.stem}"[:40]
            print("analyzing", p.name)
            try:
                result = analyze_audio(
                    str(p),
                    output_dir=str(out / "runs"),
                    recording_id=rid,
                    separate=False,
                    build_preview=False,
                )
                profile = result.get("vocal_function_profile") or {}
            except Exception as exc:  # noqa: BLE001
                print("fail", p.name, exc)
                continue
            rows.append(_row(p.name, profile))
            _write(out, rid, profile)
    else:
        sr = 22050
        t = np.arange(sr * 4) / sr
        cases = {
            "clean_mid": 0.2 * np.sin(2 * np.pi * 220 * t),
            "noisy_leakageish": 0.12 * np.sin(2 * np.pi * 200 * t) + 0.08 * np.random.randn(len(t)),
            "bright_firmish": (
                0.2 * np.sin(2 * np.pi * 260 * t)
                + 0.12 * np.sin(2 * np.pi * 520 * t)
                + 0.08 * np.sin(2 * np.pi * 780 * t)
            ),
        }
        for name, y in cases.items():
            profile = _synth(name, y, sr)
            rows.append(_row(name, profile))
            _write(out, name, profile)

    statuses = [tuple(sorted((k, r.get(k)) for k in r if k.endswith("_status"))) for r in rows]
    if len(statuses) >= 3 and len(set(statuses)) == 1:
        for r in rows:
            r.setdefault("warnings", []).append("FUNCTION_PROFILE_COLLAPSE_WARNING")

    (out / "summary.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


def _row(name: str, profile: dict) -> dict:
    dims = profile.get("dimensions") or {}
    row = {
        "file": name,
        "available": profile.get("available"),
        "valid_segments": profile.get("valid_segment_count"),
        "warnings": list(profile.get("warnings") or []),
        "contact_effort_plane": profile.get("contact_effort_plane"),
    }
    for k, d in dims.items():
        row[f"{k}_status"] = d.get("status")
        row[f"{k}_conf"] = d.get("confidence_label")
    return row


def _write(out: Path, rid: str, profile: dict) -> None:
    slim = {k: v for k, v in profile.items() if k != "scientific_debug"}
    (out / f"{rid}_profile.json").write_text(
        json.dumps(slim, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    raise SystemExit(main())
