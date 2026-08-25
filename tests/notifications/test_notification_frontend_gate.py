"""Notification production build / CTA gating regression checks (no secret values)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MINIAPP = ROOT / "miniapp"


def test_notification_feature_available_gated_on_template_code():
    src = (MINIAPP / "src" / "lib" / "tossNotifications.ts").read_text(encoding="utf-8")
    assert "notificationFeatureAvailable" in src
    assert "VITE_TOSS_ANALYSIS_COMPLETE_TEMPLATE_CODE" in src
    assert "analysisCompleteTemplateCode" in src


def test_analyzing_cta_uses_feature_gate():
    src = (MINIAPP / "src" / "pages" / "Analyzing.tsx").read_text(encoding="utf-8")
    assert "완료 알림 받기" in src
    assert "notificationFeatureAvailable" in src
    assert "notifyOfferVisible" in src


def test_production_vite_fail_fast_for_missing_template():
    vite = (MINIAPP / "vite.config.ts").read_text(encoding="utf-8")
    assert "PRODUCTION_NOTIFICATION_TEMPLATE_CODE_MISSING" in vite
    assert "assertProductionNotificationTemplate" in vite
    assert "envDir" in vite


def test_placeholder_template_codes_banned_in_vite():
    vite = (MINIAPP / "vite.config.ts").read_text(encoding="utf-8")
    for token in ("test-template", "sample-template", "dummy", "placeholder"):
        assert token in vite


def test_no_invented_template_literals_in_source():
    notify = (MINIAPP / "src" / "lib" / "tossNotifications.ts").read_text(encoding="utf-8")
    for banned in ("test-template-code", "sample-template", "dummy-template"):
        assert banned not in notify
