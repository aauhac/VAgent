"""
scripts/physiology_sanity_check.py
----------------------------------
Compare physiology inference across 3–5 local vocal samples.

Not ground-truth evaluation. Checks inference explosion, identical statuses,
unknown ratio, confidence saturation, and single-family domination.

Audio files are never committed by this script.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from audio_analyzer.preprocessing.audio_io import load_analysis_audio
from audio_analyzer.physiology.config import MECHANISM_CONFIDENCE_CAPS, PRODUCT_VISIBILITY
from audio_analyzer.physiology.observations import (
    observe_dynamic_swell_task,
    observe_siren_task,
    observe_sustained_task,
)
from audio_analyzer.physiology.report import build_premium_report, public_premium_report


SAMPLE_DIRS = [ROOT / "local_samples", ROOT]
CANDIDATES = [
    "옥탑방.m4a",
    "drowning.m4a",
    "bluemoon.m4a",
    "movie.m4a",
    "Lyrics.mp3",
]


def _pick_samples(n: int = 5) -> list[Path]:
    found: list[Path] = []
    for base in SAMPLE_DIRS:
        if not base.exists():
            continue
        for name in CANDIDATES:
            p = base / name
            if p.exists() and p not in found:
                found.append(p)
        if len(found) >= n:
            break
        for p in sorted(base.glob("*.m4a")) + sorted(base.glob("*.mp3")):
            if p not in found:
                found.append(p)
            if len(found) >= n:
                break
    return found[:n]


def _clip(y: np.ndarray, sr: int, sec: float = 4.0) -> np.ndarray:
    n = len(y)
    start = max(0, n // 2 - int(sec * sr) // 2)
    return y[start : start + int(sec * sr)].astype(np.float32)


def _distribution_warnings(rows: list[dict]) -> list[str]:
    warnings: list[str] = []
    if len(rows) < 2:
        return warnings

    sigs = []
    for r in rows:
        sig = tuple(
            sorted(
                (x["mechanism_id"], x["status"])
                for x in (r.get("reliable_findings") or [])
            )
        )
        sigs.append(sig)
    if len(set(sigs)) == 1 and sigs[0]:
        warnings.append("all_samples_identical_reliable_status")

    unc_ratios = []
    for r in rows:
        n_rel = len(r.get("reliable_findings") or [])
        n_unc = len(r.get("uncertain_findings") or [])
        tot = n_rel + n_unc
        unc_ratios.append(0.0 if tot == 0 else n_unc / tot)
    if unc_ratios and all(u == 0 for u in unc_ratios):
        warnings.append("unknown_ratio_zero_across_samples")

    attempted_n = len(
        [m for m, v in PRODUCT_VISIBILITY.items() if v in ("PRIMARY", "CONDITIONAL_PRIMARY")]
    )
    if all(len(r.get("reliable_findings") or []) == attempted_n for r in rows):
        warnings.append("all_attempted_mechanisms_always_user_visible_reliable")

    near_cap = 0
    total_conf = 0
    for r in rows:
        for m in r.get("physiology_assessments") or []:
            mid = m.get("mechanism_id")
            conf = float(m.get("confidence") or 0)
            cap = float(m.get("confidence_cap") or MECHANISM_CONFIDENCE_CAPS.get(mid, 0.5))
            total_conf += 1
            if cap > 0 and conf >= cap * 0.95:
                near_cap += 1
    if total_conf and near_cap / total_conf > 0.6:
        warnings.append("confidence_saturation_near_caps")

    fam_counter: Counter[str] = Counter()
    for r in rows:
        for m in r.get("physiology_assessments") or []:
            if m.get("status") == "unknown":
                continue
            for f in m.get("evidence_families_used") or []:
                fam_counter[f] += 1
    if fam_counter:
        top, n = fam_counter.most_common(1)[0]
        if n >= max(3, sum(fam_counter.values()) * 0.55):
            warnings.append(f"single_family_dominates_conclusions:{top}")

    return warnings


def main() -> int:
    samples = _pick_samples(5)
    if not samples:
        print("NO_SAMPLES — place audio under local_samples/ or repo root")
        return 1

    out_dir = ROOT / "runtime" / "physiology_sanity"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []

    for sample in samples:
        work = out_dir / sample.stem
        work.mkdir(parents=True, exist_ok=True)
        try:
            y, sr, _ = load_analysis_audio(str(sample), work, sample_rate=22050)
        except Exception as exc:  # noqa: BLE001
            rows.append({"sample_id": sample.stem, "error": str(exc)})
            continue
        if len(y) < sr * 3:
            rows.append({"sample_id": sample.stem, "error": "too_short"})
            continue

        clip = _clip(y, sr)
        tasks = [
            observe_sustained_task(clip, sr, task_id="sustain_a", attempt=1),
            observe_sustained_task(clip, sr, task_id="sustain_i", attempt=1),
            observe_siren_task(clip, sr, attempt=1),
            observe_dynamic_swell_task(clip, sr, attempt=1),
        ]
        full = build_premium_report(
            session_id=f"sanity_{sample.stem}",
            task_results=tasks,
            include_scientific_debug=True,
        )
        pub = public_premium_report(full)
        mechs = full.get("physiology_assessments") or []

        row = {
            "sample_id": sample.stem,
            "quality": {
                t.get("task_id"): (t.get("quality") or {}).get("status") for t in tasks
            },
            "valid_metrics": sorted(
                {
                    o.get("metric_id")
                    for t in tasks
                    for o in (t.get("observations") or [])
                    if o.get("valid")
                }
            ),
            "eligible_mechanisms": sorted(
                {f["mechanism_id"] for f in (pub.get("reliable_findings") or [])}
            ),
            "unknown_mechanisms": sorted(
                {f["mechanism_id"] for f in (pub.get("uncertain_findings") or [])}
            ),
            "confidence": {
                m["mechanism_id"]: {
                    "numeric": m.get("confidence"),
                    "label": m.get("confidence_label"),
                    "cap": m.get("confidence_cap"),
                }
                for m in mechs
            },
            "rule_ids": {
                m["mechanism_id"]: m.get("rule_id") for m in mechs if m.get("rule_id")
            },
            "reliable_findings": pub.get("reliable_findings") or [],
            "uncertain_findings": pub.get("uncertain_findings") or [],
            "physiology_assessments": mechs,
            "coverage": pub.get("mechanism_coverage"),
        }
        print(
            sample.name,
            "reliable=",
            row["eligible_mechanisms"],
            "uncertain=",
            row["unknown_mechanisms"],
        )
        rows.append(row)

    ok_rows = [r for r in rows if "error" not in r]
    dist_warnings = _distribution_warnings(ok_rows)
    payload = {
        "samples": [
            {
                "sample_id": r["sample_id"],
                "quality": r.get("quality"),
                "valid_metrics": r.get("valid_metrics"),
                "eligible_mechanisms": r.get("eligible_mechanisms"),
                "unknown_mechanisms": r.get("unknown_mechanisms"),
                "confidence": r.get("confidence"),
                "rule_ids": r.get("rule_ids"),
                "coverage": r.get("coverage"),
                "reliable_findings": [
                    {
                        "mechanism_id": x["mechanism_id"],
                        "status": x["status"],
                        "confidence_label": x.get("confidence_label"),
                    }
                    for x in (r.get("reliable_findings") or [])
                ],
                "uncertain_findings": [
                    {"mechanism_id": x["mechanism_id"], "status": x.get("status")}
                    for x in (r.get("uncertain_findings") or [])
                ],
            }
            for r in rows
        ],
        "distribution_warnings": dist_warnings,
    }
    out_path = out_dir / "summary.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("distribution_warnings:", dist_warnings)
    print("wrote", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
