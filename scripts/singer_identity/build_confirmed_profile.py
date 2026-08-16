# -*- coding: utf-8 -*-
"""Build Confirmed Singer Profile (v2 or v3) from USER_CONFIRMED recordings (cached ECAPA)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from services.singer_identity.confirmed_profile.core import run_confirmed_profile_v2  # noqa: E402
from services.singer_identity.confirmed_profile.core_v3 import run_confirmed_profile_v3  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Build confirmed singer profile")
    ap.add_argument("--singer-id", default="person_drowning_movie")
    ap.add_argument("--profile-version", type=int, default=3, choices=[2, 3])
    ap.add_argument("--manifest", type=Path, default=None)
    ap.add_argument("--embeddings-dir", type=Path, default=None)
    ap.add_argument("--segments-dir", type=Path, default=None)
    ap.add_argument("--clusters-csv", type=Path, default=None)
    ap.add_argument("--labels", type=Path, default=None)
    ap.add_argument("--output", type=Path, default=None)
    ap.add_argument("--skip-segments", action="store_true")
    args = ap.parse_args()

    common = dict(
        repo=REPO,
        singer_id=args.singer_id,
        manifest_path=args.manifest,
        embeddings_dir=args.embeddings_dir,
        segments_dir=args.segments_dir,
        clusters_csv=args.clusters_csv,
        labels_path=args.labels,
        output_dir=args.output,
        skip_segments=args.skip_segments,
    )
    if args.profile_version == 2:
        summary = run_confirmed_profile_v2(**common)
        print(
            json.dumps(
                {k: summary[k] for k in summary if k not in ("remaining_top15", "loo", "previous_high")},
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
        print("OUTPUT:", summary.get("output"))
        print("LOO MATCH:", summary["loo"]["match"], "/8")
    else:
        summary = run_confirmed_profile_v3(**common)
        slim = {
            k: summary[k]
            for k in summary
            if k
            not in (
                "remaining_top15",
                "loo",
                "hard_positives",
                "love_again",
                "multi_prototype_only",
                "strategy_rows",
                "enrollment_curve",
            )
        }
        print(json.dumps(slim, ensure_ascii=False, indent=2, default=str))
        print("OUTPUT:", summary.get("output"))
        print(
            "LOO MATCH:",
            summary["loo"]["match"],
            "/11 · love again:",
            (summary.get("love_loo") or {}).get("verification_decision"),
            "· curve:",
            summary.get("curve_trend"),
            "· strategy:",
            summary.get("strategy_verdict"),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
