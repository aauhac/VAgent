"""Frontend half of the notification deep link.

Console will point the completion alert at `intoss://vocalfb/notification-result`, which
Apps in Toss maps to the miniapp path `/notification-result`. If the route, its redirect,
or the session-clear guard regresses, the alert silently drops the user on Home again.

The miniapp has no JS test runner (no vitest/jest in package.json), so these pin the
source the same way the rest of tests/product does.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MINIAPP = ROOT / "miniapp"

DEEP_LINK_PATH = "/notification-result"
FALLBACK_PATH = "/history"


def _app() -> str:
    return (MINIAPP / "src" / "App.tsx").read_text(encoding="utf-8")


def _page() -> str:
    return (MINIAPP / "src" / "pages" / "NotificationResultRedirect.tsx").read_text(
        encoding="utf-8"
    )


def _client() -> str:
    return (MINIAPP / "src" / "api" / "client.ts").read_text(encoding="utf-8")


def _client_block() -> str:
    src = _client()
    block = src[src.index("export async function getLatestNotificationResult") :]
    return block[: block.index("\n}\n")]


# --- routing -------------------------------------------------------------------------


def test_deep_link_route_is_registered():
    src = _app()
    assert "NotificationResultRedirect" in src
    assert "NOTIFICATION_RESULT_PATH" in src
    assert f"'{DEEP_LINK_PATH}'" in _page()


def test_deep_link_route_is_not_swallowed_by_the_catch_all():
    """The `*` -> Home redirect must stay last, or the deep link never renders."""
    src = _app()
    assert src.index("NOTIFICATION_RESULT_PATH} element=") < src.index('path="*"')


def test_browser_router_keeps_plain_paths():
    """A HashRouter would turn the deep link into /#/notification-result and break it."""
    main = (MINIAPP / "src" / "main.tsx").read_text(encoding="utf-8")
    assert "BrowserRouter" in main
    assert "HashRouter" not in main


# --- redirect behaviour ---------------------------------------------------------------


def test_found_forwards_to_the_notified_result():
    src = _page()
    assert "getLatestNotificationResult" in src
    assert "latest.found && latest.analysis_id" in src
    assert "`/result/${latest.analysis_id}`" in src
    assert "replace: true" in src


def test_not_found_falls_back_to_history_not_home():
    src = _page()
    assert f"const FALLBACK = '{FALLBACK_PATH}'" in src
    assert "let target = FALLBACK" in src
    # A bare Home redirect on this page would defeat the whole deep link.
    assert "nav('/'," not in src


def test_api_failure_falls_back_to_history():
    src = _page()
    body = src[src.index("useEffect(") :]
    assert "catch {" in body
    # The catch leaves `target` at its FALLBACK initial value rather than reassigning Home.
    catch_block = body[body.index("} catch {") :]
    assert "'/'" not in catch_block.split("}")[0]


def test_landing_restores_identity_before_asking():
    """Without the device identity the server cannot match an anonymous recipient."""
    body = _page()
    body = body[body.index("useEffect(") :]
    assert body.index("await getUserIdentity()") < body.index(
        "await getLatestNotificationResult()"
    )


def test_loading_copy_is_present_and_finite():
    src = _page()
    assert "분석 결과를 불러오고 있어요." in src
    # No retry/poll loop — one attempt, then redirect either way.
    assert "setInterval" not in src
    assert "setTimeout" not in src


# --- session-clear race ---------------------------------------------------------------


def test_expired_session_does_not_force_the_deep_link_to_home():
    src = _app()
    cleared = src[src.index("const onCleared") :]
    cleared = cleared[: cleared.index("};")]
    assert "NOTIFICATION_RESULT_PATH" in cleared
    assert "return;" in cleared
    assert cleared.index("NOTIFICATION_RESULT_PATH") < cleared.index("nav('/'")


def test_other_screens_still_go_home_on_session_clear():
    src = _app()
    cleared = src[src.index("const onCleared") :]
    cleared = cleared[: cleared.index("};")]
    assert "nav('/', { replace: true })" in cleared


# --- no Home fallback anywhere on this path ---------------------------------------------


def test_no_home_navigation_in_the_redirect_page():
    """Audited exhaustively: this page may only reach /result/:id or /history."""
    src = _page()
    for forbidden in ("nav('/')", 'nav("/")', "navigate('/')", 'Navigate to="/"'):
        assert forbidden not in src, forbidden
    assert "window.location" not in src
    assert "history.replaceState" not in src


def test_only_two_home_navigations_exist_app_wide():
    """Both are accounted for: the session-clear handler (which excludes this route) and
    the catch-all (which is registered after it). A third would be a regression."""
    app = _app()
    assert app.count("nav('/', { replace: true })") == 1
    assert app.count('<Route path="*" element={<Navigate to="/" replace />} />') == 1


def test_bootstrap_does_not_navigate_on_cold_start():
    """A deep-link cold start must keep its pathname through session bootstrap."""
    app = _app()
    boot = app[app.index("const boot = async () => {") :]
    boot = boot[: boot.index("void boot();")]
    for forbidden in ("nav(", "window.location", "replaceState"):
        assert forbidden not in boot, forbidden


# --- client contract ------------------------------------------------------------------


def test_client_uses_the_specified_endpoint_and_shared_headers():
    block = _client_block()
    assert "/v1/notifications/latest-result" in block
    assert "headers: await headers()" in block


def test_client_returns_not_found_rather_than_throwing():
    block = _client_block()
    assert "if (!res.ok) return { found: false" in block
    assert "found" in block and "analysis_id" in block and "sent_at" in block


def test_client_does_not_trip_session_cleanup_on_this_call():
    """throwIfAuthLost here would fire SESSION_CLEARED and race the redirect."""
    block = _client_block()
    assert "throwIfAuthLost" not in block
