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
                f"analysis_execution_mode: {analysis_execution_mode()}",
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


def _env_bool(name: str, default: str = "false") -> bool:
    return (os.environ.get(name) or default).strip().lower() in ("1", "true", "yes", "on")


def singer_identity_enabled() -> bool:
    """Master switch — production default OFF. When false, no Singer ID service calls."""
    return _env_bool("SINGER_IDENTITY_ENABLED", "false")


def singer_identity_enrollment_enabled() -> bool:
    return singer_identity_enabled() and _env_bool("SINGER_IDENTITY_ENROLLMENT_ENABLED", "false")


def personal_vocal_baseline_enabled() -> bool:
    return _env_bool("PERSONAL_VOCAL_BASELINE_ENABLED", "false")


def singer_identity_shadow_k2_enabled() -> bool:
    """Shadow-only K2 scoring; never changes user-facing decision."""
    return singer_identity_enabled() and _env_bool("SINGER_IDENTITY_SHADOW_K2_ENABLED", "false")


def singer_identity_service_url() -> str:
    return (os.environ.get("SINGER_IDENTITY_SERVICE_URL") or "http://127.0.0.1:8100").rstrip("/")


def singer_identity_timeout_seconds() -> float:
    try:
        return float(os.environ.get("SINGER_IDENTITY_TIMEOUT_SECONDS") or "2.5")
    except ValueError:
        return 2.5


def _env_stripped(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def aws_region() -> str | None:
    """Standard AWS region env. None if unset — never invent a region."""
    return _env_stripped("AWS_REGION") or _env_stripped("AWS_DEFAULT_REGION") or None


def s3_bucket() -> str | None:
    """Future analysis-audio bucket. Unused by the live analysis path until STEP 3."""
    return _env_stripped("VAGENT_S3_BUCKET") or None


def analysis_queue_url() -> str | None:
    """Future SQS Standard queue URL. Unused by the live analysis path until STEP 3."""
    return _env_stripped("VAGENT_ANALYSIS_QUEUE_URL") or None


def analysis_dlq_url() -> str | None:
    """Optional DLQ URL for diagnostics only. Worker does not send here in STEP 2."""
    return _env_stripped("VAGENT_ANALYSIS_DLQ_URL") or None


def sqs_visibility_timeout_seconds() -> int:
    try:
        value = int(_env_stripped("VAGENT_SQS_VISIBILITY_TIMEOUT") or "600")
    except ValueError:
        value = 600
    return max(1, value)


def sqs_wait_time_seconds() -> int:
    """SQS long-poll wait; capped at the 20s API maximum."""
    try:
        value = int(_env_stripped("VAGENT_SQS_WAIT_TIME_SECONDS") or "20")
    except ValueError:
        value = 20
    return max(0, min(value, 20))


def analysis_execution_mode() -> str:
    """
    local: existing JobRunner path (default)
    queue: S3 + SQS producer; worker consumes
    Invalid values raise — never silently fall back to local.
    """
    mode, err = parse_analysis_execution_mode()
    if err or mode is None:
        raise RuntimeError(
            "VAGENT_ANALYSIS_EXECUTION_MODE is invalid; allowed: local, queue"
        )
    return mode


def parse_analysis_execution_mode() -> tuple[str | None, str | None]:
    raw = _env_stripped("VAGENT_ANALYSIS_EXECUTION_MODE")
    if not raw:
        return "local", None
    value = raw.lower()
    if value not in ("local", "queue"):
        return None, "VAGENT_ANALYSIS_EXECUTION_MODE_INVALID"
    return value, None


def sqs_heartbeat_seconds() -> int:
    vis = sqs_visibility_timeout_seconds()
    default = max(1, vis // 5)
    try:
        value = int(_env_stripped("VAGENT_SQS_HEARTBEAT_SECONDS") or str(default))
    except ValueError:
        value = default
    return max(1, value)


# SQS ChangeMessageVisibility: 0 .. 43200 seconds.
_SQS_VISIBILITY_MAX_SECONDS = 43200


def parse_sqs_retry_visibility_seconds() -> tuple[int | None, str | None]:
    raw = _env_stripped("VAGENT_SQS_RETRY_VISIBILITY_SECONDS")
    if not raw:
        return 60, None
    try:
        value = int(raw)
    except ValueError:
        return None, "VAGENT_SQS_RETRY_VISIBILITY_INVALID"
    if value < 0 or value > _SQS_VISIBILITY_MAX_SECONDS:
        return None, "VAGENT_SQS_RETRY_VISIBILITY_INVALID"
    return value, None


def sqs_retry_visibility_seconds() -> int:
    value, err = parse_sqs_retry_visibility_seconds()
    if err or value is None:
        raise RuntimeError(
            "VAGENT_SQS_RETRY_VISIBILITY_SECONDS is invalid; allowed: 0..43200"
        )
    return value


def worker_lease_seconds() -> int:
    return sqs_visibility_timeout_seconds()


def get_worker_workspace_dir() -> Path:
    raw = _env_stripped("WORKER_RUNTIME_DIR")
    path = Path(raw) if raw else (get_runtime_dir() / "_worker")
    if not path.is_absolute():
        path = project_root() / path
    path = path.resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def validate_analysis_execution_config() -> list[str]:
    """Fail-fast blockers. Invalid execution mode never becomes local."""
    mode, err = parse_analysis_execution_mode()
    if err:
        return [err]
    if mode != "queue":
        return []
    blockers: list[str] = []
    if not s3_bucket():
        blockers.append("VAGENT_S3_BUCKET_MISSING")
    if not analysis_queue_url():
        blockers.append("VAGENT_ANALYSIS_QUEUE_URL_MISSING")
    if not aws_region():
        blockers.append("AWS_REGION_MISSING")
    if not database_url():
        blockers.append("DATABASE_URL_MISSING")
    return blockers


def validate_worker_config() -> list[str]:
    """Worker always needs S3/SQS/DB; independent of API execution mode."""
    blockers: list[str] = []
    if not s3_bucket():
        blockers.append("VAGENT_S3_BUCKET_MISSING")
    if not analysis_queue_url():
        blockers.append("VAGENT_ANALYSIS_QUEUE_URL_MISSING")
    if not aws_region():
        blockers.append("AWS_REGION_MISSING")
    if not database_url():
        blockers.append("DATABASE_URL_MISSING")
    vis = sqs_visibility_timeout_seconds()
    hb = sqs_heartbeat_seconds()
    if hb >= vis:
        blockers.append("VAGENT_SQS_HEARTBEAT_INVALID")
    _, retry_err = parse_sqs_retry_visibility_seconds()
    if retry_err:
        blockers.append(retry_err)
    return blockers
