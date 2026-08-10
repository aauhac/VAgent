#!/usr/bin/env python3
"""
scripts/discrimination_audit.py
--------------------------------
Hostile root-cause audit: why two recordings collide in Song Performance v3.

Usage:
  python scripts/discrimination_audit.py --a Lyrics.mp3 --b 옥탑방.m4a \\
      --output runtime/discrimination_audit

  python scripts/discrimination_audit.py \\
      --analysis-a 74cd88f992874f16bceed5a5bd2e6666 \\
      --analysis-b 8d528a74ae9e4061b381a68a86305d3b \\
      --output runtime/discrimination_audit_pair

Does NOT retune score thresholds. Exploratory only with small N.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Optional

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from audio_analyzer.audit.fingerprints import (  # noqa: E402
    dump_json,
    file_fingerprint,
    sha256_file,
    waveform_checksum,
)
from audio_analyzer.scoring import config_v3 as cfg  # noqa: E402
from audio_analyzer.scoring.helpers_v3 import score_abs_deviation, score_piecewise  # noqa: E402


RAW_EPS = 1e-6
RAW_REL_COLLISION = 0.02
SCORE_COLLISION = 0.55


def _load_analysis(analysis_id: str, runtime: Path) -> dict[str, Any]:
    path = runtime / analysis_id / "analysis.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _submetrics(analysis: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out = {}
    for area in (analysis.get("score") or {}).get("areas") or []:
        for sm in area.get("submetrics") or []:
            sid = sm.get("submetric_id")
            if sid:
                out[sid] = {**sm, "area_id": area.get("area_id"), "area_status": area.get("status")}
    return out


def _anchor_interval(value: Optional[float], anchors: list, *, lower_is_better: bool) -> str:
    if value is None or not anchors:
        return "n/a"
    ordered = sorted(anchors, key=lambda a: a[0])
    v = float(value)
    if v <= ordered[0][0]:
        return f"(-inf, {ordered[0][0]}]"
    if v >= ordered[-1][0]:
        return f"[{ordered[-1][0]}, +inf)"
    for i in range(len(ordered) - 1):
        if ordered[i][0] <= v <= ordered[i + 1][0]:
            return f"[{ordered[i][0]}, {ordered[i+1][0]}]"
    return "?"


def _map_known(sid: str, raw: Optional[float]) -> Optional[float]:
    if raw is None:
        return None
    v = float(raw)
    try:
        if sid == "sustain_pitch_stability":
            return score_piecewise(v, cfg.STABILITY_PITCH_ANCHORS, lower_is_better=True)
        if sid == "sustain_level_stability":
            return score_piecewise(v, cfg.STABILITY_LEVEL_ANCHORS, lower_is_better=True)
        if sid == "region_consistency":
            return score_piecewise(v, cfg.STABILITY_CONSISTENCY_STD_ANCHORS, lower_is_better=True)
        if sid == "unstable_region_ratio":
            return score_piecewise(v, cfg.STABILITY_UNSTABLE_RATIO_ANCHORS, lower_is_better=True)
        if sid == "spectral_projection":
            return score_piecewise(v, cfg.PROJECTION_SPR_ANCHORS, lower_is_better=True)
        if sid == "presence_prominence":
            return score_piecewise(v, cfg.PROJECTION_PROMINENCE_ANCHORS, lower_is_better=False)
        if sid == "weight_balance":
            return score_abs_deviation(v, cfg.RESONANCE_WEIGHT_CENTER, cfg.RESONANCE_ABS_DEV_ANCHORS)
        if sid == "mid_resonance_balance":
            return score_abs_deviation(v, cfg.RESONANCE_MOUTH_CENTER, cfg.RESONANCE_ABS_DEV_ANCHORS)
        if sid == "spectral_slope_balance":
            return score_abs_deviation(v, cfg.RESONANCE_SLOPE_CENTER, cfg.RESONANCE_ABS_DEV_ANCHORS)
        if sid == "global_dynamic_range":
            return score_abs_deviation(v, cfg.DYNAMIC_RANGE_CENTER, cfg.DYNAMIC_RANGE_DEV_ANCHORS)
        if sid == "local_dynamic_variation":
            return score_abs_deviation(v, cfg.LOCAL_DYN_CENTER, cfg.LOCAL_DYN_DEV_ANCHORS)
        if sid in ("smoothness", "abrupt_change_ratio"):
            return score_piecewise(v, cfg.SMOOTHNESS_ABRUPT_ANCHORS, lower_is_better=True)
    except Exception:
        return None
    return None


def _classify(raw_a, raw_b, score_a, score_b, area_status_a, area_status_b) -> str:
    if area_status_a == "unknown" and area_status_b == "unknown":
        return "INVALID_MEASUREMENT"
    if raw_a is None and raw_b is None:
        return "INVALID_MEASUREMENT"
    if raw_a is not None and raw_b is not None:
        abs_d = abs(float(raw_a) - float(raw_b))
        scale = max(abs(float(raw_a)), abs(float(raw_b)), RAW_EPS)
        rel = abs_d / scale
        raw_same = abs_d < RAW_EPS or rel < RAW_REL_COLLISION
    else:
        raw_same = False
        abs_d = None
        rel = None
    score_same = False
    if score_a is not None and score_b is not None:
        score_same = abs(float(score_a) - float(score_b)) < SCORE_COLLISION
    if raw_same and score_same:
        return "RAW_COLLISION"
    if (not raw_same) and score_same and raw_a is not None and raw_b is not None:
        return "MAPPING_COLLISION"
    if (not score_same) and score_a is not None and score_b is not None:
        return "DISCRIMINATES"
    return "MIXED"


CONTAMINATION = {
    "sustain_pitch_stability": ("medium", "VOCAL-ONLY PREFERRED", "accompaniment harmonic tracking risk"),
    "sustain_level_stability": ("medium", "VOCAL-ONLY PREFERRED", "mix RMS can dominate"),
    "region_consistency": ("medium", "VOCAL-ONLY PREFERRED", ""),
    "unstable_region_ratio": ("medium", "VOCAL-ONLY PREFERRED", ""),
    "spectral_projection": ("high", "VOCAL-ONLY PREFERRED", "SPR mix-sensitive"),
    "presence_prominence": ("high", "VOCAL-ONLY PREFERRED", "presence band mix-sensitive"),
    "projection_consistency": ("high", "VOCAL-ONLY PREFERRED", ""),
    "weak_projection_segment_ratio": ("high", "VOCAL-ONLY PREFERRED", ""),
    "weight_balance": ("high", "VOCAL-ONLY PREFERRED", "low-band accompaniment"),
    "mid_resonance_balance": ("high", "VOCAL-ONLY PREFERRED", ""),
    "spectral_slope_balance": ("high", "VOCAL-ONLY PREFERRED", "mastering EQ"),
    "resonance_consistency": ("high", "VOCAL-ONLY PREFERRED", ""),
    "extreme_resonance_ratio": ("high", "VOCAL-ONLY PREFERRED", ""),
    "global_dynamic_range": ("very_high", "VOCAL-ONLY PREFERRED", "mastering/compression confound"),
    "local_dynamic_variation": ("very_high", "VOCAL-ONLY PREFERRED", "mix dynamics"),
    "smoothness": ("high", "VOCAL-ONLY PREFERRED", ""),
    "phrase_consistency": ("high", "VOCAL-ONLY PREFERRED", ""),
    "abrupt_change_ratio": ("high", "VOCAL-ONLY PREFERRED", ""),
}


FEATURE_VERDICT_DEFAULT = {
    "sustain_pitch_stability": "KEEP_VOCAL_ONLY",
    "sustain_level_stability": "KEEP_VOCAL_ONLY",
    "region_consistency": "KEEP_VOCAL_ONLY",
    "unstable_region_ratio": "RESTRICT",
    "spectral_projection": "RESTRICT",
    "presence_prominence": "RESTRICT",
    "projection_consistency": "RESTRICT",
    "weak_projection_segment_ratio": "RESTRICT",
    "weight_balance": "RESTRICT",
    "mid_resonance_balance": "RESTRICT",
    "spectral_slope_balance": "RESTRICT",
    "resonance_consistency": "RESTRICT",
    "extreme_resonance_ratio": "RESTRICT",
    "global_dynamic_range": "REDESIGN",
    "local_dynamic_variation": "KEEP_VOCAL_ONLY",
    "smoothness": "KEEP_VOCAL_ONLY",
    "phrase_consistency": "KEEP_VOCAL_ONLY",
    "abrupt_change_ratio": "KEEP_VOCAL_ONLY",
}


def compare_analyses(a: dict[str, Any], b: dict[str, Any], label_a: str, label_b: str) -> list[dict]:
    sa, sb = _submetrics(a), _submetrics(b)
    keys = sorted(set(sa) | set(sb))
    rows = []
    for k in keys:
        ma, mb = sa.get(k) or {}, sb.get(k) or {}
        raw_a, raw_b = ma.get("raw_value"), mb.get("raw_value")
        sc_a, sc_b = ma.get("score"), mb.get("score")
        verdict = _classify(
            raw_a, raw_b, sc_a, sc_b, ma.get("area_status"), mb.get("area_status")
        )
        cont = CONTAMINATION.get(k, ("unknown", "?", ""))
        rows.append(
            {
                "submetric_id": k,
                "area_id": ma.get("area_id") or mb.get("area_id"),
                f"raw_{label_a}": raw_a,
                f"raw_{label_b}": raw_b,
                "absolute_diff": None
                if raw_a is None or raw_b is None
                else abs(float(raw_a) - float(raw_b)),
                "relative_diff": None
                if raw_a is None or raw_b is None
                else abs(float(raw_a) - float(raw_b))
                / max(abs(float(raw_a)), abs(float(raw_b)), RAW_EPS),
                f"mapped_{label_a}": sc_a,
                f"mapped_{label_b}": sc_b,
                "score_diff": None
                if sc_a is None or sc_b is None
                else abs(float(sc_a) - float(sc_b)),
                "collision_type": verdict,
                "accompaniment_sensitive": cont[0],
                "preferred_source": cont[1],
                "note": cont[2],
                "feature_verdict": FEATURE_VERDICT_DEFAULT.get(k, "RESEARCH"),
            }
        )
    return rows


def fingerprint_job(runtime: Path, analysis_id: str) -> dict[str, Any]:
    d = runtime / analysis_id
    out: dict[str, Any] = {"analysis_id": analysis_id}
    for name in ("upload.mp3", "upload.m4a", "upload.wav", "analysis.wav"):
        p = d / name
        if p.exists():
            out[name] = file_fingerprint(p, label=name)
    demucs = d / "demucs"
    for name in ("vocals.wav", "no_vocals.wav", "input_converted.wav"):
        p = demucs / name
        if p.exists():
            out[f"demucs/{name}"] = file_fingerprint(p, label=name)
            if p.suffix == ".wav":
                try:
                    import soundfile as sf

                    y, sr = sf.read(str(p), always_2d=False)
                    if getattr(y, "ndim", 1) > 1:
                        y = y.mean(axis=1)
                    out[f"demucs/{name}_wave"] = waveform_checksum(y, sr=sr)
                except Exception as exc:  # noqa: BLE001
                    out[f"demucs/{name}_wave_error"] = str(exc)
    aj = d / "analysis.json"
    if aj.exists():
        analysis = json.loads(aj.read_text(encoding="utf-8"))
        sc = analysis.get("score") or {}
        out["score_overall"] = sc.get("overall")
        out["source_mode"] = (analysis.get("audio") or {}).get("source_mode")
        out["content_sha256"] = (analysis.get("audio") or {}).get("content_sha256")
        out["fingerprints_embedded"] = analysis.get("fingerprints")
    return out


def analyze_file(
    path: Path,
    out_dir: Path,
    *,
    separate: bool,
    recording_id: str,
) -> dict[str, Any]:
    from audio_analyzer.pipeline import analyze_audio

    return analyze_audio(
        str(path),
        output_dir=str(out_dir),
        recording_id=recording_id,
        separate=separate,
        build_preview=False,
        include_feedback=False,
    )


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def write_summary_md(
    path: Path,
    *,
    fp_a: dict,
    fp_b: dict,
    rows: list[dict],
    label_a: str,
    label_b: str,
    answers: dict[str, str],
) -> None:
    same_upload = None
    ua = (fp_a.get("upload.mp3") or fp_a.get("upload.m4a") or fp_a.get("upload.wav") or {}).get(
        "sha256"
    )
    ub = (fp_b.get("upload.mp3") or fp_b.get("upload.m4a") or fp_b.get("upload.wav") or {}).get(
        "sha256"
    )
    if ua and ub:
        same_upload = ua == ub
    collisions = {}
    for r in rows:
        collisions[r["collision_type"]] = collisions.get(r["collision_type"], 0) + 1
    lines = [
        "# Discrimination audit summary",
        "",
        f"- label_a: `{label_a}`",
        f"- label_b: `{label_b}`",
        f"- upload SHA identical: **{same_upload}**",
        f"- upload_a: `{ua}`",
        f"- upload_b: `{ub}`",
        "",
        "## Collision counts",
        "",
    ]
    for k, v in sorted(collisions.items()):
        lines.append(f"- {k}: {v}")
    lines += ["", "## Q&A", ""]
    for q, a in answers.items():
        lines.append(f"### {q}")
        lines.append(a)
        lines.append("")
    lines += ["", "## Feature verdicts", ""]
    for r in rows:
        lines.append(
            f"- `{r['submetric_id']}`: {r['feature_verdict']} ({r['collision_type']})"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", type=Path, help="Audio file A")
    ap.add_argument("--b", type=Path, help="Audio file B")
    ap.add_argument("--analysis-a", type=str)
    ap.add_argument("--analysis-b", type=str)
    ap.add_argument("--runtime", type=Path, default=Path("runtime"))
    ap.add_argument("--output", type=Path, default=Path("runtime/discrimination_audit"))
    ap.add_argument("--separate", action="store_true")
    ap.add_argument("--label-a", default="A")
    ap.add_argument("--label-b", default="B")
    ap.add_argument("--skip-reanalyze", action="store_true")
    args = ap.parse_args()

    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    label_a, label_b = args.label_a, args.label_b

    analysis_a = analysis_b = None
    fp_a: dict[str, Any] = {}
    fp_b: dict[str, Any] = {}

    if args.analysis_a and args.analysis_b:
        fp_a = fingerprint_job(args.runtime, args.analysis_a)
        fp_b = fingerprint_job(args.runtime, args.analysis_b)
        analysis_a = _load_analysis(args.analysis_a, args.runtime)
        analysis_b = _load_analysis(args.analysis_b, args.runtime)
        dump_json(out / "input_fingerprints.json", {"A": fp_a, "B": fp_b})
    elif args.a and args.b:
        dump_json(
            out / "input_fingerprints.json",
            {
                "A": file_fingerprint(args.a, original_filename=args.a.name),
                "B": file_fingerprint(args.b, original_filename=args.b.name),
                "sha_equal": sha256_file(args.a) == sha256_file(args.b),
            },
        )
        if not args.skip_reanalyze:
            work = out / "runs"
            analysis_a = analyze_file(
                args.a, work, separate=args.separate, recording_id=f"audit_{label_a}"
            )
            analysis_b = analyze_file(
                args.b, work, separate=args.separate, recording_id=f"audit_{label_b}"
            )
            fp_a = fingerprint_job(work, f"audit_{label_a}")
            fp_b = fingerprint_job(work, f"audit_{label_b}")
            dump_json(out / "input_fingerprints.json", {"A": fp_a, "B": fp_b})
    else:
        ap.error("Provide --a/--b or --analysis-a/--analysis-b")

    assert analysis_a and analysis_b
    rows = compare_analyses(analysis_a, analysis_b, label_a, label_b)
    write_csv(out / "raw_metrics.csv", rows)
    write_csv(out / "mapped_metrics.csv", rows)
    write_csv(
        out / "feature_verdicts.csv",
        [
            {
                "submetric_id": r["submetric_id"],
                "verdict": r["feature_verdict"],
                "collision_type": r["collision_type"],
                "accompaniment_sensitive": r["accompaniment_sensitive"],
            }
            for r in rows
        ],
    )

    ua = (fp_a.get("upload.mp3") or fp_a.get("upload.m4a") or fp_a.get("upload.wav") or {}).get(
        "sha256"
    )
    ub = (fp_b.get("upload.mp3") or fp_b.get("upload.m4a") or fp_b.get("upload.wav") or {}).get(
        "sha256"
    )
    same_input = bool(ua and ub and ua == ub)
    raw_coll = sum(1 for r in rows if r["collision_type"] == "RAW_COLLISION")
    map_coll = sum(1 for r in rows if r["collision_type"] == "MAPPING_COLLISION")

    answers = {
        "Q1 raw signals different?": (
            "NO — upload SHA256 identical (same file)."
            if same_input
            else "YES — upload fingerprints differ."
        ),
        "Q2 raw metrics nearly identical?": (
            f"YES — RAW_COLLISION count={raw_coll} (expected if same input)."
            if same_input
            else f"RAW_COLLISION={raw_coll}, see raw_metrics.csv"
        ),
        "Q3 mapping collision?": f"MAPPING_COLLISION count={map_coll}",
        "Q4 worst collision submetrics?": ", ".join(
            r["submetric_id"]
            for r in rows
            if r["collision_type"] in ("RAW_COLLISION", "MAPPING_COLLISION")
        )[:500],
        "Q5 RAW vs VOCAL gap?": (
            "Not re-run in this mode; use --a/--b without prior analyses and compare "
            "with/without --separate. Existing pair both used source_mode=separated."
        ),
        "Q6 instrumental stem high scores?": (
            "Check demucs/no_vocals energy vs vocals in fingerprints; "
            "spectral features on mix/instrumental are accompaniment-sensitive (RESTRICT)."
        ),
        "Q7 dynamic mastering confound?": (
            "YES risk — global_dynamic_range redesign candidate; "
            "commercial loudness/compression dominates skill."
        ),
        "Q8 projection/resonance backing dominated?": (
            "YES risk — high accompaniment sensitivity; often UNKNOWN after Demucs HF-loss gate."
        ),
        "Q9 stability F0 tracks vocal?": (
            "PARTIAL — residual_std can track accompaniment harmonics on mixes; "
            "prefer vocal stem + voiced windows."
        ),
        "Q10 long-song sampling hurts?": (
            "YES risk — uniform max-24 windows over 4min dilutes; "
            "duration_policy vocal-active 45s clip now applied for >60s."
        ),
        "Q11 15–60s clip helps?": (
            "Implemented as deterministic vocal-active clip; pair re-run recommended."
        ),
        "Q12 KEEP/RESTRICT/REMOVE?": "See feature_verdicts.csv",
    }

    dump_json(
        out / "collision_report.json",
        {
            "same_input": same_input,
            "upload_sha_a": ua,
            "upload_sha_b": ub,
            "collision_counts": {
                t: sum(1 for r in rows if r["collision_type"] == t)
                for t in sorted({r["collision_type"] for r in rows})
            },
            "rows": rows,
        },
    )
    write_summary_md(
        out / "audit_summary.md",
        fp_a=fp_a,
        fp_b=fp_b,
        rows=rows,
        label_a=label_a,
        label_b=label_b,
        answers=answers,
    )
    print(f"Wrote audit to {out}")
    print(f"same_input={same_input} RAW_COLLISION={raw_coll} MAPPING_COLLISION={map_coll}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
