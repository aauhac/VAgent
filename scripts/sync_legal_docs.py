#!/usr/bin/env python3
"""Copy canonical docs/legal public markdown into miniapp/src/legal."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "legal"
DST = ROOT / "miniapp" / "src" / "legal"

FILES = (
    "TERMS_OF_SERVICE.ko.md",
    "PRIVACY_POLICY.ko.md",
    "PRIVACY_COLLECTION_CONSENT.ko.md",
)


def main() -> int:
    DST.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        src = SRC / name
        if not src.is_file():
            print(f"FAIL: missing {src}", file=sys.stderr)
            return 1
        shutil.copyfile(src, DST / name)
        print(f"synced {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
