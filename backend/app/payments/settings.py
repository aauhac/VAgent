"""Payment / IAP configuration. Secrets are never logged."""

from __future__ import annotations

import os
from pathlib import Path

PLACEHOLDER_SKUS = frozenset(
    {
        "vagent.song_detail",
        "vagent.diagnostic_full",
        "vagent.diagnostic_upgrade",
    }
)

INTENT_TTL_SECONDS = 20 * 60  # 20 minutes — purchase intent expiry
SESSION_TTL_SECONDS = 12 * 60 * 60  # 12 hours — VAgent bearer session
ALLOWED_TOSS_API_BASES = frozenset(
    {
        "https://apps-in-toss-api.toss.im",
    }
)
DEFAULT_TOSS_API_BASE = "https://apps-in-toss-api.toss.im"

GRANTABLE_ORDER_STATUSES = frozenset({"PAYMENT_COMPLETED", "PURCHASED"})
DENY_ORDER_STATUSES = frozenset(
    {"FAILED", "REFUNDED", "ORDER_IN_PROGRESS", "NOT_FOUND", "MINIAPP_MISMATCH", "ERROR"}
)


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def payments_enabled() -> bool:
    return _env("PAYMENTS_ENABLED", "false").lower() in ("1", "true", "yes", "on")


def toss_login_enabled() -> bool:
    return _env("TOSS_LOGIN_ENABLED", "false").lower() in ("1", "true", "yes", "on")


def iap_sku_song_detail() -> str:
    return _env("IAP_SONG_DETAIL_SKU", "vagent.song_detail")


def iap_sku_diagnostic_full() -> str:
    return _env("IAP_DIAGNOSTIC_FULL_SKU", "vagent.diagnostic_full")


def iap_sku_diagnostic_upgrade() -> str:
    return _env("IAP_DIAGNOSTIC_UPGRADE_SKU", "vagent.diagnostic_upgrade")


def production_skus() -> dict[str, str]:
    return {
        "song_detail": iap_sku_song_detail(),
        "diagnostic_full": iap_sku_diagnostic_full(),
        "diagnostic_upgrade": iap_sku_diagnostic_upgrade(),
    }


def sku_is_placeholder(sku: str) -> bool:
    return (sku or "").strip() in PLACEHOLDER_SKUS or not (sku or "").strip()


def toss_api_base_url() -> str:
    return _env("TOSS_API_BASE_URL", DEFAULT_TOSS_API_BASE).rstrip("/")


def toss_mtls_cert_path() -> str:
    return _env("TOSS_MTLS_CERT_PATH")


def toss_mtls_key_path() -> str:
    return _env("TOSS_MTLS_KEY_PATH")


def session_signing_secret() -> str:
    return _env("VAGENT_SESSION_SECRET")


def backend_replicas() -> int:
    try:
        return int(_env("BACKEND_REPLICAS", "1") or "1")
    except ValueError:
        return 1
