# -*- coding: utf-8 -*-
"""Evaluate exported singer-id models (trainer container)."""

from __future__ import annotations

import argparse
import json


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", default="")
    args = ap.parse_args()
    print(json.dumps({"status": "use_batch_enrollment_eval", "hint": args.summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
