"""PUBLIC_BACKEND_BASE_URL and production CORS policy."""

from __future__ import annotations

from backend.app.http_config import (
    TOSS_MINIAPP_LIVE_ORIGIN,
    TOSS_MINIAPP_QR_ORIGIN,
    cors_origins,
    public_backend_url,
    public_legal_privacy_consent_url,
    public_legal_privacy_url,
    public_legal_terms_url,
    public_toss_disconnect_url,
    validate_production_http_config,
    validate_public_backend_base_url,
)


def test_public_urls_compose_from_base(monkeypatch):
    monkeypatch.setenv("PUBLIC_BACKEND_BASE_URL", "https://backend.test")
    assert public_legal_terms_url() == "https://backend.test/legal/terms"
    assert public_legal_privacy_url() == "https://backend.test/legal/privacy"
    assert public_legal_privacy_consent_url() == "https://backend.test/legal/privacy-consent"
    assert public_toss_disconnect_url() == "https://backend.test/v1/auth/toss/disconnect"
    assert public_backend_url("legal/terms") == "https://backend.test/legal/terms"


def test_public_urls_unset_without_inventing_host(monkeypatch):
    monkeypatch.delenv("PUBLIC_BACKEND_BASE_URL", raising=False)
    assert public_legal_terms_url() is None
    assert public_toss_disconnect_url() is None


def test_public_base_rejects_localhost_and_placeholders(monkeypatch):
    assert "PUBLIC_BACKEND_BASE_URL_NOT_HTTPS" in validate_public_backend_base_url("http://backend.test")
    assert "PUBLIC_BACKEND_BASE_URL_BANNED_HOST" in validate_public_backend_base_url("https://localhost")
    assert "PUBLIC_BACKEND_BASE_URL_BANNED_HOST" in validate_public_backend_base_url("https://127.0.0.1")
    assert "PUBLIC_BACKEND_BASE_URL_BANNED_HOST" in validate_public_backend_base_url("https://example.com")
    assert "PUBLIC_BACKEND_BASE_URL_BANNED_HOST" in validate_public_backend_base_url(
        "https://<PRODUCTION_DOMAIN>"
    )
    assert validate_public_backend_base_url("https://backend.test") == []
    assert validate_public_backend_base_url(None, required=True) == ["PUBLIC_BACKEND_BASE_URL_MISSING"]
    assert validate_public_backend_base_url(None, required=False) == []


def test_production_cors_defaults_to_verified_toss_origins(monkeypatch):
    monkeypatch.setenv("VAGENT_ENV", "production")
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    monkeypatch.delenv("PUBLIC_BACKEND_BASE_URL", raising=False)
    origins = cors_origins()
    assert origins == [TOSS_MINIAPP_LIVE_ORIGIN, TOSS_MINIAPP_QR_ORIGIN]
    assert "localhost" not in ",".join(origins)
    assert "*" not in origins
    assert validate_production_http_config() == []


def test_production_cors_strips_localhost_and_rejects_wildcard(monkeypatch):
    monkeypatch.setenv("VAGENT_ENV", "production")
    monkeypatch.setenv(
        "CORS_ORIGINS",
        f"{TOSS_MINIAPP_LIVE_ORIGIN},http://localhost:5173,*",
    )
    origins = cors_origins()
    assert TOSS_MINIAPP_LIVE_ORIGIN in origins
    assert all("localhost" not in o for o in origins)
    assert "*" not in origins
    blockers = validate_production_http_config()
    assert "CORS_WILDCARD" in blockers


def test_production_cors_localhost_only_is_empty_fail(monkeypatch):
    monkeypatch.setenv("VAGENT_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    assert cors_origins() == []
    assert "CORS_ORIGINS_EMPTY" in validate_production_http_config()


def test_dev_cors_allows_vite_localhost(monkeypatch):
    monkeypatch.setenv("VAGENT_ENV", "development")
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    origins = cors_origins()
    assert "http://localhost:5173" in origins
    assert "http://127.0.0.1:5173" in origins
