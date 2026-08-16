# -*- coding: utf-8 -*-
"""Re-evaluate confirmed singer profile (deterministic re-run)."""

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
    ap = argparse.ArgumentParser(description="Evaluate confirmed singer profile")
    ap.add_argument("--singer-id", default="person_drowning_movie")
    ap.add_argument("--profile-version", type=int, default=3, choices=[2, 3])
    ap.add_argument("--skip-segments", action="store_true")
    args = ap.parse_args()
    if args.profile_version == 2:
        summary = run_confirmed_profile_v2(
            repo=REPO, singer_id=args.singer_id, skip_segments=args.skip_segments
        )
        print(
            json.dumps(
                {
                    "loo": summary["loo"],
                    "enrollment_improves": summary["enrollment_improves"],
                    "remaining_counts": summary["remaining_counts"],
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
    else:
        summary = run_confirmed_profile_v3(
            repo=REPO, singer_id=args.singer_id, skip_segments=args.skip_segments
        )
        print(
            json.dumps(
                {
                    "loo": {
                        "match": summary["loo"]["match"],
                        "uncertain": summary["loo"]["uncertain"],
                        "non_match": summary["loo"]["non_match"],
                        "mean_sim": summary["loo"]["mean_sim"],
                        "min_sim": summary["loo"]["min_sim"],
                    },
                    "love_loo": summary.get("love_loo"),
                    "curve_trend": summary.get("curve_trend"),
                    "strategy_verdict": summary.get("strategy_verdict"),
                    "remaining_counts": summary["remaining_counts"],
                    "false_accept": summary.get("false_accept"),
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
