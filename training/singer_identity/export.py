# -*- coding: utf-8 -*-
"""Export model artifacts for inference image."""

from __future__ import annotations

import argparse
import json


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="export")
    args = ap.parse_args()
    print(json.dumps({"status": "NO_FINETUNED_WEIGHTS", "out": args.out}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
