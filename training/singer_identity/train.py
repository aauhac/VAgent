# -*- coding: utf-8 -*-
"""Offline fine-tune dry-run / training entrypoint (separate container)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--labels", type=Path, default=None)
    ap.add_argument("--min-speakers", type=int, default=5)
    ap.add_argument("--min-recordings", type=int, default=3)
    args = ap.parse_args()

    n_speakers = 0
    min_rec = 0
    if args.labels and args.labels.exists():
        data = json.loads(args.labels.read_text(encoding="utf-8"))
        recs = data.get("recordings") or {}
        by = {}
        for meta in recs.values():
            sid = meta.get("singer_id")
            by[sid] = by.get(sid, 0) + 1
        n_speakers = len(by)
        min_rec = min(by.values()) if by else 0

    if args.dry_run or n_speakers < args.min_speakers or min_rec < args.min_recordings:
        print(
            json.dumps(
                {
                    "status": "SKIPPED_INSUFFICIENT_DATA",
                    "n_speakers": n_speakers,
                    "min_recordings": min_rec,
                    "message": "Fine-tune deferred until enough singer labels exist. Test set remains untouched.",
                },
                indent=2,
            )
        )
        return 0

    # Stage-5/6 placeholder — not executed without sufficient data
    print(json.dumps({"status": "NOT_IMPLEMENTED_WITHOUT_DATA"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
