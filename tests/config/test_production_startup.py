"""Production startup fail-closed checks."""

from __future__ import annotations

from backend.app.payments.startup import (
    validate_login_production_config,
    validate_payment_production_config,
)


def test_login_enabled_requires_session_mtls_and_disconnect(monkeypatch, tmp_path):
    monkeypatch.setenv("TOSS_LOGIN_ENABLED", "true")
    monkeypatch.setenv("VAGENT_SESSION_SECRET", "")
    monkeypatch.setenv("TOSS_MTLS_CERT_PATH", "")
    monkeypatch.setenv("TOSS_MTLS_KEY_PATH", "")
    monkeypatch.setenv("TOSS_DISCONNECT_BASIC_USER", "")
    monkeypatch.setenv("TOSS_DISCONNECT_BASIC_PASSWORD", "")
    blockers = validate_login_production_config()
    assert "SESSION_SECRET_MISSING" in blockers
    assert "MTLS_CERT_MISSING" in blockers
    assert "MTLS_KEY_MISSING" in blockers
    assert "DISCONNECT_BASIC_AUTH_MISSING" in blockers


def test_login_ready_when_secret_mtls_and_disconnect_present(monkeypatch, tmp_path):
    cert = tmp_path / "client.crt"
    key = tmp_path / "client.key"
    cert.write_text("x", encoding="utf-8")
    key.write_text("y", encoding="utf-8")
    monkeypatch.setenv("TOSS_LOGIN_ENABLED", "true")
    monkeypatch.setenv("VAGENT_SESSION_SECRET", "production-session-secret")
    monkeypatch.setenv("TOSS_MTLS_CERT_PATH", str(cert))
    monkeypatch.setenv("TOSS_MTLS_KEY_PATH", str(key))
    monkeypatch.setenv("TOSS_API_BASE_URL", "https://apps-in-toss-api.toss.im")
    monkeypatch.setenv("TOSS_DISCONNECT_BASIC_USER", "callback-user")
    monkeypatch.setenv("TOSS_DISCONNECT_BASIC_PASSWORD", "callback-pass")
    assert validate_login_production_config() == []


def test_payments_reject_placeholder_sku(monkeypatch, tmp_path):
    cert = tmp_path / "client.crt"
    key = tmp_path / "client.key"
    cert.write_text("x", encoding="utf-8")
    key.write_text("y", encoding="utf-8")
    monkeypatch.setenv("PAYMENTS_ENABLED", "true")
    monkeypatch.setenv("TOSS_LOGIN_ENABLED", "true")
    monkeypatch.setenv("VAGENT_SESSION_SECRET", "production-session-secret")
    monkeypatch.setenv("TOSS_MTLS_CERT_PATH", str(cert))
    monkeypatch.setenv("TOSS_MTLS_KEY_PATH", str(key))
    monkeypatch.setenv("TOSS_DISCONNECT_BASIC_USER", "callback-user")
    monkeypatch.setenv("TOSS_DISCONNECT_BASIC_PASSWORD", "callback-pass")
    monkeypatch.setenv("IAP_SONG_DETAIL_SKU", "vagent.song_detail")
    monkeypatch.setenv("IAP_DIAGNOSTIC_FULL_SKU", "real.full")
    monkeypatch.setenv("IAP_DIAGNOSTIC_UPGRADE_SKU", "real.upgrade")
    blockers = validate_payment_production_config()
    assert any(b.startswith("PLACEHOLDER_SKU") for b in blockers)


def test_login_disabled_skips_login_validator(monkeypatch):
    monkeypatch.setenv("TOSS_LOGIN_ENABLED", "false")
    assert validate_login_production_config() == []
