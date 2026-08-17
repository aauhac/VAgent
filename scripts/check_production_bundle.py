"""Scan production miniapp assets for banned hosts / placeholder SKUs.

Inspects runtime web assets under miniapp/dist (JS/CSS/HTML), not source maps
and not granite local-dev config. Documentation strings in the repo are out of scope.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "miniapp" / "dist"

BANNED_PATTERNS = (
    re.compile(r"https?://localhost\b", re.I),
    re.compile(r"https?://127\.0\.0\.1\b", re.I),
    re.compile(r"wss?://localhost\b", re.I),
    re.compile(r"wss?://127\.0\.0\.1\b", re.I),
    re.compile(r"https?://(?:www\.)?example\.com\b", re.I),
    re.compile(r"<PRODUCTION_DOMAIN>", re.I),
    re.compile(r"\bvagent\.song_detail\b"),
    re.compile(r"\bvagent\.diagnostic_full\b"),
    re.compile(r"\bvagent\.diagnostic_upgrade\b"),
)

SKIP_SUFFIXES = {".map", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".woff", ".woff2", ".ttf"}
SCAN_SUFFIXES = {".js", ".css", ".html", ".json"}


def iter_runtime_files(dist: Path = DIST) -> list[Path]:
    if not dist.is_dir():
        return []
    files: list[Path] = []
    for path in dist.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        if path.suffix.lower() not in SCAN_SUFFIXES:
            continue
        files.append(path)
    return files


def scan_text(text: str) -> list[str]:
    hits: list[str] = []
    for pattern in BANNED_PATTERNS:
        if pattern.search(text):
            hits.append(pattern.pattern)
    return hits


def scan_dist(dist: Path = DIST) -> list[tuple[str, str]]:
    findings: list[tuple[str, str]] = []
    for path in iter_runtime_files(dist):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in scan_text(text):
            findings.append((str(path.relative_to(dist)).replace("\\", "/"), pattern))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", type=Path, default=DIST)
    args = parser.parse_args()
    if not args.dist.is_dir():
        print(f"FAIL: dist not found: {args.dist}", file=sys.stderr)
        return 2
    findings = scan_dist(args.dist)
    if findings:
        print("FAIL: banned host/SKU in production runtime assets")
        for rel, pattern in findings:
            print(f"  {rel}: {pattern}")
        return 1
    print(f"PASS: no banned hosts/SKUs in {args.dist}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
