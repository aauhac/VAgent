"""One production purchase presentation across all three purchase surfaces.

Result, DiagnosticCTA and PremiumUnlock used to render locked paid products three
different ways — white card, white card, blue featured card — with two different CTA
verbs. That was drift, not deliberate differentiation.

Locked paid products now share `variant="purchase"`, and `featured` is a compile error on
that variant, so a purchase card cannot become a highlighted panel again. Recommendation is
carried by a badge only.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MINIAPP = ROOT / "miniapp"
DIST = MINIAPP / "dist"

# Price-leading wording so the button reads as a paid purchase, not a navigation link.
DETAIL_CTA = "에 상세 리포트 열기"
DIAGNOSTIC_CTA = "에 정밀 진단 시작하기"
REWARDED_CTA = "광고 보고 무료로 열기"
# Retired wording — must not survive anywhere user-facing.
BANNED_CTAS = ("Toss로 바로 열기", "Toss로 바로 시작", "정밀 진단 시작 ·")


def _read(rel: str) -> str:
    return (MINIAPP / rel).read_text(encoding="utf-8")


def _card() -> str:
    return _read("src/components/ui/PremiumProductCard.tsx")


def _result() -> str:
    return _read("src/pages/Result.tsx")


def _cta() -> str:
    return _read("src/components/report/DiagnosticCTA.tsx")


def _premium() -> str:
    return _read("src/pages/PremiumUnlock.tsx")


def _bundle() -> str | None:
    assets = sorted(DIST.rglob("*.js")) + sorted(DIST.rglob("*.css"))
    if not assets:
        return None
    return chr(10).join(p.read_text(encoding="utf-8", errors="ignore") for p in assets)


# --- the shared component ---------------------------------------------------------------


def test_purchase_variant_exists():
    src = _card()
    assert "variant: 'purchase'" in src
    assert "is-purchase" in src


def test_featured_is_impossible_on_a_purchase_card():
    """Type-level, not convention: `featured?: never` on the purchase branch."""
    src = _card()
    assert "featured?: never" in src
    # And defensively at runtime, so a cast cannot sneak it through.
    assert "variant === 'purchase' ? false" in src


def test_purchase_style_is_defined_and_wins_over_featured():
    css = _read("src/styles/app.css")
    assert ".premium-card.is-purchase" in css
    assert ".premium-card.is-purchase.is-featured" in css
    assert css.index(".premium-card.is-featured {") < css.index(".premium-card.is-purchase")


# --- no featured on any locked purchase surface -----------------------------------------


@pytest.mark.parametrize(
    "name,src",
    [
        ("Result", _result()),
        ("DiagnosticCTA", _cta()),
        ("PremiumUnlock", _premium()),
    ],
)
def test_no_featured_on_purchase_surfaces(name, src):
    assert "featured" not in src, name


def test_all_three_surfaces_use_the_purchase_variant():
    assert 'variant="purchase"' in _result()
    assert 'variant="purchase"' in _cta()
    assert 'variant="purchase"' in _premium()


def test_locked_song_detail_shares_the_purchase_surface():
    """Its rewarded-ad block cannot be card props, so it carries the same class instead."""
    src = _result()
    assert 'className="premium-card is-purchase"' in src


# --- CTA wording -------------------------------------------------------------------------


def test_song_detail_cta_leads_with_the_price():
    src = _result()
    assert "`${songPriceLabel}" + DETAIL_CTA + "`" in src


def test_diagnostic_cta_wording_is_identical_everywhere():
    """Entering PremiumUnlock must not change the wording the user just tapped."""
    assert "`${diagPriceLabel}" + DIAGNOSTIC_CTA + "`" in _result()
    assert "`${priceLabel}" + DIAGNOSTIC_CTA + "`" in _cta()
    assert "`${displayAmount}" + DIAGNOSTIC_CTA + "`" in _premium()


def test_rewarded_cta_is_unchanged():
    assert REWARDED_CTA in _result()


def test_retired_cta_wording_is_gone_from_source():
    for name, src in (("Result", _result()), ("CTA", _cta()), ("Premium", _premium())):
        for banned in BANNED_CTAS:
            assert banned not in src, f"{name}: {banned}"


def test_recommendation_is_a_badge_not_a_highlight():
    assert "needsDiagnostic ? '추가 확인 추천'" in _result()


# --- built bundle -------------------------------------------------------------------------


def test_bundle_has_no_retired_cta_wording():
    blob = _bundle()
    if blob is None:
        pytest.skip("miniapp not built")
    for banned in BANNED_CTAS:
        assert banned not in blob, banned


def test_bundle_ships_the_purchase_style_and_new_wording():
    blob = _bundle()
    if blob is None:
        pytest.skip("miniapp not built")
    assert "is-purchase" in blob
    assert DETAIL_CTA in blob
    assert DIAGNOSTIC_CTA in blob
    assert REWARDED_CTA in blob
