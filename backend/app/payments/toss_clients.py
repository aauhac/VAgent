"""Apps in Toss server APIs over mTLS. Never log tokens, certs, or authorization codes."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from .settings import toss_api_base_url, toss_mtls_cert_path, toss_mtls_key_path

logger = logging.getLogger("vagent.payments.toss")

TOKEN_PATH = "/api-partner/v1/apps-in-toss/user/oauth2/generate-token"
LOGIN_ME_PATH = "/api-partner/v1/apps-in-toss/user/oauth2/login-me"
ORDER_STATUS_PATH = "/api-partner/v1/apps-in-toss/order/get-order-status"


class TossApiError(Exception):
    def __init__(self, code: str, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class TossOrderStatus:
    order_id: str
    sku: str | None
    status: str
    reason: str | None
    result_type: str
    raw: dict[str, Any]


def _mtls_files() -> tuple[str, str]:
    cert = toss_mtls_cert_path()
    key = toss_mtls_key_path()
    if not cert or not key:
        raise TossApiError("MTLS_NOT_CONFIGURED", retryable=False)
    return cert, key


def _client() -> httpx.Client:
    cert, key = _mtls_files()
    return httpx.Client(
        base_url=toss_api_base_url(),
        cert=(cert, key),
        timeout=8.0,
    )


def _require_success_envelope(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise TossApiError("INVALID_TOSS_RESPONSE", retryable=True)
    result_type = str(payload.get("resultType") or "").upper()
    if result_type != "SUCCESS":
        retryable = result_type in {"HTTP_TIMEOUT", "NETWORK_ERROR", "ERROR", "INTERNAL_ERROR"}
        raise TossApiError(result_type or "TOSS_RESULT_FAIL", retryable=retryable)
    success = payload.get("success")
    if not isinstance(success, dict):
        raise TossApiError("INVALID_TOSS_RESPONSE", retryable=True)
    return success


class TossLoginClient:
    """Server-side authorization code exchange + login-me. Tokens never leave this process."""

    def exchange_code(self, authorization_code: str, referrer: str) -> dict[str, Any]:
        with _client() as client:
            response = client.post(
                TOKEN_PATH,
                json={
                    "authorizationCode": authorization_code,
                    "referrer": referrer,
                },
            )
        if response.status_code >= 500:
            raise TossApiError("TOSS_LOGIN_UNAVAILABLE", retryable=True)
        payload = response.json()
        if isinstance(payload, dict) and payload.get("error") == "invalid_grant":
            raise TossApiError("INVALID_GRANT", retryable=False)
        return _require_success_envelope(payload)

    def login_me(self, access_token: str) -> dict[str, Any]:
        with _client() as client:
            response = client.get(
                LOGIN_ME_PATH,
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if response.status_code >= 500:
            raise TossApiError("TOSS_LOGIN_UNAVAILABLE", retryable=True)
        payload = response.json()
        return _require_success_envelope(payload)


class TossIapClient:
    def get_order_status(self, order_id: str, *, toss_user_key: str | None = None) -> TossOrderStatus:
        headers = {}
        if toss_user_key:
            headers["x-toss-user-key"] = str(toss_user_key)
        with _client() as client:
            response = client.post(
                ORDER_STATUS_PATH,
                json={"orderId": order_id},
                headers=headers,
            )
        if response.status_code >= 500:
            raise TossApiError("TOSS_ORDER_UNAVAILABLE", retryable=True)
        payload = response.json() if response.content else {}
        if not isinstance(payload, dict):
            raise TossApiError("INVALID_TOSS_RESPONSE", retryable=True)
        result_type = str(payload.get("resultType") or "").upper()
        if result_type != "SUCCESS":
            retryable = result_type in {"HTTP_TIMEOUT", "NETWORK_ERROR", "ERROR", "INTERNAL_ERROR"}
            raise TossApiError(result_type or "TOSS_RESULT_FAIL", retryable=retryable)
        success = payload.get("success") if isinstance(payload.get("success"), dict) else {}
        status = str(success.get("status") or "").upper()
        return TossOrderStatus(
            order_id=str(success.get("orderId") or order_id),
            sku=str(success["sku"]) if success.get("sku") else None,
            status=status,
            reason=str(success.get("reason")) if success.get("reason") else None,
            result_type=result_type,
            raw=payload,
        )


SEND_MESSAGE_PATH = "/api-partner/v1/apps-in-toss/messenger/send-message"


class TossMessengerClient:
    def send_message(
        self,
        *,
        template_set_code: str,
        headers: dict[str, str],
        context: dict[str, str] | None = None,
    ) -> str:
        """Send one Smart Message.

        `context` carries the template/URL variables for THIS send. Callers pass only
        non-sensitive identifiers — never a userKey, anonymous hash, token, or order id.
        deploymentId stays out of live send-message; it is a send-test-message parameter.
        """
        anon = (headers.get("x-anon-key") or "").strip()
        user = (headers.get("x-toss-user-key") or "").strip()
        if bool(anon) == bool(user):
            raise TossApiError("INVALID_RECIPIENT", retryable=False)
        if anon and user:
            raise TossApiError("INVALID_RECIPIENT", retryable=False)
        with _client() as client:
            response = client.post(
                SEND_MESSAGE_PATH,
                json={
                    "templateSetCode": template_set_code,
                    "context": dict(context or {}),
                },
                headers=headers,
            )
        payload = response.json() if response.content else {}
        if not isinstance(payload, dict):
            raise TossApiError("INVALID_TOSS_RESPONSE", retryable=True)
        result_type = str(payload.get("resultType") or "").upper()
        if result_type != "SUCCESS":
            retryable = result_type in {"HTTP_TIMEOUT", "NETWORK_ERROR", "ERROR", "INTERNAL_ERROR"}
            raise TossApiError(result_type or "TOSS_RESULT_FAIL", retryable=retryable)
        return result_type


_login_client: Optional[TossLoginClient] = None
_iap_client: Optional[TossIapClient] = None
_messenger_client: Optional[TossMessengerClient] = None


def get_login_client() -> TossLoginClient:
    global _login_client
    if _login_client is None:
        _login_client = TossLoginClient()
    return _login_client


def get_iap_client() -> TossIapClient:
    global _iap_client
    if _iap_client is None:
        _iap_client = TossIapClient()
    return _iap_client


def set_login_client(client: TossLoginClient | None) -> None:
    global _login_client
    _login_client = client


def set_iap_client(client: TossIapClient | None) -> None:
    global _iap_client
    _iap_client = client


def get_messenger_client() -> TossMessengerClient:
    global _messenger_client
    if _messenger_client is None:
        _messenger_client = TossMessengerClient()
    return _messenger_client


def set_messenger_client(client: TossMessengerClient | None) -> None:
    global _messenger_client
    _messenger_client = client
