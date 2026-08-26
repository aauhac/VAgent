"""Frontend half of the anonymous-ownership payment fix, plus safe stage logging.

The backend can only adopt a device's free analyses if the login request actually carries
the pre-login anonymous identifier, so that header is a regression guard, not a detail.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MINIAPP = ROOT / "miniapp"

FORBIDDEN_LOG_TOKENS = (
    "authorization_code",
    "authorizationCode",
    "accessToken",
    "access_token",
    "refreshToken",
    "refresh_token",
    "session_token",
    "sessionToken",
    "userKey",
    "user_key",
)


def _client_src() -> str:
    return (MINIAPP / "src" / "api" / "client.ts").read_text(encoding="utf-8")


def _iap_src() -> str:
    return (MINIAPP / "src" / "lib" / "tossIap.ts").read_text(encoding="utf-8")


def test_login_exchange_sends_anonymous_identity_headers():
    src = _client_src()
    block = src[src.index("export async function exchangeTossLogin") :]
    block = block[: block.index("\n}\n")]
    assert "ensureIdentityHeaders" in block
    assert "'Content-Type': 'application/json'" in block
    # Identity resolution must never be able to block a login that would otherwise work.
    assert "try {" in block and "catch {" in block


def test_login_exchange_still_posts_only_code_and_referrer():
    """Identity travels in the header; the body must not gain an identity field."""
    src = _client_src()
    block = src[src.index("export async function exchangeTossLogin") :]
    block = block[: block.index("\n}\n")]
    body = block[block.index("body: JSON.stringify(") :]
    assert "authorization_code" in body
    assert "referrer" in body
    assert "X-VAgent-User-Key" not in body
    assert "user_key" not in body


def test_iap_logs_each_purchase_stage():
    src = _iap_src()
    for stage in (
        "login_start",
        "login_ok",
        "login_failed",
        "intent_start",
        "intent_ok",
        "intent_failed",
        "order_start",
        "order_failed",
        "grant_start",
        "grant_ok",
        "grant_failed",
    ):
        assert f"'{stage}'" in src, stage


def test_iap_stage_logging_never_carries_secrets():
    src = _iap_src()
    log_lines = [line for line in src.splitlines() if "iapLog(" in line]
    assert log_lines
    for line in log_lines:
        for token in FORBIDDEN_LOG_TOKENS:
            assert token not in line, f"{token} in {line.strip()}"


def test_user_facing_purchase_copy_is_unchanged():
    """Observability is dev-console only — the shown message stays generic."""
    src = _iap_src()
    assert "결제를 시작하지 못했어요. 잠시 후 다시 시도해주세요." in src
    assert "결제가 취소됐어요." in src


def _strip_line_comments(text: str) -> str:
    """Drop // comments so a call and a mention of that call are not confused."""
    kept = [
        line for line in text.splitlines() if not line.lstrip().startswith(("//", "*", "/*"))
    ]
    return chr(10).join(kept)


def _purchase_callback() -> str:
    src = _iap_src()
    start = src.index("processProductGrant: async")
    end = src.index(chr(10) + "          },", start)
    return src[start:end]


def _recovery_body() -> str:
    src = _iap_src()
    return src[src.index("export async function recoverPendingPurchases") :]


def test_initial_purchase_has_no_direct_complete_product_grant():
    """Returning true is the callback's completion signal; calling it too duplicates it."""
    body = _strip_line_comments(_purchase_callback())
    assert "completeProductGrant" not in body


def test_grant_success_returns_true():
    body = _purchase_callback()
    assert "grantIapOrder(" in body
    granted_branch = body[body.index("iapLog('grant_ok')") :]
    assert "return true;" in granted_branch


def test_grant_failure_returns_false():
    """Backend refusal and a thrown grant call must both answer the SDK with false."""
    body = _purchase_callback()
    assert "if (!grant?.granted)" in body

    # Refusal branch: false is the next statement after the log, not somewhere later.
    denied = body[body.index("iapLog('grant_denied')") :]
    assert denied.split(";")[1].strip() == "return false"

    # Throw branch: the catch's last statement, ignoring closing braces.
    failed = body[body.index("iapLog('grant_failed'") :]
    statements = [
        line.strip() for line in failed.splitlines() if line.strip() not in ("", "}", "};")
    ]
    assert statements[-1] == "return false;"


def test_recovery_path_still_completes_product_grant():
    """Official pending-order recovery flow — must never be removed."""
    body = _recovery_body()
    assert "getPendingOrders" in body
    assert "recoverIapOrder" in body
    assert "IAP.completeProductGrant({ params: { orderId } })" in body


def test_one_time_purchase_order_matches_sdk_contract():
    """options.sku + options.processProductGrant + onEvent + onError + cleanup return."""
    src = _iap_src()
    assert "IAP.createOneTimePurchaseOrder({" in src
    assert "sku: intent.sku" in src
    assert "processProductGrant: async ({ orderId }" in src
    assert "onEvent:" in src
    assert "onError:" in src
    # The cleanup return value is captured and invoked exactly once. It is assigned to a
    # `let` declared above the callbacks so a synchronous onError/onEvent cannot hit the
    # temporal dead zone of a const and lose the unsubscribe.
    assert "let cleanup: (() => void) | undefined;" in src
    assert "cleanup = IAP.createOneTimePurchaseOrder" in src
    assert "const cleanupOnce = () => {" in src
