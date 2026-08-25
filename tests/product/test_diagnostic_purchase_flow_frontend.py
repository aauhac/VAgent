"""Diagnostic purchase order, mock removal, and unified paid-product UI.

Production bugs this pins:
  - a DiagnosticSession was created BEFORE payment, so cancelling still left a session
    behind (which the old backend then read as "unlocked")
  - `/premium?session=…` called the mock-pay endpoint unconditionally, so in production
    "영구 해제하기" could never complete a real purchase (backend 403 fail-closed)
  - the two paid products rendered as different card systems while both were locked

The miniapp has no JS test runner, so these pin the source the way tests/product does.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MINIAPP = ROOT / "miniapp"
DIST = MINIAPP / "dist"

MOCK_SYMBOLS = ("mockPaySession", "mockUnlockSongDetail")
MOCK_USER_COPY = ("Mock 결제", "mock pay", "mock-pay", "mock-unlock")


def _premium() -> str:
    return (MINIAPP / "src" / "pages" / "PremiumUnlock.tsx").read_text(encoding="utf-8")


def _result() -> str:
    return (MINIAPP / "src" / "pages" / "Result.tsx").read_text(encoding="utf-8")


def _cta() -> str:
    return (MINIAPP / "src" / "components" / "report" / "DiagnosticCTA.tsx").read_text(
        encoding="utf-8"
    )


def _start_body() -> str:
    src = _premium()
    body = src[src.index("async function start()") :]
    return body[: body.index("\n  }\n")]


# --- B: pay before creating anything --------------------------------------------------


def test_purchase_happens_before_any_session_is_created():
    body = _start_body()
    assert "buyProduct(" in body
    assert "createDiagnosticSession(" in body
    assert body.index("buyProduct(") < body.index("createDiagnosticSession(")


def test_cancelled_purchase_creates_nothing():
    """The cancel branch must return before any create/grant call."""
    body = _start_body()
    cancel = body[body.index("if (iap.state === 'CANCELLED')") :]
    cancel = cancel[: cancel.index("}")]
    assert "return" in cancel
    for forbidden in ("createDiagnosticSession", "mockPaySession", "patchHistory"):
        assert forbidden not in cancel


def test_purchase_is_confirmed_against_the_server_before_navigating():
    body = _start_body()
    assert "getAnalysisAccess(target)" in body
    assert "access?.diagnostic_unlocked" in body
    assert body.index("getAnalysisAccess(target)") < body.index("nav(`/diagnostic/${sid}")


def test_existing_session_is_reused_not_duplicated():
    body = _start_body()
    assert "access.diagnostic_session_id || existingSession" in body
    # Creation only happens when nothing usable came back.
    assert "if (!sid)" in body


# --- C/D: no mock in the production path ----------------------------------------------


def test_existing_session_unlock_uses_real_iap():
    """`/premium?session=…` must buy, not mock-pay."""
    src = _premium()
    # The old shape called mockPaySession with the URL session id straight away.
    assert "mockPaySession(existingSession" not in src
    body = _start_body()
    assert "buyProduct({ productId, resourceId: target })" in body


def test_session_route_recovers_its_analysis_for_the_intent():
    """An IAP intent needs an analysis id; the session carries source_analysis_id."""
    src = _premium()
    assert "session?.source_analysis_id" in src
    assert "setSourceAnalysisId" in src
    assert "const target = sourceAnalysisId || analysisId" in _start_body()


def test_mock_is_reachable_only_behind_a_production_guard():
    body = _start_body()
    assert "mockPaySession" in body  # dev fallback still exists
    guard = body.index("import.meta.env.PROD")
    assert guard < body.index("mockPaySession")


def _bundle_text() -> str | None:
    """Built JS, wherever the last build left it.

    build:web emits dist/assets; build:toss reorganises into dist/web/assets.
    Returns None when nothing is built — scripts/check_production_bundle.py is the gate
    that always runs against a real bundle during the release step.
    """
    assets = sorted(DIST.rglob("*.js"))
    if not assets:
        return None
    return chr(10).join(p.read_text(encoding="utf-8", errors="ignore") for p in assets)


def test_production_bundle_has_no_mock_payment_symbols():
    blob = _bundle_text()
    if blob is None:
        pytest.skip("miniapp not built")
    for symbol in MOCK_SYMBOLS:
        assert symbol not in blob, symbol


def test_production_bundle_has_no_mock_payment_user_copy():
    blob = _bundle_text()
    if blob is None:
        pytest.skip("miniapp not built")
    for copy in MOCK_USER_COPY:
        assert copy not in blob, copy


# --- E: one card system for both paid products ----------------------------------------


def test_locked_paid_products_share_the_same_card_treatment():
    """Neither locked product may render as a featured/blue panel."""
    assert "featured" not in _result()
    assert "featured" not in _cta()


def test_locked_diagnostic_cta_mirrors_song_detail_wording():
    """Both paid products lead with the price; exact strings live in
    test_purchase_ui_consistency."""
    assert "에 정밀 진단 시작하기" in _result()
    assert "에 상세 리포트 열기" in _result()
    assert "에 정밀 진단 시작하기" in _cta()


def test_recommendation_stays_a_badge():
    src = _result()
    assert "needsDiagnostic ? '추가 확인 추천'" in src


def test_unlocked_state_is_shown_as_availability():
    assert 'badge="이용 가능"' in _result()
    assert 'badge="이용 가능"' in _cta()


# --- F: server is the source of truth --------------------------------------------------


def test_song_detail_purchase_confirms_with_the_server():
    src = _result()
    body = src[src.index("async function buySongDetail()") :]
    body = body[: body.index("\n  }\n")]
    assert "getAnalysisAccess(id)" in body
    assert "access?.song_detail_unlocked" in body
    assert body.index("getAnalysisAccess(id)") < body.index("nav(`/result/${id}/detail`)")


def test_cancelled_song_detail_purchase_refetches_access():
    src = _result()
    body = src[src.index("async function buySongDetail()") :]
    body = body[: body.index("\n  }\n")]
    cancel = body[body.index("if (iap.state === 'CANCELLED')") :]
    assert "reloadAccess()" in cancel[: cancel.index("return")]


def test_premium_unlock_no_longer_writes_optimistic_unlock_state():
    """localStorage flags must not stand in for an entitlement."""
    src = _premium()
    for writer in ("saveUnlockedSession", "saveSongDetailUnlock", "patchHistory"):
        assert writer not in src, writer
