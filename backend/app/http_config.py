"""Public HTTPS base URL and CORS — vendor-neutral, no invented hostnames."""

from __future__ import annotations

import os
from urllib.parse import urlparse

from .config import is_production

# Apps in Toss CORS (SDK 1.x–2.x). This miniapp uses granite SDK 2.x, appName=vocalfb.
# Official docs (GitBook currently renders the appName wildcard as a missing label):
#   https://developers-apps-in-toss.toss.im/documentation/integration/server-api.md
#   SDK 1.x–2.x live:  https://{appName}.apps.tossmini.com
#   SDK 1.x–2.x QR:    https://{appName}.private-apps.tossmini.com
# SDK 3.x *.web.tossmini.com origins do not apply unless this app migrates.
TOSS_MINIAPP_LIVE_ORIGIN = "https://vocalfb.apps.tossmini.com"
TOSS_MINIAPP_QR_ORIGIN = "https://vocalfb.private-apps.tossmini.com"
# Toss Console disconnect callback browser test origin (OPTIONS preflight from console UI).
TOSS_CONSOLE_ORIGIN = "https://apps-in-toss.toss.im"
TOSS_MINIAPP_PRODUCTION_ORIGINS = (
    TOSS_MINIAPP_LIVE_ORIGIN,
    TOSS_MINIAPP_QR_ORIGIN,
)
TOSS_PRODUCTION_CORS_ORIGINS = (
    *TOSS_MINIAPP_PRODUCTION_ORIGINS,
    TOSS_CONSOLE_ORIGIN,
)

DEV_CORS_DEFAULT = "http://localhost:5173,http://127.0.0.1:5173"

PUBLIC_PATH_TERMS = "/legal/terms"
PUBLIC_PATH_PRIVACY = "/legal/privacy"
PUBLIC_PATH_PRIVACY_CONSENT = "/legal/privacy-consent"
PUBLIC_PATH_TOSS_DISCONNECT = "/v1/auth/toss/disconnect"

_BANNED_HOST_MARKERS = (
    "localhost",
    "127.0.0.1",
    "example.com",
    "<production_domain>",
)


def public_backend_base_url() -> str | None:
    raw = (os.environ.get("PUBLIC_BACKEND_BASE_URL") or "").strip().rstrip("/")
    return raw or None


def public_backend_url(path: str) -> str | None:
    """Join PUBLIC_BACKEND_BASE_URL with a path. None if the base is unset."""
    base = public_backend_base_url()
    if not base:
        return None
    if not path.startswith("/"):
        path = "/" + path
    return f"{base}{path}"


def public_legal_terms_url() -> str | None:
    return public_backend_url(PUBLIC_PATH_TERMS)


def public_legal_privacy_url() -> str | None:
    return public_backend_url(PUBLIC_PATH_PRIVACY)


def public_legal_privacy_consent_url() -> str | None:
    return public_backend_url(PUBLIC_PATH_PRIVACY_CONSENT)


def public_toss_disconnect_url() -> str | None:
    return public_backend_url(PUBLIC_PATH_TOSS_DISCONNECT)


def _host_is_banned(host: str, raw: str) -> bool:
    h = (host or "").lower()
    blob = raw.lower()
    if not h:
        return True
    if h == "localhost" or h.endswith(".localhost"):
        return True
    if h == "127.0.0.1" or h.startswith("127."):
        return True
    for marker in _BANNED_HOST_MARKERS:
        if marker in h or marker in blob:
            return True
    return False


def validate_public_backend_base_url(url: str | None, *, required: bool = False) -> list[str]:
    blockers: list[str] = []
    if not url:
        if required:
            blockers.append("PUBLIC_BACKEND_BASE_URL_MISSING")
        return blockers
    parsed = urlparse(url)
    if parsed.scheme != "https":
        blockers.append("PUBLIC_BACKEND_BASE_URL_NOT_HTTPS")
    if parsed.username or parsed.password:
        blockers.append("PUBLIC_BACKEND_BASE_URL_HAS_USERINFO")
    host = parsed.hostname or ""
    if _host_is_banned(host, url):
        blockers.append("PUBLIC_BACKEND_BASE_URL_BANNED_HOST")
    if parsed.path not in ("", "/"):
        blockers.append("PUBLIC_BACKEND_BASE_URL_MUST_BE_ORIGIN")
    return blockers


def cors_origins() -> list[str]:
    """
    Production: Toss miniapp live + QR + Toss Console callback-test origin.
    No localhost, no *.
    Development: local Vite origins unless CORS_ORIGINS overrides.
    """
    if is_production():
        default = ",".join(TOSS_PRODUCTION_CORS_ORIGINS)
    else:
        default = DEV_CORS_DEFAULT
    raw = os.environ.get("CORS_ORIGINS")
    if raw is None or not str(raw).strip():
        raw = default
    origins: list[str] = []
    for item in str(raw).split(","):
        origin = item.strip().rstrip("/")
        if not origin:
            continue
        if origin == "*":
            continue
        low = origin.lower()
        if is_production() and ("localhost" in low or "127.0.0.1" in low):
            continue
        origins.append(origin)
    return list(dict.fromkeys(origins))


def validate_production_http_config() -> list[str]:
    """Fail-closed CORS / public URL rules for production. Does not print values."""
    blockers: list[str] = []
    raw = os.environ.get("CORS_ORIGINS") or ""
    raw_items = [o.strip() for o in raw.split(",") if o.strip()]
    if "*" in raw_items:
        blockers.append("CORS_WILDCARD")
    origins = cors_origins()
    if "*" in origins:
        blockers.append("CORS_WILDCARD")
    if not origins:
        blockers.append("CORS_ORIGINS_EMPTY")
    for origin in origins:
        low = origin.lower()
        if "localhost" in low or "127.0.0.1" in low:
            blockers.append("CORS_LOCALHOST")
        parsed = urlparse(origin)
        if parsed.scheme != "https":
            blockers.append("CORS_ORIGIN_NOT_HTTPS")
    blockers.extend(validate_public_backend_base_url(public_backend_base_url(), required=False))
    return list(dict.fromkeys(blockers))
