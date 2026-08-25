"""Frontend payments_enabled gate — no IAP SDK when disabled."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MINIAPP = ROOT / "miniapp"


def test_use_iap_respects_payments_enabled():
    src = (MINIAPP / "src" / "lib" / "useIapProductPrices.ts").read_text(encoding="utf-8")
    assert "payments_enabled" in src
    assert "DISABLED" in src
    assert "loadIapCatalog" in src
    # enabled=false path must short-circuit before load
    assert "if (!paymentsEnabled)" in src


def test_result_hides_purchase_when_payments_disabled():
    src = (MINIAPP / "src" / "pages" / "Result.tsx").read_text(encoding="utf-8")
    assert "paymentsEnabled" in src
    # The purchase CTA exists but is rendered behind the payments gate.
    assert "에 상세 리포트 열기" in src
    assert "paymentsEnabled ?" in src or "paymentsEnabled &&" in src


def test_iap_catalog_has_disabled_state():
    src = (MINIAPP / "src" / "lib" / "iapCatalog.ts").read_text(encoding="utf-8")
    assert "'DISABLED'" in src or '"DISABLED"' in src
