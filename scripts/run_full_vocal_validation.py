#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""VAgent Full Vocal Validation wrapper

Runs: discovery → analyze → concern/target/safety/pairs → human validation →
baseline reclassification → per-audio Markdown → HTML.

Usage:
  python scripts/run_full_vocal_validation.py --full
  python scripts/run_full_vocal_validation.py --quick
  python scripts/run_full_vocal_validation.py --generate-md-only --output-dir audit_output_final
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _ensure_cache_link(output_dir: Path, cache_sources: list[Path]) -> None:
    cache = output_dir / "cache"
    if cache.exists():
        return
    for src in cache_sources:
        if src.exists():
            try:
                cache.symlink_to(src, target_is_directory=True)
                return
            except Exception:
                try:
                    # Windows junction via mklink may fail in some shells; copy is last resort
                    if sys.platform == "win32":
                        import subprocess

                        subprocess.run(
                            ["cmd", "/c", "mklink", "/J", str(cache), str(src)],
                            check=False,
                            capture_output=True,
                        )
                        if cache.exists():
                            return
                except Exception:
                    pass
    cache.mkdir(parents=True, exist_ok=True)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="VAgent full vocal validation + MD + human labels")
    p.add_argument("--output-dir", type=str, default="audit_output_final")
    p.add_argument("--baseline-dir", type=str, default="audit_output_baseline")
    p.add_argument("--labels", type=str, default="audit_labels/human_audio_labels.json")
    p.add_argument("--quick", action="store_true")
    p.add_argument("--full", action="store_true")
    p.add_argument("--generate-md-only", action="store_true")
    p.add_argument("--force-reanalyze", action="store_true")
    p.add_argument("--max-audios", type=int, default=None)
    p.add_argument("--skip-pairs", action="store_true")
    args = p.parse_args(argv)

    output_dir = (ROOT / args.output_dir).resolve()
    baseline_dir = (ROOT / args.baseline_dir).resolve()
    labels_path = (ROOT / args.labels).resolve()

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
        print(json.dumps({"ok": True, "mode": "md-only", **{k: result.get(k) for k in result}}, ensure_ascii=False, indent=2, default=str))
        return 0

    _ensure_cache_link(
        output_dir,
        [
            ROOT / "audit_output_after" / "cache",
            ROOT / "audit_output" / "cache",
        ],
    )

    from scripts.vocal_behavioral_audit.runner import run_audit

    summary = run_audit(
        repo_root=ROOT,
        output_dir=output_dir,
        force_reanalyze=args.force_reanalyze,
        max_audios=args.max_audios,
        quick=args.quick,
        full=args.full or (not args.quick),
        skip_pairs=args.skip_pairs,
        generate_md=True,
        human_validation=True,
        reclassify_baseline=True,
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
                "markdown": (summary.get("validation_finalize") or {}).get("markdown_count"),
                "human_labeled": (summary.get("validation_finalize") or {}).get("human_labeled"),
                "summary": str(output_dir / "summary.json"),
                "md_index": str(output_dir / "audio_reports" / "index.md"),
                "md_summary": str(output_dir / "audio_reports" / "summary.md"),
                "html": str(output_dir / "report.html"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
