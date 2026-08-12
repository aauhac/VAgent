"""
Central backend configuration — single source of truth for paths/env.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


def project_root() -> Path:
    """Repository root (…/VocalAgent), independent of process cwd."""
    # backend/app/config.py → parents[2] == repo root
    return Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def get_runtime_dir() -> Path:
    """
    Resolve RUNTIME_DIR deterministically.

    - Absolute env path → used as-is
    - Relative env path / default \"runtime\" → resolved under project_root()
    """
    raw = (os.environ.get("RUNTIME_DIR") or "runtime").strip() or "runtime"
    path = Path(raw)
    if not path.is_absolute():
        path = project_root() / path
    path = path.resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_environment() -> str:
    return (os.environ.get("VAGENT_ENV") or "development").lower()


def is_production() -> bool:
    return get_environment() == "production"


def database_url() -> str | None:
    url = (os.environ.get("DATABASE_URL") or "").strip()
    return url or None


def entitlements_path() -> Path:
    return get_runtime_dir() / "entitlements.json"


def identity_trust_mode() -> str:
    raw = (os.environ.get("TOSS_IDENTITY_TRUST_MODE") or "UNVERIFIED_CLIENT_SUBJECT").strip().upper()
    return raw or "UNVERIFIED_CLIENT_SUBJECT"


def artifact_storage_mode() -> str:
    """
    INITIAL LAUNCH: LOCAL_PERSISTENT under RUNTIME_DIR.
    ArtifactStore abstraction exists but live pipeline still uses direct paths (OPTION B).
    MULTI_INSTANCE UNSAFE until object storage is wired.
    """
    return (os.environ.get("ARTIFACT_STORAGE_MODE") or "LOCAL_PERSISTENT").strip().upper()


def log_startup_banner() -> None:
    """Dev/startup diagnostics — never print secrets."""
    if is_production():
        return
    cwd = Path.cwd().resolve()
    root = project_root()
    runtime = get_runtime_dir()
    db = database_url()
    print(
        "\n".join(
            [
                "[VAgent startup]",
                f"cwd: {cwd}",
                f"project_root: {root}",
                f"runtime_dir: {runtime}",
                f"environment: {get_environment()}",
                f"database_url: {'set' if db else 'missing'}",
                f"entitlement_store: {entitlements_path()}",
                f"identity_trust_mode: {identity_trust_mode()}",
                f"artifact_storage_mode: {artifact_storage_mode()} (MULTI_INSTANCE UNSAFE)",
                "",
            ]
        ),
        flush=True,
    )


def runtime_writable() -> bool:
    try:
        probe = get_runtime_dir() / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False
