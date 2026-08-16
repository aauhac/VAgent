#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""VAgent Full Audio × Checklist Behavioral Audit

Usage:
  python scripts/audit_all_vocal_assets.py --full
  python scripts/audit_all_vocal_assets.py --full --generate-md --human-validation
  python scripts/audit_all_vocal_assets.py --generate-md-only --output-dir audit_output_final
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="VAgent behavioral audit harness")
    p.add_argument("--audio-root", type=str, default=None, help="Limit discovery to this root")
    p.add_argument("--output-dir", type=str, default="audit_output", help="Artifact directory")
    p.add_argument("--force-reanalyze", action="store_true")
    p.add_argument("--max-audios", type=int, default=None)
    p.add_argument("--skip-target-sweep", action="store_true")
    p.add_argument("--skip-pairs", action="store_true")
    p.add_argument("--skip-html", action="store_true")
    p.add_argument("--only-concern", type=str, default=None)
    p.add_argument("--only-audio", type=str, default=None)
    p.add_argument("--quick", action="store_true", help="3 audios × all concerns smoke")
    p.add_argument("--full", action="store_true", help="All discovered audios + sweeps")
    p.add_argument("--generate-md", action="store_true", help="Write per-audio Markdown reports")
    p.add_argument("--human-validation", action="store_true", help="Compare human labels after analysis")
    p.add_argument("--reclassify-baseline", action="store_true", help="Reclassify baseline with current classifiers")
    p.add_argument("--generate-md-only", action="store_true", help="Rebuild MD/human/baseline from existing artifacts")
    p.add_argument("--labels", type=str, default="audit_labels/human_audio_labels.json")
    p.add_argument("--baseline-dir", type=str, default="audit_output_baseline")
    args = p.parse_args(argv)

    output_dir = (ROOT / args.output_dir).resolve()
    labels_path = (ROOT / args.labels).resolve()
    baseline_dir = (ROOT / args.baseline_dir).resolve()

    if args.generate_md_only:
        from scripts.vocal_behavioral_audit.finalize import finalize_validation_bundle

        result = finalize_validation_bundle(
            repo_root=ROOT,
            output_dir=output_dir,
            baseline_dir=baseline_dir if baseline_dir.exists() else None,
            labels_path=labels_path if labels_path.exists() else None,
            generate_md=True,
            human_validation=True,
            reclassify_baseline=True,
        )
        print(json.dumps({"ok": True, "mode": "md-only", "reviews": result.get("reviews")}, ensure_ascii=False, indent=2))
        return 0

    from scripts.vocal_behavioral_audit.runner import run_audit

    summary = run_audit(
        repo_root=ROOT,
        output_dir=output_dir,
        audio_root=Path(args.audio_root).resolve() if args.audio_root else None,
        force_reanalyze=args.force_reanalyze,
        max_audios=args.max_audios,
        quick=args.quick,
        full=args.full or (not args.quick),
        skip_target_sweep=args.skip_target_sweep,
        skip_pairs=args.skip_pairs,
        skip_html=args.skip_html,
        only_concern=args.only_concern,
        only_audio=args.only_audio,
        generate_md=args.generate_md,
        human_validation=args.human_validation,
        reclassify_baseline=args.reclassify_baseline,
        labels_path=labels_path if labels_path.exists() else None,
        baseline_dir=baseline_dir if baseline_dir.exists() else None,
    )
    print(
        json.dumps(
            {
                "ok": True,
                "audios": summary.get("audios"),
                "singleton_cases": summary.get("singleton_cases"),
                "canonical_mutations": summary.get("canonical_mutations"),
                "elapsed_sec": summary.get("elapsed_sec"),
                "summary": str(output_dir / "summary.json"),
                "html": str(output_dir / "report.html"),
                "md_index": str(output_dir / "audio_reports" / "index.md")
                if args.generate_md
                else None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
