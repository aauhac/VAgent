"""Scan production miniapp assets for banned hosts / placeholder SKUs.

Also fails if public legal markdown still contains draft/TODO release blockers.
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

LEGAL_PUBLIC = (
    ROOT / "docs" / "legal" / "TERMS_OF_SERVICE.ko.md",
    ROOT / "docs" / "legal" / "PRIVACY_POLICY.ko.md",
    ROOT / "docs" / "legal" / "PRIVACY_COLLECTION_CONSENT.ko.md",
    ROOT / "miniapp" / "src" / "legal" / "TERMS_OF_SERVICE.ko.md",
    ROOT / "miniapp" / "src" / "legal" / "PRIVACY_POLICY.ko.md",
    ROOT / "miniapp" / "src" / "legal" / "PRIVACY_COLLECTION_CONSENT.ko.md",
)

LEGAL_BLOCKERS = (
    "[TODO:",
    "TODO_BEFORE_PRODUCTION",
    "POLICY_DECISION_REQUIRED",
    "PRODUCTION_HOSTING_DECISION_REQUIRED",
    "LEGAL_REVIEW_REQUIRED",
    "draft-2",
)


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


def scan_legal_sources() -> list[str]:
    hits: list[str] = []
    for path in LEGAL_PUBLIC:
        if not path.is_file():
            hits.append(f"missing:{path.relative_to(ROOT).as_posix()}")
            continue
        text = path.read_text(encoding="utf-8")
        for token in LEGAL_BLOCKERS:
            if token in text:
                hits.append(f"{path.relative_to(ROOT).as_posix()}:{token}")
    return hits


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", type=Path, default=DIST)
    args = parser.parse_args()
    legal_hits = scan_legal_sources()
    if legal_hits:
        print("FAIL: legal release blockers in public markdown")
        for h in legal_hits:
            print(f"  {h}")
        return 1
    if not args.dist.is_dir():
        print(f"FAIL: dist not found: {args.dist}", file=sys.stderr)
        return 2
    findings = scan_dist(args.dist)
    if findings:
        print("FAIL: banned host/SKU in production runtime assets")
        for rel, pattern in findings:
            print(f"  {rel}: {pattern}")
        return 1
    print("PASS: legal sources have no release blockers")
    print(f"PASS: no banned hosts/SKUs in {args.dist}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
