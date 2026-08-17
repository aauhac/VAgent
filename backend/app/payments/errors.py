"""Payment / auth errors — user-facing messages never include Toss enums."""

from __future__ import annotations

from fastapi import HTTPException


class PaymentError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.message = message
        self.status_code = status_code

    def as_http(self) -> HTTPException:
        return HTTPException(
            status_code=self.status_code,
            detail={"error": {"code": self.code, "message": self.message}},
        )


def http_payment_error(code: str, message: str, status_code: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error": {"code": code, "message": message}},
    )


USER_MESSAGES = {
    "PAYMENT_PREPARE_FAILED": "결제를 시작하지 못했어요. 잠시 후 다시 시도해주세요.",
    "PAYMENT_CANCELLED": "결제가 취소됐어요.",
    "PAYMENT_PENDING": "결제 상태를 확인하고 있어요. 다시 앱을 열어도 이어서 확인할 수 있어요.",
    "ALREADY_PURCHASED": "이미 이용할 수 있는 리포트예요.",
    "PAYMENT_REFUNDED": "환불된 구매라 현재 이용할 수 없어요.",
    "PAYMENT_UNAVAILABLE": "토스 앱에서 결제를 진행할 수 있어요.",
    "AUTH_REQUIRED": "로그인이 필요해요.",
    "PAYMENT_ORDER_BINDING_MISMATCH": "이 결제는 다른 계정이나 분석에 연결되어 있어요.",
    "AMBIGUOUS_PENDING_PURCHASE": "복구할 구매를 특정하지 못했어요. 잠시 후 다시 시도해주세요.",
    "NEEDS_MANUAL_RESTORE": "결제 상태를 확인하고 있어요. 다시 앱을 열어도 이어서 확인할 수 있어요.",
}
