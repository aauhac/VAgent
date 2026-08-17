"""Production fail-closed checks for payments / identity / mTLS / SKUs."""

from __future__ import annotations

import os
from pathlib import Path

from .settings import (
    ALLOWED_TOSS_API_BASES,
    payments_enabled,
    production_skus,
    session_signing_secret,
    sku_is_placeholder,
    toss_api_base_url,
    toss_login_enabled,
    toss_mtls_cert_path,
    toss_mtls_key_path,
)


class ProductionConfigError(RuntimeError):
    pass


def _readable_file(path: str, label: str) -> None:
    if not path:
        raise ProductionConfigError(f"{label} is required when PAYMENTS_ENABLED=true")
    p = Path(path)
    if not p.is_file():
        raise ProductionConfigError(f"{label} file is missing")
    if not os.access(p, os.R_OK):
        raise ProductionConfigError(f"{label} file is not readable")


def _disconnect_basic_configured() -> bool:
    user = (os.environ.get("TOSS_DISCONNECT_BASIC_USER") or "").strip()
    password = (os.environ.get("TOSS_DISCONNECT_BASIC_PASSWORD") or "").strip()
    return bool(user and password)


def validate_login_production_config() -> list[str]:
    """
    Fail-closed checks when TOSS_LOGIN_ENABLED=true.
    Does not print secret values.
    """
    blockers: list[str] = []
    if not toss_login_enabled():
        return blockers
    secret = session_signing_secret()
    if not secret or secret == "dev-only-unverified-session-secret":
        blockers.append("SESSION_SECRET_MISSING")
    try:
        _readable_file(toss_mtls_cert_path(), "TOSS_MTLS_CERT_PATH")
    except ProductionConfigError:
        blockers.append("MTLS_CERT_MISSING")
    try:
        _readable_file(toss_mtls_key_path(), "TOSS_MTLS_KEY_PATH")
    except ProductionConfigError:
        blockers.append("MTLS_KEY_MISSING")
    base = toss_api_base_url()
    if base not in ALLOWED_TOSS_API_BASES:
        blockers.append("TOSS_API_BASE_NOT_ALLOWLISTED")
    if not _disconnect_basic_configured():
        blockers.append("DISCONNECT_BASIC_AUTH_MISSING")
    return list(dict.fromkeys(blockers))


def validate_payment_production_config(*, payments_on: bool | None = None) -> list[str]:
    """
    Return a list of blocker codes. Empty means pass.
    Does not print secret values.
    """
    blockers: list[str] = []
    enabled = payments_enabled() if payments_on is None else payments_on
    if not enabled:
        return blockers
    if not toss_login_enabled():
        blockers.append("TOSS_LOGIN_NOT_ENABLED")
    blockers.extend(validate_login_production_config())
    secret = session_signing_secret()
    if not secret or secret == "dev-only-unverified-session-secret":
        blockers.append("SESSION_SECRET_MISSING")
    try:
        _readable_file(toss_mtls_cert_path(), "TOSS_MTLS_CERT_PATH")
    except ProductionConfigError:
        blockers.append("MTLS_CERT_MISSING")
    try:
        _readable_file(toss_mtls_key_path(), "TOSS_MTLS_KEY_PATH")
    except ProductionConfigError:
        blockers.append("MTLS_KEY_MISSING")
    base = toss_api_base_url()
    if base not in ALLOWED_TOSS_API_BASES:
        blockers.append("TOSS_API_BASE_NOT_ALLOWLISTED")
    for name, sku in production_skus().items():
        if sku_is_placeholder(sku):
            blockers.append(f"PLACEHOLDER_SKU_{name.upper()}")
    trust = (os.environ.get("TOSS_IDENTITY_TRUST_MODE") or "").strip().upper()
    if trust == "VERIFIED_TOSS_SUBJECT":
        # Env flag alone is not verified identity. Payments still require Toss login config.
        if "TOSS_LOGIN_NOT_ENABLED" not in blockers and not toss_login_enabled():
            blockers.append("UNVERIFIED_IDENTITY_WITH_PAYMENTS")
    if not toss_login_enabled():
        blockers.append("UNVERIFIED_IDENTITY_WITH_PAYMENTS")
    mock = (os.environ.get("ALLOW_MOCK_PREMIUM") or "").strip().lower()
    if mock in ("1", "true", "yes", "on"):
        blockers.append("MOCK_PREMIUM_ENABLED")
    return list(dict.fromkeys(blockers))


def assert_production_payments_ready() -> None:
    blockers = validate_payment_production_config()
    if blockers:
        raise ProductionConfigError(
            "production payments are not ready: " + ",".join(blockers)
        )
