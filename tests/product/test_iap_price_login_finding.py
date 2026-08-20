# -*- coding: utf-8 -*-
"""IAP price states, login cancel, vocal type reasons, findings, notifications."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MINI = ROOT / "miniapp" / "src"


def _read(rel: str) -> str:
    return (MINI / rel).read_text(encoding="utf-8")


def test_iap_catalog_never_shows_dash_price():
    catalog = _read("lib/iapCatalog.ts")
    assert "IapCatalogState" in catalog
    assert "SDK_UNAVAILABLE" in catalog
    assert "UNSUPPORTED_APP" in catalog
    assert "EMPTY" in catalog
    assert "SKU_NOT_FOUND" in catalog
    assert "가격 확인 중…" in catalog
    assert "가격 정보를 불러오지 못했어요." in catalog
    assert "catalog_start" in catalog
    assert "getProductItemList_returned_undefined" in catalog
    assert "catalog_loaded state=" in catalog
    assert "catalog_item sku=" in catalog
    assert "sku_audit product=" in catalog
    assert "price_unavailable product=" in catalog
    assert "price_state product=" in _read("lib/useIapProductPrices.ts")
    assert "expectedBackendSkus" in catalog
    assert "missing_configured_sku" in catalog
    assert "sku_not_in_toss_list" in catalog
    assert "missing_display_amount" in catalog
    assert "'—'" not in catalog
    assert "₩990" not in catalog
    assert "₩1,980" not in catalog
    assert "canPurchase" in catalog


def test_iap_catalog_states_distinguished_in_logs():
    catalog = _read("lib/iapCatalog.ts")
    assert "catalog_state=SDK_UNAVAILABLE reason=getProductItemList_returned_undefined" in catalog
    assert "catalog_state=EMPTY reason=products_array_empty" in catalog
    assert "toss_products_empty" in catalog
    assert "sku_not_in_toss_list" in catalog


def test_paid_screens_reuse_iap_price_resolver():
    for rel in (
        "pages/Result.tsx",
        "pages/PremiumUnlock.tsx",
        "pages/SongDetailReport.tsx",
        "components/report/DiagnosticCTA.tsx",
    ):
        src = _read(rel)
        assert "display_amount || '—'" not in src, rel
        assert "useState('—')" not in src, rel
        assert "₩990" not in src, rel
        assert "₩1,980" not in src, rel
    result = _read("pages/Result.tsx")
    unlock = _read("pages/PremiumUnlock.tsx")
    detail = _read("pages/SongDetailReport.tsx")
    assert "useIapProductPrices" in result
    assert "useIapProductPrices" in unlock
    assert "useIapProductPrices" in detail
    assert "canPurchase" in result
    assert "songCanBuy" in result
    assert "Toss로 바로 열기" in result or "상세 리포트 보기" in result
    assert "가격 다시 확인하기" in _read("components/ui/PremiumProductCard.tsx")
    assert "가격 다시 확인하기" in result
    assert "ensureTossLogin" not in _read("lib/iapCatalog.ts")
    assert "ensureTossLogin" not in _read("lib/useIapProductPrices.ts")


def test_login_cancel_is_silent_and_failure_has_korean():
    auth = _read("lib/tossAuth.ts")
    result = _read("pages/Result.tsx")
    unlock = _read("pages/PremiumUnlock.tsx")
    errors = _read("lib/userFacingErrors.ts")
    assert "APP_LOGIN_CANCELLED" in auth
    assert "LOGIN_SUCCESS" in auth
    assert "tossLoginUserMessage" in auth
    assert "case 'APP_LOGIN_CANCELLED':" in auth
    assert "return null" in auth
    assert "토스 로그인을 시작하지 못했어요" in errors
    assert "로그인 정보를 확인하지 못했어요" in errors
    buy = result[result.find("async function buySongDetail") : result.find("const coreAxes")]
    cancel = buy[buy.find("CANCELLED") : buy.find("!import.meta.env.PROD")]
    assert "setError" not in cancel
    start = unlock[unlock.find("async function start") : unlock.find("if (resolving")]
    cancel_u = start[start.find("CANCELLED") : start.find("토스 앱")]
    assert "setError" not in cancel_u


def test_vocal_type_unresolved_reasons_and_core_finding_states():
    hero = _read("components/report/VocalTypeHero.tsx")
    pres = _read("lib/reportPresentation.ts")
    result = _read("pages/Result.tsx")
    assert "vocalTypeUnresolvedCopy" in hero
    assert "INSUFFICIENT_EVIDENCE" in pres
    assert "CONFLICTED_EVIDENCE" in pres
    assert "NEUTRAL_EVIDENCE" in pres
    assert "발성 성향을 충분히 구분하기 어려웠어요" in pres
    assert "한쪽으로 단정하기 어려웠어요" in pres
    assert "한쪽으로 치우친 발성 성향이 뚜렷하지 않았어요" in pres
    assert "presentCoreFinding" in result
    assert "data-testid=\"core-finding\"" in result
    assert "두드러진 발성 문제는 보이지 않았어요" in pres
    assert "한 가지 문제를 핵심으로 정하기 어려웠어요" in pres
    assert "NO_PRIMARY_FOUND_MESSAGE" in pres
    assert "PRIMARY_UNRESOLVED_MESSAGE" in pres


def test_notification_cta_always_shown_checks_on_click():
    notify = _read("lib/tossNotifications.ts")
    page = _read("pages/Analyzing.tsx")
    assert "newAgreement" in notify
    assert "alreadyAgreed" in notify
    assert "agreementRejected" in notify
    assert "알림 설정을 완료하지 못했어요" in notify
    assert "지금은 완료 알림을 사용할 수 없어요." in notify
    assert "cleanup?.()" in notify
    assert "잠깐 다른 일을 보셔도 돼요." in page
    assert "분석이 끝나면 알려드릴까요?" in page
    assert "완료 알림 받기" in page
    assert "notifyAvailable" not in page
    assert "notificationFeatureAvailable" not in page
    assert "analyzing-notify" in page
    assert "requestAnalysisCompleteAgreement(id)" in page
    assert "VITE_TOSS_ANALYSIS_COMPLETE_TEMPLATE_CODE" in notify
    assert "test-template-code" not in notify
    assert "requestNotificationAgreement" not in page
    # Template/SDK checked only inside click handler path, not for render gating.
    assert "analysisCompleteTemplateCode()" not in page
