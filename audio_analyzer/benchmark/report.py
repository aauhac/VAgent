"""
audio_analyzer/benchmark/report.py
----------------------------------
Write benchmark_summary.md
"""

from __future__ import annotations

from typing import Any


def write_benchmark_summary(path, *, meta: dict[str, Any], body: dict[str, Any]) -> None:
    lines = [
        "# Labeled Vocal Discrimination Benchmark",
        "",
        "> Calibration-pre validation. No score anchors were retuned from this run.",
        "",
        "## 1. Dataset",
        "",
        f"- samples (active): {body.get('samples')}",
        f"- subjects: {body.get('subjects')}",
        f"- expert: {body.get('expert')}",
        f"- intermediate: {body.get('intermediate')}",
        f"- beginner: {body.get('beginner')}",
        f"- duplicates_excluded: {body.get('duplicates')}",
        f"- missing_files: {body.get('missing_files')}",
        "",
        "## 2. Group distribution",
        "",
        "See `feature_statistics.csv` / `axis_statistics.csv`.",
        "",
        "## 3. Source distribution",
        "",
        str(body.get("source_counts") or {}),
        "",
        "## 4. Human rating reliability",
        "",
        str(body.get("human_reliability") or "n/a (no multi-rater overlap)"),
        "",
        "## 5. Best raw features",
        "",
    ]
    for i, row in enumerate(body.get("best_raw") or [], 1):
        lines.append(
            f"{i}. `{row.get('feature')}` AUC={row.get('auc')} rho={row.get('rho')} ({row.get('mode')})"
        )
    lines += ["", "## 6. Best mapped features", ""]
    for i, row in enumerate(body.get("best_mapped") or [], 1):
        lines.append(
            f"{i}. `{row.get('feature')}` AUC={row.get('auc')} rho={row.get('rho')} ({row.get('mode')})"
        )
    lines += ["", "## 7. Worst features", ""]
    for i, row in enumerate(body.get("worst") or [], 1):
        lines.append(
            f"{i}. `{row.get('feature')}` AUC={row.get('auc')} verdict={row.get('verdict')}"
        )
    lines += ["", "## 8. Saturated features", ""]
    for row in body.get("saturated") or []:
        lines.append(f"- `{row.get('feature')}` sat_rate={row.get('saturation_rate')}")
    lines += ["", "## 9. Source-confounded features", ""]
    for row in body.get("source_confounded") or []:
        lines.append(
            f"- `{row.get('feature')}` skill_auc={row.get('auc')} source_auc={row.get('source_auc')}"
        )
    lines += [
        "",
        "## 10. RAW vs VOCAL",
        "",
        str(body.get("raw_vs_vocal") or {}),
        "",
        "## 11. Matched-song",
        "",
        str(body.get("matched_song") or "insufficient"),
        "",
        "## 12. Axis-level results",
        "",
    ]
    for ax, st in (body.get("axis_results") or {}).items():
        lines.append(f"- **{ax}**: {st}")
    lines += ["", "## 13. Feature verdict", "", "See `feature_verdicts.csv`.", ""]
    lines += ["", "## 14. Calibration readiness", ""]
    for ax, st in (body.get("calibration_readiness") or {}).items():
        lines.append(f"- {ax}: **{st}**")
    lines += [
        "",
        "## 15. Remaining blockers",
        "",
    ]
    for b in body.get("blockers") or []:
        lines.append(f"- {b}")
    lines += [
        "",
        "---",
        "",
        "## Metadata",
        "",
        f"- score_version: {meta.get('score_version')}",
        f"- analysis_version: {meta.get('analysis_version')}",
        f"- demucs_model: {meta.get('demucs_model')}",
        f"- clip_policy: {meta.get('clip_policy')}",
        f"- config_hash: {meta.get('config_hash')}",
        f"- git_commit: {meta.get('git_commit')}",
        "",
        f"## Evidence flag: **{body.get('evidence_flag', 'NO')}**",
        "",
        f"## Next action: {body.get('next_action', '')}",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
