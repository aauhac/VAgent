"""Rewarded ad must actually reach the production build, and share one decision area.

Creating the ad group in the Apps in Toss Console does not connect it to the app: the
production build reads `VITE_TOSS_REWARDED_DETAIL_AD_GROUP_ID`, and with that key missing
`rewardedAdFeatureConfigured()` is false and the whole free-unlock option disappears.

Free and paid unlock are one decision, so both buttons live in a single action group
inside the same card rather than stacking as separate blocks.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MINIAPP = ROOT / "miniapp"
DIST = MINIAPP / "dist"

LIVE_AD_GROUP_ID = "ait.v2.live.55d11c8fe5c34004"
TEST_AD_GROUP_ID = "ait-ad-test-rewarded-id"
ENV_KEY = "VITE_TOSS_REWARDED_DETAIL_AD_GROUP_ID"

REWARDED_CTA = "광고 보고 무료로 열기"
DETAIL_PURCHASE_CTA = "에 상세 리포트 열기"
DIAGNOSTIC_CTA = "에 정밀 진단 시작하기"


def _read(rel: str) -> str:
    return (MINIAPP / rel).read_text(encoding="utf-8")


def _result() -> str:
    return _read("src/pages/Result.tsx")


def _ad_lib() -> str:
    return _read("src/lib/tossRewardedAd.ts")


def _bundle() -> str | None:
    assets = sorted(DIST.rglob("*.js")) + sorted(DIST.rglob("*.css"))
    if not assets:
        return None
    return chr(10).join(p.read_text(encoding="utf-8", errors="ignore") for p in assets)


# --- env wiring --------------------------------------------------------------------------


def test_ad_group_id_is_env_driven_not_hardcoded():
    """The live ID must never be compiled into a TS file."""
    for rel in ("src/lib/tossRewardedAd.ts", "src/lib/useRewardedDetailUnlock.ts", "src/pages/Result.tsx"):
        assert LIVE_AD_GROUP_ID not in _read(rel), rel
    assert ENV_KEY in _ad_lib()


def test_production_never_falls_back_to_the_test_ad_group():
    src = _ad_lib()
    body = src[src.index("export function rewardedDetailAdGroupId()") :]
    body = body[: body.index("\n}\n")]
    assert "if (!import.meta.env.PROD)" in body
    # Production returns empty rather than a test ID it must not run ads against.
    assert body.rstrip().endswith("return '';")


def test_production_env_file_carries_the_live_ad_group():
    env = MINIAPP / ".env.production.local"
    if not env.exists():
        pytest.skip("production env file is gitignored and absent here")
    active = [
        line
        for line in env.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    values = dict(line.partition("=")[::2] for line in active)
    assert values.get(ENV_KEY) == LIVE_AD_GROUP_ID


def test_bundle_ships_the_live_ad_group_and_not_the_test_one():
    blob = _bundle()
    if blob is None:
        pytest.skip("miniapp not built")
    assert LIVE_AD_GROUP_ID in blob
    assert TEST_AD_GROUP_ID not in blob


# --- one decision area --------------------------------------------------------------------


def test_free_and_paid_share_one_action_group():
    src = _result()
    block = src[src.index('<div className="purchase-choice-actions">') :]
    block = block[: block.index("</div>")]
    assert "unlockViaRewardedAd" in block
    assert "buySongDetail" in block


def test_action_group_is_responsive():
    css = _read("src/styles/app.css")
    assert ".purchase-choice-actions" in css
    assert "grid-template-columns: 1fr;" in css
    assert "grid-template-columns: 1fr 1fr;" in css
    assert "@media (min-width: 380px)" in css


def test_action_group_buttons_share_height_and_radius():
    css = _read("src/styles/app.css")
    block = css[css.index(".purchase-choice-actions > .btn {") :]
    block = block[: block.index("}")]
    assert "min-height: 48px" in block
    assert "border-radius: var(--radius-control)" in block


def test_the_or_separator_is_gone():
    """A vertical '또는' between two blocks is what made them read as separate offers."""
    src = _result()
    block = src[src.index('data-testid="rewarded-detail-offer"') :]
    block = block[: block.index("\n                  </div>")]
    assert "또는" not in block


# --- visibility conditions ------------------------------------------------------------------


def test_result_uses_the_hook_condition_rather_than_reassembling_it():
    """One source of truth for 'may we offer an ad', so screen and hook cannot diverge."""
    src = _result()
    assert "rewarded.canOffer" in src
    assert "rewarded.loadState !== 'unavailable' &&" not in src


def test_loading_and_error_keep_the_button_visible():
    src = _result()
    assert "'광고 준비 중…'" in src
    assert "'광고 다시 시도'" in src
    assert "'광고 진행 중…'" in src


def test_failed_preload_retries_the_load_not_the_unlock():
    """`광고 다시 시도` must call retryLoad.

    Wiring it to the unlock path would create a rewarded session — and consume the
    server-side attempt — before any ad had actually loaded.
    """
    src = _result()
    block = src[src.index('<div className="purchase-choice-actions">') :]
    block = block[: block.index("</button>")]
    handler = block[block.index("onClick={") :]
    assert "rewarded.loadState === 'error'" in handler
    assert "rewarded.retryLoad()" in handler
    # The error branch is chosen before the unlock fallback.
    assert handler.index("rewarded.retryLoad()") < handler.index("unlockViaRewardedAd")


def test_ready_state_still_uses_the_unlock_path():
    src = _result()
    block = src[src.index('<div className="purchase-choice-actions">') :]
    block = block[: block.index("</button>")]
    assert "unlockViaRewardedAd" in block


def test_unavailable_and_daily_limit_still_explain_themselves():
    src = _result()
    assert "지금은 광고 무료 열람을 사용할 수 없어요." in src
    assert "오늘 무료 열람 기회를 모두 사용했어요." in src
    assert "오늘 무료 열람" in src  # remaining-count line


def test_reward_grant_conditions_are_untouched():
    """UI only: the claim path still requires the server session + claim endpoint."""
    hook = _read("src/lib/useRewardedDetailUnlock.ts")
    assert "claimRewardedSongDetail" in hook
    assert "can_use_rewarded_ad" in hook
    assert "remaining_today" in hook


def test_diagnostic_cta_is_unchanged():
    src = _result()
    assert DIAGNOSTIC_CTA in src
    assert DETAIL_PURCHASE_CTA in src


def test_detail_report_screen_has_no_purchase_or_ad_cta():
    """/result/:id/detail sells the diagnostic only. The ad never moves here."""
    src = _read("src/pages/SongDetailReport.tsx")
    assert REWARDED_CTA not in src
    assert DETAIL_PURCHASE_CTA not in src
    assert "buySongDetail" not in src
    assert "useRewardedDetailUnlock" not in src
    assert "DiagnosticCTA" in src


def _app_bundle() -> str | None:
    """Only OUR compiled app.

    dist also holds the Apps in Toss RN bundles (`bundle.*.js`) after build:toss, and the
    SDK vendors its own devDependency metadata in there — which literally contains the
    words "vitest" and "jsdom". Those are the SDK's, not ours, so the contamination check
    is scoped to the app assets vite emits.
    """
    assets = [
        p
        for p in sorted(DIST.rglob("*.js")) + sorted(DIST.rglob("*.css"))
        if "assets" in p.parts
    ]
    if not assets:
        return None
    return chr(10).join(p.read_text(encoding="utf-8", errors="ignore") for p in assets)


def test_production_bundle_has_no_test_library_code():
    """RTL is dev-only; a test file reaching the app bundle would drag it in."""
    blob = _app_bundle()
    if blob is None:
        pytest.skip("miniapp not built")
    for marker in ("@testing-library", "expect.extend", "vi.mock"):
        assert marker not in blob, marker


def test_test_sources_are_not_shipped():
    blob = _app_bundle()
    if blob is None:
        pytest.skip("miniapp not built")
    for marker in ("detailOffer.test", "lifecycle.test", "src/test/setup"):
        assert marker not in blob, marker


def test_test_packages_stay_dev_only():
    import json

    pkg = json.loads((MINIAPP / "package.json").read_text(encoding="utf-8"))
    test_pkgs = {
        "vitest",
        "jsdom",
        "@testing-library/react",
        "@testing-library/jest-dom",
        "@testing-library/user-event",
    }
    assert test_pkgs <= set(pkg.get("devDependencies", {}))
    assert not (test_pkgs & set(pkg.get("dependencies", {})))
    assert pkg["scripts"].get("test:ui") == "vitest run"


def test_production_typecheck_excludes_test_files():
    """`tsc -b` in build:web must not compile test files (they use vitest globals)."""
    import json

    ts = json.loads((MINIAPP / "tsconfig.json").read_text(encoding="utf-8"))
    excluded = set(ts.get("exclude", []))
    assert "src/**/*.test.tsx" in excluded
    assert "src/**/*.test.ts" in excluded
    assert "src/test" in excluded


def test_bundle_keeps_both_ctas():
    blob = _bundle()
    if blob is None:
        pytest.skip("miniapp not built")
    assert REWARDED_CTA in blob
    assert DETAIL_PURCHASE_CTA in blob
    assert DIAGNOSTIC_CTA in blob
