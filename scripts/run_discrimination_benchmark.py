#!/usr/bin/env python3
"""
scripts/run_discrimination_benchmark.py
---------------------------------------
Labeled Vocal Discrimination Benchmark runner.

Does NOT retune score anchors / thresholds.
Does NOT use group labels inside scoring — labels are evaluation-only.

Usage:
  python scripts/run_discrimination_benchmark.py \\
    --manifest data/discrimination_manifest.csv \\
    --ratings data/human_ratings.csv \\
    --output runtime/discrimination_benchmark

  # Smoke / CI without private audio:
  python scripts/run_discrimination_benchmark.py --synthetic-demo \\
    --output runtime/discrimination_benchmark_demo
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from audio_analyzer.benchmark.extract import (  # noqa: E402
    AXES,
    SUBMETRICS,
    extract_axis_scores,
    extract_mapped_features,
    extract_raw_features,
    run_analysis,
    unknown_flags,
)
from audio_analyzer.benchmark.manifest import (  # noqa: E402
    dataset_counts,
    filter_active,
    fingerprint_samples,
    load_human_ratings,
    load_manifest,
    same_song_subset,
)
from audio_analyzer.benchmark.report import write_benchmark_summary  # noqa: E402
from audio_analyzer.benchmark.stats import (  # noqa: E402
    bootstrap_ci,
    cliffs_delta,
    group_describe,
    monotonic_by_group,
    roc_auc,
    saturation_rate,
    spearman_rho,
    within_between_variance,
)
from audio_analyzer.benchmark.verdicts import (  # noqa: E402
    axis_calibration_readiness,
    classify_feature_verdict,
    mapping_loss_label,
    vocal_benefit_label,
)
from audio_analyzer.models import ANALYSIS_VERSION  # noqa: E402
from audio_analyzer.scoring import config_v3 as cfg  # noqa: E402


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys: list[str] = []
    seen = set()
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                keys.append(k)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _git_sha() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(ROOT), stderr=subprocess.DEVNULL
        )
        return out.decode().strip()
    except Exception:
        return "unknown"


def _config_hash() -> str:
    blob = json.dumps(
        {
            "SCORE_VERSION": cfg.SCORE_VERSION,
            "SEGMENT_MIN_VOICED_RATIO": getattr(cfg, "SEGMENT_MIN_VOICED_RATIO", None),
            "LONG_SONG_SCORE_CLIP_SEC": getattr(cfg, "LONG_SONG_SCORE_CLIP_SEC", None),
            "RECOMMENDED_MAX_SCORE_SEC": getattr(cfg, "RECOMMENDED_MAX_SCORE_SEC", None),
        },
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def make_synthetic_demo(n_per: int = 12) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    """
    Synthetic labeled tables (no audio). Expert > beginner on some features,
    mastering confound on global DR, saturation on pitch mapped score.
    Returns samples, raw_rows, mapped_rows, axis_rows (each with mode raw+vocal).
    """
    rng = np.random.default_rng(42)
    samples = []
    raw_rows = []
    mapped_rows = []
    axis_rows = []
    for gi, group in enumerate(("beginner", "intermediate", "expert")):
        rank = gi
        for i in range(n_per):
            sid = f"{group[:3]}_{i:02d}"
            subj = f"sub_{group[0]}{i % 5}"
            commercial = bool(group == "expert" and i % 3 == 0)
            sample = {
                "sample_id": sid,
                "file_path": f"synthetic/{sid}.wav",
                "subject_id": subj,
                "group": group,
                "skill_rank": rank,
                "song_id": "song_a" if i % 2 == 0 else "song_b",
                "source_type": "commercial_mix" if commercial else "phone_recording",
                "recording_device": "phone",
                "has_backing_track": commercial,
                "commercial_mastered": commercial,
                "same_song_group": "song_a_match" if i % 2 == 0 else "",
                "notes": "synthetic",
                "file_exists": True,
                "sha256": hashlib.sha256(sid.encode()).hexdigest(),
                "size_bytes": 1000 + i,
                "duplicate_input": False,
            }
            samples.append(sample)
            # skill-linked residual (lower better)
            residual = 30 - 8 * rank + rng.normal(0, 3)
            level_var = 8 - 2.2 * rank + rng.normal(0, 1)
            # mastering-linked DR
            gdr = (28 if commercial else 14) + rng.normal(0, 1.5)
            pitch_mapped = min(100.0, 92 + rng.normal(0, 2))  # saturated
            for mode, boost in (("raw", 0.0), ("vocal", 0.08)):
                raw_rows.append(
                    {
                        "sample_id": sid,
                        "mode": mode,
                        "group": group,
                        "skill_rank": rank,
                        "subject_id": subj,
                        "source_type": sample["source_type"],
                        "commercial_mastered": int(commercial),
                        "same_song_group": sample["same_song_group"],
                        "residual_median": residual * (1.0 - boost * 0.3),
                        "residual_p90": residual * 1.4,
                        "median_rms_variation_db": level_var,
                        "global_dynamic_range_db": gdr,
                        "spr_db": 22 - 2 * rank + rng.normal(0, 1),
                        "voiced_ratio": 0.4 + 0.1 * rank,
                        "quality_status": "pass",
                    }
                )
                mapped_rows.append(
                    {
                        "sample_id": sid,
                        "mode": mode,
                        "group": group,
                        "skill_rank": rank,
                        "subject_id": subj,
                        "source_type": sample["source_type"],
                        "commercial_mastered": int(commercial),
                        "same_song_group": sample["same_song_group"],
                        "sustain_pitch_stability_score": pitch_mapped,
                        "sustain_pitch_stability_raw": residual,
                        "sustain_level_stability_score": max(
                            20.0, min(100.0, 40 + 18 * rank + rng.normal(0, 5))
                        ),
                        "sustain_level_stability_raw": level_var,
                        "global_dynamic_range_score": max(
                            20.0, min(100.0, 90 - abs(gdr - 16) * 2)
                        ),
                        "global_dynamic_range_raw": gdr,
                        "spectral_projection_score": None if mode == "raw" and i % 4 == 0 else 70 + 5 * rank,
                        "spectral_projection_raw": 22 - 2 * rank,
                    }
                )
                axis_rows.append(
                    {
                        "sample_id": sid,
                        "mode": mode,
                        "group": group,
                        "skill_rank": rank,
                        "subject_id": subj,
                        "source_type": sample["source_type"],
                        "commercial_mastered": int(commercial),
                        "same_song_group": sample["same_song_group"],
                        "stability_score": 45 + 15 * rank + rng.normal(0, 4),
                        "stability_status": "normal",
                        "projection_score": None if mode == "raw" and i % 4 == 0 else 50 + 10 * rank,
                        "projection_status": "unknown"
                        if mode == "raw" and i % 4 == 0
                        else "normal",
                        "resonance_score": None if i % 5 == 0 else 48 + 8 * rank,
                        "resonance_status": "unknown" if i % 5 == 0 else "normal",
                        "dynamic_control_score": 55 + rng.normal(0, 8) - (10 if commercial else 0),
                        "dynamic_control_status": "normal",
                        "reliable_axis_count": 2,
                        "overall_primary": None,
                        "overall_internal": 60 + 5 * rank,
                    }
                )
    return samples, raw_rows, mapped_rows, axis_rows


def _split_mode(rows: list[dict], mode: str) -> list[dict]:
    return [r for r in rows if r.get("mode") == mode]


def _vals(rows: list[dict], key: str) -> list[Any]:
    return [r.get(key) for r in rows]


def _by_group(rows: list[dict], key: str) -> dict[str, list]:
    out = {"beginner": [], "intermediate": [], "expert": []}
    for r in rows:
        g = r.get("group")
        if g in out:
            out[g].append(r.get(key))
    return out


def evaluate_feature(
    rows: list[dict],
    feature: str,
    *,
    higher_better: bool = True,
) -> dict[str, Any]:
    ranks = _vals(rows, "skill_rank")
    vals = _vals(rows, feature)
    # For lower-is-better raw metrics, flip for AUC vs expert-high labels
    labels = []
    scores = []
    expert_vals, beg_vals = [], []
    for r in rows:
        if r.get(feature) is None or r.get("skill_rank") is None:
            continue
        v = float(r[feature])
        scores.append(v if higher_better else -v)
        labels.append(1 if int(r["skill_rank"]) == 2 else (0 if int(r["skill_rank"]) == 0 else None))
        if int(r["skill_rank"]) == 2:
            expert_vals.append(v)
        if int(r["skill_rank"]) == 0:
            beg_vals.append(v)
    # expert vs beginner only for AUC
    eb_scores, eb_labels = [], []
    for s, lab in zip(scores, labels):
        if lab is None:
            continue
        eb_scores.append(s)
        eb_labels.append(lab)
    auc_res = roc_auc(eb_scores, eb_labels)
    # spearman on all ordinal ranks
    valid_v, valid_r = [], []
    for r in rows:
        if r.get(feature) is None or r.get("skill_rank") is None:
            continue
        vv = float(r[feature])
        valid_v.append(vv if higher_better else -vv)
        valid_r.append(float(r["skill_rank"]))
    rho_res = spearman_rho(valid_v, valid_r)
    delta = cliffs_delta(expert_vals, beg_vals)
    if not higher_better and delta["delta"] is not None:
        # cliffs on raw lower-better: expert should be lower → delta negative; flip for "effect favoring expert skill"
        delta = {**delta, "delta_skill_oriented": -float(delta["delta"])}
    else:
        delta = {**delta, "delta_skill_oriented": delta["delta"]}
    g = _by_group(rows, feature)
    mono = monotonic_by_group(
        g["beginner"], g["intermediate"], g["expert"], higher_better=higher_better
    )
    sat = saturation_rate(vals, threshold=95.0)
    # source confound: commercial_mastered as binary label
    src_scores, src_labels = [], []
    for r in rows:
        if r.get(feature) is None:
            continue
        src_scores.append(float(r[feature]) if higher_better else -float(r[feature]))
        src_labels.append(1 if r.get("commercial_mastered") in (True, 1, "1") else 0)
    src_auc = roc_auc(src_scores, src_labels)
    ci = bootstrap_ci(eb_scores, eb_labels, stat="auc", n_boot=150, seed=1)
    return {
        "feature": feature,
        "n": rho_res["n"],
        "n_expert": int(sum(1 for x in eb_labels if x == 1)),
        "n_beginner": int(sum(1 for x in eb_labels if x == 0)),
        "auc": auc_res["auc"],
        "auc_direction": auc_res["direction"],
        "auc_ci_lo": ci.get("lo"),
        "auc_ci_hi": ci.get("hi"),
        "rho": rho_res["rho"],
        "rho_p_approx": rho_res["p_approx"],
        "cliffs_delta": delta.get("delta_skill_oriented"),
        "saturation_rate": sat["rate"],
        "source_auc": src_auc["auc"],
        "monotonic_order": mono["monotonic_order"],
        "group_stats": {k: group_describe(v) for k, v in g.items()},
        "higher_better": higher_better,
    }


def analyze_tables(
    samples: list[dict],
    raw_rows: list[dict],
    mapped_rows: list[dict],
    axis_rows: list[dict],
    ratings: list[dict],
    out: Path,
    meta: dict,
) -> dict[str, Any]:
    feature_stats: list[dict] = []
    verdicts: list[dict] = []

    raw_feature_keys = [
        ("residual_median", False),
        ("residual_p90", False),
        ("median_rms_variation_db", False),
        ("global_dynamic_range_db", False),  # often confound
        ("spr_db", False),
        ("voiced_ratio", True),
    ]
    mapped_keys = [
        ("sustain_pitch_stability_score", True),
        ("sustain_level_stability_score", True),
        ("global_dynamic_range_score", True),
        ("spectral_projection_score", True),
    ]

    raw_vs_vocal = {}
    for mode in ("raw", "vocal"):
        rr = _split_mode(raw_rows, mode)
        mr = _split_mode(mapped_rows, mode)
        for feat, hb in raw_feature_keys:
            st = evaluate_feature(rr, feat, higher_better=hb)
            st["mode"] = mode
            st["kind"] = "raw"
            feature_stats.append(st)
        for feat, hb in mapped_keys:
            st = evaluate_feature(mr, feat, higher_better=hb)
            st["mode"] = mode
            st["kind"] = "mapped"
            # mapping loss vs raw counterpart
            if feat.startswith("sustain_pitch"):
                raw_st = evaluate_feature(rr, "residual_median", higher_better=False)
                st["raw_auc"] = raw_st["auc"]
                st["mapped_auc"] = st["auc"]
                st["mapping_loss"] = mapping_loss_label(raw_st["auc"], st["auc"])
            if feat.startswith("global_dynamic"):
                raw_st = evaluate_feature(rr, "global_dynamic_range_db", higher_better=False)
                st["raw_auc"] = raw_st["auc"]
                st["mapped_auc"] = st["auc"]
                st["mapping_loss"] = mapping_loss_label(raw_st["auc"], st["auc"])
            feature_stats.append(st)

    # Pair RAW vs VOCAL AUC for key features
    for feat, hb in raw_feature_keys + [(m, True) for m, _ in mapped_keys]:
        table = raw_rows if not feat.endswith("_score") else mapped_rows
        a_raw = evaluate_feature(_split_mode(table, "raw"), feat, higher_better=hb)
        a_voc = evaluate_feature(_split_mode(table, "vocal"), feat, higher_better=hb)
        raw_vs_vocal[feat] = {
            "auc_raw": a_raw["auc"],
            "auc_vocal": a_voc["auc"],
            "benefit": vocal_benefit_label(a_raw["auc"], a_voc["auc"]),
        }

    # Verdicts from vocal-mode mapped/raw preferred
    for st in feature_stats:
        if st.get("mode") != "vocal":
            continue
        v = classify_feature_verdict(
            {
                "n": st["n"],
                "n_expert": st["n_expert"],
                "n_beginner": st["n_beginner"],
                "auc": st["auc"],
                "rho": st["rho"],
                "saturation_rate": st["saturation_rate"],
                "source_auc": st["source_auc"],
                "raw_auc": st.get("raw_auc"),
                "mapped_auc": st.get("mapped_auc", st["auc"]),
                "unknown_rate": 0.0,
                "vocal_better": raw_vs_vocal.get(st["feature"], {}).get("benefit")
                == "VOCAL_BETTER",
            }
        )
        verdicts.append(
            {
                "feature": st["feature"],
                "mode": st["mode"],
                "kind": st["kind"],
                "verdict": v["verdict"],
                "reasons": "|".join(v["reasons"]),
                "auc": st["auc"],
                "rho": st["rho"],
                "source_auc": st["source_auc"],
                "saturation_rate": st["saturation_rate"],
                "mapping_loss": st.get("mapping_loss"),
            }
        )

    # Axis stats
    axis_stats_rows = []
    axis_results = {}
    calibration = {}
    for mode in ("raw", "vocal"):
        ar = _split_mode(axis_rows, mode)
        for ax in AXES:
            key = f"{ax}_score"
            st = evaluate_feature(ar, key, higher_better=True)
            unk = [
                1
                if (r.get(f"{ax}_status") == "unknown" or r.get(key) is None)
                else 0
                for r in ar
            ]
            unk_rate = float(np.mean(unk)) if unk else None
            st["unknown_rate"] = unk_rate
            st["mode"] = mode
            st["axis"] = ax
            axis_stats_rows.append(st)
            if mode == "vocal":
                source_conf = (
                    st["source_auc"] is not None
                    and st["auc"] is not None
                    and float(st["source_auc"]) - float(st["auc"]) >= 0.15
                )
                redesign = ax == "dynamic_control" and source_conf
                readiness = axis_calibration_readiness(
                    {
                        "n": st["n"],
                        "n_expert": st["n_expert"],
                        "n_beginner": st["n_beginner"],
                        "auc": st["auc"],
                        "rho": st["rho"],
                        "unknown_rate": unk_rate or 0,
                        "source_confound": source_conf,
                        "redesign": redesign,
                    }
                )
                calibration[ax] = readiness
                axis_results[ax] = {
                    "auc": st["auc"],
                    "rho": st["rho"],
                    "unknown_rate": unk_rate,
                    "source_confound": source_conf,
                    "readiness": readiness,
                }

    # Matched song subset
    matched = [s for s in samples if s.get("same_song_group")]
    matched_stats = []
    if matched:
        ids = {s["sample_id"] for s in same_song_subset(samples)}
        mr = [r for r in _split_mode(mapped_rows, "vocal") if r["sample_id"] in ids]
        if mr:
            st = evaluate_feature(mr, "sustain_level_stability_score", higher_better=True)
            matched_stats.append({"feature": "sustain_level_stability_score", **{k: st[k] for k in ("auc", "rho", "n", "n_expert", "n_beginner")}})

    # Human reliability + model agreement
    human_rel = {"n_ratings": len(ratings)}
    if ratings:
        by_sample: dict[str, list] = {}
        for r in ratings:
            by_sample.setdefault(r["sample_id"], []).append(r)
        pairs_a, pairs_b = [], []
        for _sid, lst in by_sample.items():
            if len(lst) >= 2 and lst[0].get("overall_skill") and lst[1].get("overall_skill"):
                pairs_a.append(lst[0]["overall_skill"])
                pairs_b.append(lst[1]["overall_skill"])
        if pairs_a:
            human_rel["overall_spearman"] = spearman_rho(pairs_a, pairs_b)

    # Error cases: expert with low stability / beginner with high
    errors = []
    for r in _split_mode(axis_rows, "vocal"):
        sc = r.get("stability_score")
        if sc is None:
            continue
        if r.get("group") == "expert" and float(sc) < 55:
            errors.append({**r, "error_type": "expert_model_low"})
        if r.get("group") == "beginner" and float(sc) > 80:
            errors.append({**r, "error_type": "beginner_model_high"})
    errors = errors[:10]

    # Rank features
    vocal_mapped = [v for v in feature_stats if v.get("mode") == "vocal" and v.get("kind") == "mapped"]
    vocal_raw = [v for v in feature_stats if v.get("mode") == "vocal" and v.get("kind") == "raw"]
    best_mapped = sorted(
        [v for v in vocal_mapped if v.get("auc") is not None],
        key=lambda x: -float(x["auc"]),
    )[:5]
    best_raw = sorted(
        [v for v in vocal_raw if v.get("auc") is not None],
        key=lambda x: -float(x["auc"]),
    )[:5]
    worst = sorted(
        [v for v in vocal_mapped if v.get("auc") is not None],
        key=lambda x: float(x["auc"]),
    )[:5]
    saturated = [
        v
        for v in vocal_mapped
        if v.get("saturation_rate") is not None and float(v["saturation_rate"]) >= 0.7
    ]
    source_confounded = [
        v
        for v in feature_stats
        if v.get("mode") == "vocal"
        and v.get("auc") is not None
        and v.get("source_auc") is not None
        and float(v["source_auc"]) - float(v["auc"]) >= 0.15
    ]

    counts = dataset_counts(samples)
    evidence = "NO"
    keepish = [v for v in verdicts if v["verdict"] in ("KEEP", "KEEP_VOCAL_ONLY", "CALIBRATION_CANDIDATE")]
    if counts["samples"] >= 30 and len(keepish) >= 2:
        evidence = "PARTIAL"
    if (
        counts["samples"] >= 30
        and counts.get("expert", 0) >= 10
        and any(v.get("auc") and float(v["auc"]) >= 0.75 for v in best_mapped)
    ):
        evidence = "YES" if evidence == "PARTIAL" else evidence

    blockers = []
    if counts["samples"] < 30:
        blockers.append("labeled sample count below exploratory target (30)")
    if saturated:
        blockers.append("pitch / score saturation present")
    if source_confounded:
        blockers.append("source/mastering confound on one or more features")
    if calibration.get("projection") == "NOT_READY":
        blockers.append("projection not calibration-ready")
    if calibration.get("resonance") == "NOT_READY":
        blockers.append("resonance not calibration-ready")

    body = {
        **counts,
        "duplicates": sum(1 for s in samples if s.get("duplicate_input")),
        "missing_files": sum(1 for s in samples if not s.get("file_exists")),
        "source_counts": {},
        "human_reliability": human_rel,
        "best_raw": best_raw,
        "best_mapped": best_mapped,
        "worst": [{**w, "verdict": next((x["verdict"] for x in verdicts if x["feature"] == w["feature"]), "?")} for w in worst],
        "saturated": saturated,
        "source_confounded": source_confounded,
        "raw_vs_vocal": raw_vs_vocal,
        "matched_song": matched_stats or "insufficient",
        "axis_results": axis_results,
        "calibration_readiness": calibration,
        "blockers": blockers,
        "evidence_flag": evidence,
        "next_action": (
            "Collect ≥10 files/group with subject metadata; re-run before any anchor calibration."
            if counts["samples"] < 30
            else "Review feature_verdicts.csv; only CALIBRATION_CANDIDATE/KEEP features may proceed to a separate calibration PR."
        ),
    }
    for s in samples:
        st = s.get("source_type") or "unknown"
        body["source_counts"][st] = body["source_counts"].get(st, 0) + 1

    # Flatten feature stats for CSV
    flat_stats = []
    for st in feature_stats:
        flat = {k: v for k, v in st.items() if k != "group_stats"}
        for gname, gd in (st.get("group_stats") or {}).items():
            for mk, mv in gd.items():
                flat[f"{gname}_{mk}"] = mv
        flat_stats.append(flat)

    _write_csv(out / "feature_statistics.csv", flat_stats)
    _write_csv(
        out / "axis_statistics.csv",
        [{k: v for k, v in st.items() if k != "group_stats"} for st in axis_stats_rows],
    )
    _write_csv(out / "feature_verdicts.csv", verdicts)
    _write_csv(out / "matched_song_statistics.csv", matched_stats if isinstance(matched_stats, list) else [])
    _write_csv(
        out / "source_confound_statistics.csv",
        [
            {
                "feature": v["feature"],
                "mode": v.get("mode"),
                "auc": v.get("auc"),
                "source_auc": v.get("source_auc"),
                "delta": None
                if v.get("auc") is None or v.get("source_auc") is None
                else float(v["source_auc"]) - float(v["auc"]),
            }
            for v in feature_stats
            if v.get("source_auc") is not None
        ],
    )
    _write_csv(out / "error_cases.csv", errors)
    write_benchmark_summary(out / "benchmark_summary.md", meta=meta, body=body)

    # Final console block
    print("\n========== BENCHMARK FINAL ==========")
    print("DATASET")
    print(f"expert: {counts.get('expert')}")
    print(f"intermediate: {counts.get('intermediate')}")
    print(f"beginner: {counts.get('beginner')}")
    print(f"subjects: {counts.get('subjects')}")
    print(f"samples: {counts.get('samples')}")
    print("\nTOP DISCRIMINATIVE FEATURES")
    for i, r in enumerate(best_mapped or best_raw, 1):
        print(f"{i}. {r.get('feature')} AUC={r.get('auc')} rho={r.get('rho')}")
    print("\nLOW / FAILED FEATURES")
    for i, r in enumerate(worst, 1):
        print(f"{i}. {r.get('feature')} AUC={r.get('auc')}")
    print("\nRAW vs VOCAL")
    print(raw_vs_vocal)
    print("\nSOURCE CONFOUND")
    print([v["feature"] for v in source_confounded])
    print("\nMATCHED SONG RESULT")
    print(matched_stats)
    print("\nAXIS RESULTS")
    for ax, st in axis_results.items():
        print(f"{ax}: {st}")
    print("\nFEATURE VERDICTS")
    for v in verdicts:
        print(f"- {v['feature']}: {v['verdict']} ({v['reasons']})")
    print("\nCALIBRATION READINESS")
    for ax, st in calibration.items():
        print(f"{ax}: {st}")
    print(f"\nDO WE HAVE EVIDENCE THAT VAGENT DISTINGUISHES VOCAL SKILL?\n{evidence}")
    print(f"\nNEXT ACTION\n{body['next_action']}")
    return body


def extract_from_audio(samples: list[dict], work: Path, modes: tuple[str, ...]) -> tuple:
    raw_rows, mapped_rows, axis_rows = [], [], []
    for s in samples:
        for mode in modes:
            separate = mode == "vocal"
            rid = f"{s['sample_id']}_{mode}"
            try:
                analysis = run_analysis(
                    s["file_path"],
                    output_dir=str(work),
                    recording_id=rid,
                    separate=separate,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[skip] {s['sample_id']} mode={mode}: {exc}")
                continue
            base = {
                "sample_id": s["sample_id"],
                "group": s["group"],
                "skill_rank": s["skill_rank"],
                "subject_id": s["subject_id"],
                "source_type": s["source_type"],
                "commercial_mastered": int(bool(s.get("commercial_mastered"))),
                "same_song_group": s.get("same_song_group") or "",
                "recording_device": s.get("recording_device") or "",
            }
            raw_rows.append({**base, **extract_raw_features(analysis, mode=mode)})
            mapped_rows.append({**base, **extract_mapped_features(analysis, mode=mode)})
            axis_rows.append({**base, **extract_axis_scores(analysis, mode=mode)})
            unk = unknown_flags(analysis)
            axis_rows[-1]["unknown_projection"] = unk.get("projection")
            axis_rows[-1]["unknown_resonance"] = unk.get("resonance")
    return raw_rows, mapped_rows, axis_rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, default=None)
    ap.add_argument("--ratings", type=Path, default=None)
    ap.add_argument("--output", type=Path, default=Path("runtime/discrimination_benchmark"))
    ap.add_argument("--synthetic-demo", action="store_true")
    ap.add_argument("--modes", default="raw,vocal", help="comma: raw,vocal")
    ap.add_argument("--skip-audio", action="store_true", help="manifest fingerprints only")
    args = ap.parse_args()

    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    meta = {
        "score_version": cfg.SCORE_VERSION,
        "analysis_version": ANALYSIS_VERSION,
        "demucs_model": "htdemucs",
        "clip_policy": f">{getattr(cfg, 'RECOMMENDED_MAX_SCORE_SEC', 60)}s max; "
        f"clip={getattr(cfg, 'LONG_SONG_SCORE_CLIP_SEC', 45)}s vocal-active",
        "config_hash": _config_hash(),
        "git_commit": _git_sha(),
        "sampling_policy": "voiced-window + duration_policy_v3",
    }
    (out / "run_metadata.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )

    ratings: list[dict] = []
    if args.synthetic_demo:
        samples, raw_rows, mapped_rows, axis_rows = make_synthetic_demo()
        _write_csv(out / "manifest_snapshot.csv", samples)
        _write_csv(out / "sample_fingerprints.csv", samples)
    else:
        if not args.manifest or not args.manifest.exists():
            print(
                "No manifest. Use --synthetic-demo or provide --manifest "
                "(copy data/discrimination_manifest.example.csv)."
            )
            return 2
        rows = load_manifest(args.manifest)
        samples, dupes = fingerprint_samples(rows)
        _write_csv(out / "manifest_snapshot.csv", samples)
        _write_csv(out / "sample_fingerprints.csv", samples)
        if dupes:
            print(f"DUPLICATE_INPUT excluded: {dupes}")
        active = filter_active(samples)
        ratings = load_human_ratings(args.ratings)
        _write_csv(out / "human_ratings.csv", ratings)
        modes = tuple(m.strip() for m in args.modes.split(",") if m.strip())
        if args.skip_audio or not active:
            print("No active audio samples to analyze (or --skip-audio). Writing empty feature tables.")
            raw_rows, mapped_rows, axis_rows = [], [], []
        else:
            raw_rows, mapped_rows, axis_rows = extract_from_audio(
                active, out / "runs", modes
            )

    _write_csv(out / "raw_features_raw.csv", _split_mode(raw_rows, "raw"))
    _write_csv(out / "raw_features_vocal.csv", _split_mode(raw_rows, "vocal"))
    _write_csv(out / "mapped_features_raw.csv", _split_mode(mapped_rows, "raw"))
    _write_csv(out / "mapped_features_vocal.csv", _split_mode(mapped_rows, "vocal"))
    _write_csv(out / "axis_scores_raw.csv", _split_mode(axis_rows, "raw"))
    _write_csv(out / "axis_scores_vocal.csv", _split_mode(axis_rows, "vocal"))
    # aliases requested in spec
    _write_csv(out / "samples.csv", samples)
    if not (out / "human_ratings.csv").exists():
        _write_csv(out / "human_ratings.csv", ratings)

    analyze_tables(samples, raw_rows, mapped_rows, axis_rows, ratings, out, meta)
    print(f"\nWrote benchmark artifacts to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
