# -*- coding: utf-8 -*-
"""
Regenerate human-readable audit presentation artifacts into audit_output_final_v2.

Reuses existing analysis artifacts from audit_output_final — no re-analysis.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def _copy_analysis_artifacts(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    # Copy whole tree first (keeps cache / jsonl / csv), then regenerate presentation.
    if dst.exists() and any(dst.iterdir()):
        # Prefer clean presentation dirs only
        for name in ("audio_reports", "human_validation"):
            p = dst / name
            if p.exists():
                shutil.rmtree(p)
    else:
        shutil.copytree(src, dst, dirs_exist_ok=True)
        return

    keep = {
        "concern_singletons.jsonl",
        "target_matrix.csv",
        "target_matrix.jsonl",
        "generic_collapse.csv",
        "summary.json",
        "analysis_meta.json",
        "audio_axes.csv",
        "fingerprint_sameness.json",
        "checkpoint.json",
        "apples_to_apples.json",
        "baseline_reclass.json",
    }
    for name in keep:
        s = src / name
        if s.exists():
            if s.is_dir():
                if (dst / name).exists():
                    shutil.rmtree(dst / name)
                shutil.copytree(s, dst / name)
            else:
                shutil.copy2(s, dst / name)
    # Also copy any remaining top-level json/csv/jsonl not already present
    for s in src.iterdir():
        if s.name in ("audio_reports", "report.html", "audio_reviews.json"):
            continue
        if s.suffix.lower() in (".json", ".jsonl", ".csv") and not (dst / s.name).exists():
            shutil.copy2(s, dst / s.name)
    hv = src / "human_validation"
    if hv.exists():
        # labels used as input; will be rewritten
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--src",
        type=Path,
        default=Path("audit_output_final"),
        help="Existing finalized audit dir (analysis artifacts)",
    )
    ap.add_argument(
        "--dst",
        type=Path,
        default=Path("audit_output_final_v2"),
        help="Output dir for readable presentation v2",
    )
    ap.add_argument("--repo-root", type=Path, default=Path("."))
    args = ap.parse_args()

    src = args.src.resolve()
    dst = args.dst.resolve()
    repo = args.repo_root.resolve()
    if not src.exists():
        raise SystemExit(f"missing source: {src}")

    print(f"Copying analysis artifacts: {src} -> {dst}")
    if not dst.exists():
        shutil.copytree(src, dst)
    else:
        _copy_analysis_artifacts(src, dst)

    from scripts.vocal_behavioral_audit.finalize import finalize_validation_bundle

    bundle = finalize_validation_bundle(
        repo_root=repo,
        output_dir=dst,
        baseline_dir=repo / "audit_output_baseline",
        generate_md=True,
        human_validation=True,
        reclassify_baseline=True,
    )
    print("Done:", bundle)
    print("MD:", dst / "audio_reports")
    print("HTML:", dst / "report.html")
    print("CSV:", dst / "audio_axes.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
