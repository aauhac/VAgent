"""Rebuild anon-hash ↔ Toss userKey links for users migrated by the retired path.

Thin CLI over `backend.app.db.identity_linking`, which holds the logic (and is unit
tested). DRY RUN BY DEFAULT — nothing is written without --apply. Never moves or deletes
rows; it only inserts links, and it is safe to re-run.

    python scripts/backfill_identity_links.py             # report candidate count only
    python scripts/backfill_identity_links.py --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write links (default: dry run)")
    parser.add_argument("--runtime-dir", type=Path, default=None)
    args = parser.parse_args()

    from backend.app.config import database_url, get_runtime_dir

    if not database_url():
        print("FAIL: DATABASE_URL is not set")
        return 1

    from backend.app.db.identity_linking import reconcile_legacy_links
    from backend.app.db.session import session_scope

    runtime_dir = Path(args.runtime_dir or get_runtime_dir())
    with session_scope() as session:
        tally = reconcile_legacy_links(session, runtime_dir, apply=args.apply)

    print(f"discovered:     {tally.get('discovered', 0)}")
    print(f"  already_linked: {tally.get('already_linked', 0)}")
    print(f"  to_create:      {tally.get('to_create', 0)}")
    print(f"  conflict:       {tally.get('conflict', 0)}")
    if not tally.get("discovered"):
        print("nothing to backfill; remaining users repair themselves at next login")
        return 0
    if not args.apply:
        if not tally.get("to_create"):
            print("DRY RUN — nothing new to write; existing links are already correct.")
        else:
            print("DRY RUN — re-run with --apply to write. No values are printed.")
        return 0
    applied = {k: v for k, v in tally.items() if k.startswith("applied_")}
    for reason, count in sorted(applied.items()):
        print(f"  {reason}: {count}")
    print("done — idempotent, safe to re-run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
