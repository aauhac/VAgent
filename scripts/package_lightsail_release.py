# -*- coding: utf-8 -*-
"""Package the CURRENT working tree for Lightsail (not git HEAD alone)."""

from __future__ import annotations

import hashlib
import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "qa_output" / "production_release_v1" / "lightsail"
ARCHIVE_NAME = "vocalfb-lightsail-release.tar.gz"

EXCLUDE_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".vite",
    ".cursor",
    ".idea",
    "htmlcov",
    "coverage",
    "runtime",
    "qa_output",
    "pretrained_models",
    "outputs",
    "temp",
    "local_samples",
    "test_demucs_out",
    "singer_identity_output",
    "singer_identity_labels",
    ".audit_runtime",
    "_tmp_effort_audit",
    "dist",
    "dist-qa-visual",
}

EXCLUDE_DIR_PREFIXES = (
    "audit_output",
)

EXCLUDE_FILE_NAMES = {
    "tsconfig.tsbuildinfo",
    ".env",
    ".env.local",
    ".env.production",
}

ROOT_JUNK_PREFIXES = (
    ".pytest_",
    ".build_",
    "_audit_",
    ".effort_",
    ".coaching_",
    ".e2e_",
)

EXCLUDE_SUFFIXES = {
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".log",
    ".pyc",
    ".pyo",
    ".wav",
    ".mp3",
    ".m4a",
    ".aac",
    ".flac",
    ".ogg",
    ".wma",
    ".ait",
    ".sqlite",
    ".db",
    ".npy",
    ".npz",
    ".pt",
    ".pth",
    ".onnx",
    ".ckpt",
}

ALLOW_EXAMPLE_ENV = {
    ".env.example",
    ".env.production.example",
}

BANNED_MEMBER_PATTERNS = (
    re.compile(r"(^|/)\.env$"),
    re.compile(r"(^|/)\.env\.local$"),
    re.compile(r"(^|/)\.env\.production$"),
    re.compile(r"\.pem$", re.I),
    re.compile(r"\.key$", re.I),
    re.compile(r"\.p12$", re.I),
    re.compile(r"\.pfx$", re.I),
    re.compile(r"(^|/)node_modules(/|$)"),
    re.compile(r"(^|/)\.venv(/|$)"),
    re.compile(r"(^|/)runtime(/|$)"),
    re.compile(r"(^|/)qa_output(/|$)"),
    re.compile(r"tsconfig\.tsbuildinfo$"),
)

def _pem_begin(*words: str) -> str:
    return "-----" + " ".join(words) + "-----"


# Constructed at runtime so this source file does not contain a contiguous PEM header.
PRIVATE_KEY_MARKERS = (
    _pem_begin("BEGIN", "PRIVATE", "KEY"),
    _pem_begin("BEGIN", "RSA", "PRIVATE", "KEY"),
    _pem_begin("BEGIN", "EC", "PRIVATE", "KEY"),
    _pem_begin("BEGIN", "OPENSSH", "PRIVATE", "KEY"),
)

SESSION_SECRET_RE = re.compile(
    r"(?m)^[ \t]*VAGENT_SESSION_SECRET[ \t]*=[ \t]*(.*)$",
    re.I,
)
DB_URL_RE = re.compile(
    r"(?m)^[ \t]*DATABASE_URL[ \t]*=[ \t]*(.*)$",
    re.I,
)

TEXT_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
    ".md",
    ".yml",
    ".yaml",
    ".toml",
    ".ini",
    ".txt",
    ".sh",
    ".ps1",
    ".css",
    ".html",
    ".example",
    ".cfg",
    ".conf",
    ".template",
}


def _posix(rel: Path) -> str:
    return rel.as_posix()


def should_skip_dir(name: str) -> bool:
    if name in EXCLUDE_DIR_NAMES:
        return True
    return any(name.startswith(p) for p in EXCLUDE_DIR_PREFIXES)


def should_skip_file(path: Path) -> bool:
    name = path.name
    if name in ALLOW_EXAMPLE_ENV:
        return False
    if name in EXCLUDE_FILE_NAMES:
        return True
    if name.startswith(".e2e_"):
        return True
    if path.parent == ROOT and any(name.startswith(p) for p in ROOT_JUNK_PREFIXES):
        return True
    if path.suffix.lower() in EXCLUDE_SUFFIXES:
        return True
    if name.startswith(".env") and name not in ALLOW_EXAMPLE_ENV:
        return True
    return False


def collect_files() -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]
        base = Path(dirpath)
        for fn in filenames:
            p = base / fn
            if should_skip_file(p):
                continue
            files.append(p)
    files.sort()
    return files


def git_state() -> str:
    def run(args: list[str]) -> str:
        try:
            out = subprocess.check_output(args, cwd=ROOT, text=True, stderr=subprocess.STDOUT)
            return out.strip()
        except Exception as exc:  # noqa: BLE001
            return f"(unavailable: {type(exc).__name__})"

    head = run(["git", "rev-parse", "HEAD"])
    ahead_behind = run(["git", "rev-list", "--left-right", "--count", "origin/main...HEAD"])
    status = run(["git", "status", "--short"])
    return "\n".join(
        [
            f"HEAD={head}",
            f"origin/main...HEAD={ahead_behind}",
            "git status --short:",
            status or "(clean)",
            f"packaged_at_utc={datetime.now(timezone.utc).isoformat()}",
        ]
    )


def scan_member_names(members: list[str]) -> list[str]:
    hits: list[str] = []
    for name in members:
        for pat in BANNED_MEMBER_PATTERNS:
            if pat.search(name):
                if Path(name).name in ALLOW_EXAMPLE_ENV:
                    continue
                hits.append(name)
                break
    return hits


def _looks_like_real_secret_assignment(raw: str) -> bool:
    val = raw.strip().strip("'").strip('"')
    if not val:
        return False
    placeholders = (
        "change-me",
        "changeme",
        "replace-me",
        "your-secret",
        "todo",
        "xxx",
        "<secret>",
    )
    low = val.lower()
    if any(p in low for p in placeholders):
        return False
    if val.endswith("PASSWORD") or val.endswith("USER"):
        return False
    return len(val) >= 8


def _looks_like_real_database_url(raw: str) -> bool:
    val = raw.strip().strip("'").strip('"')
    if not val:
        return False
    low = val.lower()
    if "user:password" in low or "user:pass@" in low:
        return False
    if "vagent:vagent@" in low:
        return False
    if "localhost" in low or "127.0.0.1" in low:
        return False
    if "@postgres:" in val and "PASSWORD" in val:
        return False
    return "@" in val and "://" in val


def scan_contents(files: list[Path]) -> list[str]:
    """Return relative paths only. Never include secret values."""
    hits: list[str] = []
    for path in files:
        suffix = path.suffix.lower()
        if suffix not in TEXT_SUFFIXES and path.name not in ALLOW_EXAMPLE_ENV:
            if suffix not in {".sh", ".ps1", ""} and "Dockerfile" not in path.name:
                continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        rel = _posix(path.relative_to(ROOT))
        if rel.endswith("scripts/package_lightsail_release.py"):
            continue
        upper = text.upper()
        if any(marker in upper for marker in PRIVATE_KEY_MARKERS):
            hits.append(rel)
            continue
        for m in SESSION_SECRET_RE.finditer(text):
            line_start = text.rfind("\n", 0, m.start()) + 1
            line = text[line_start : m.end()]
            if line.lstrip().startswith("#") or line.lstrip().startswith("//"):
                continue
            if path.name in ALLOW_EXAMPLE_ENV and not m.group(1).strip():
                continue
            if _looks_like_real_secret_assignment(m.group(1)):
                hits.append(rel)
                break
        else:
            for m in DB_URL_RE.finditer(text):
                line_start = text.rfind("\n", 0, m.start()) + 1
                line = text[line_start : m.end()]
                if line.lstrip().startswith("#") or line.lstrip().startswith("//"):
                    continue
                if path.name in ALLOW_EXAMPLE_ENV:
                    continue
                if _looks_like_real_database_url(m.group(1)):
                    hits.append(rel)
                    break
    return hits


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def required_present(members: list[str]) -> list[str]:
    need = [
        "backend/app/main.py",
        "backend/alembic/env.py",
        "alembic.ini",
        "requirements.txt",
        "audio_analyzer/pipeline.py",
        "docs/legal/TERMS_OF_SERVICE.ko.md",
        "docs/legal/PRIVACY_POLICY.ko.md",
        "docs/legal/PRIVACY_COLLECTION_CONSENT.ko.md",
        "deploy/lightsail/Dockerfile.backend",
        "deploy/lightsail/docker-compose.production.yml",
        "deploy/lightsail/deploy.sh",
        "miniapp/src/lib/unavailableAxisReason.ts",
        "miniapp/src/pages/Home.tsx",
        ".env.production.example",
    ]
    missing = [n for n in need if n not in members]
    return missing


def main() -> int:
    print(f"ROOT={ROOT}")
    files = collect_files()
    print(f"staging files={len(files)}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    archive = OUT_DIR / ARCHIVE_NAME

    with tempfile.TemporaryDirectory(prefix="vocalfb-lightsail-pack-") as tmp:
        # Copy to a clean tree first so tar members are relative and stable.
        staging = Path(tmp) / "src"
        for src in files:
            dest = staging / src.relative_to(ROOT)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        staged = [p for p in staging.rglob("*") if p.is_file()]
        # Rewrite collect relative to staging for tar
        members: list[str] = []
        if archive.exists():
            archive.unlink()
        with tarfile.open(archive, "w:gz", format=tarfile.PAX_FORMAT) as tf:
            for path in sorted(staged):
                rel = path.relative_to(staging)
                name = _posix(rel)
                data = path.read_bytes()
                if name.endswith(".sh") or name.endswith(".ps1"):
                    data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
                info = tarfile.TarInfo(name=name)
                info.size = len(data)
                info.mtime = int(path.stat().st_mtime)
                info.mode = 0o755 if name.endswith(".sh") else 0o644
                tf.addfile(info, io.BytesIO(data))
                members.append(name)

    name_hits = scan_member_names(members)
    if name_hits:
        print("FAIL: banned archive members (paths only)")
        for n in name_hits:
            print(f"  {n}")
        return 1

    content_hits = scan_contents(files)
    if content_hits:
        print("FAIL: secret-like content (paths only)")
        for n in content_hits:
            print(f"  {n}")
        return 1

    missing = required_present(members)
    if missing:
        print("FAIL: required production files missing from archive")
        for n in missing:
            print(f"  {n}")
        return 1

    digest = sha256_file(archive)
    (OUT_DIR / "vocalfb-lightsail-release.sha256").write_text(
        f"{digest}  {ARCHIVE_NAME}\n", encoding="utf-8"
    )
    (OUT_DIR / "MANIFEST.txt").write_text(
        "\n".join(members) + "\n", encoding="utf-8"
    )
    (OUT_DIR / "DEPLOY_SOURCE_STATE.txt").write_text(git_state() + "\n", encoding="utf-8")

    size = archive.stat().st_size
    print(f"PASS archive={archive}")
    print(f"PASS size_bytes={size}")
    print(f"PASS sha256={digest}")
    print(f"PASS members={len(members)}")
    print("SECRET FILE SCAN: PASS")
    print("SECRET CONTENT SCAN: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
