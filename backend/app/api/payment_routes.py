"""IAP intent / grant / recover / refund. Frontend cannot choose entitlement type."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from ..db.session import session_scope
from ..identity import ResolvedIdentity, require_authenticated_user
from ..payments import rate_limit
from ..payments.errors import PaymentError, http_payment_error
from ..payments.service import (
    create_intent,
    grant_for_intent,
    peek_intent_sku,
    reconcile_refund,
    recover_pending_order,
    require_payments_enabled,
    verify_order_for_grant,
)
from ..payments.settings import INTENT_TTL_SECONDS

router = APIRouter(prefix="/v1/payments/iap", tags=["payments"])


class IntentBody(BaseModel):
    product_id: str = Field(min_length=3, max_length=64)
    analysis_id: str | None = Field(default=None, max_length=64)
    session_id: str | None = Field(default=None, max_length=64)


class GrantBody(BaseModel):
    intent_id: str = Field(min_length=8, max_length=64)
    order_id: str = Field(min_length=8, max_length=128)


class RecoverBody(BaseModel):
    order_id: str = Field(min_length=8, max_length=128)
    sku: str | None = Field(default=None, max_length=128)


class RefundBody(BaseModel):
    order_id: str = Field(min_length=8, max_length=128)


def _rate(request: Request, ident: ResolvedIdentity, bucket: str) -> None:
    uid = ident.toss_user_key or ident.subject
    ip = request.client.host if request.client else "unknown"
    if not rate_limit.allow(f"{bucket}:u:{uid}", max_hits=20):
        raise http_payment_error("RATE_LIMITED", "잠시 후 다시 시도해주세요.", 429)
    if not rate_limit.allow(f"{bucket}:ip:{ip}", max_hits=60):
        raise http_payment_error("RATE_LIMITED", "잠시 후 다시 시도해주세요.", 429)


def _run(fn):
    try:
        with session_scope() as session:
            return fn(session)
    except PaymentError as exc:
        raise exc.as_http() from exc


@router.post("/intents")
def create_payment_intent(
    body: IntentBody,
    request: Request,
    ident: ResolvedIdentity = Depends(require_authenticated_user),
) -> dict:
    try:
        require_payments_enabled()
    except PaymentError as exc:
        raise exc.as_http() from exc
    _rate(request, ident, "intent")
    intent = _run(
        lambda s: create_intent(
            s,
            toss_user_key=ident.toss_user_key or ident.subject,
            product_id=body.product_id,
            analysis_id=body.analysis_id,
            session_id=body.session_id,
        )
    )
    return {
        "intent_id": intent["id"],
        "product_id": intent["product_id"],
        "sku": intent["sku"],
        "resource_type": intent["resource_type"],
        "resource_id": intent["resource_id"],
        "expires_in": INTENT_TTL_SECONDS,
        "status": intent["status"],
    }


@router.post("/grant")
def grant_iap(
    body: GrantBody,
    request: Request,
    ident: ResolvedIdentity = Depends(require_authenticated_user),
) -> dict:
    try:
        require_payments_enabled()
    except PaymentError as exc:
        raise exc.as_http() from exc
    _rate(request, ident, "grant")
    key = ident.toss_user_key or ident.subject
    try:
        sku = _run(lambda s: peek_intent_sku(s, toss_user_key=key, intent_id=body.intent_id))
        order_status = verify_order_for_grant(
            order_id=body.order_id,
            toss_user_key=key,
            expected_sku=sku,
        )
        return _run(
            lambda s: grant_for_intent(
                s,
                toss_user_key=key,
                intent_id=body.intent_id,
                order_id=body.order_id,
                order_status=order_status,
            )
        )
    except PaymentError as exc:
        raise exc.as_http() from exc


@router.post("/recover")
def recover_iap(
    body: RecoverBody,
    request: Request,
    ident: ResolvedIdentity = Depends(require_authenticated_user),
) -> dict:
    try:
        require_payments_enabled()
    except PaymentError as exc:
        raise exc.as_http() from exc
    _rate(request, ident, "recover")
    return _run(
        lambda s: recover_pending_order(
            s,
            toss_user_key=ident.toss_user_key or ident.subject,
            order_id=body.order_id,
            sku=body.sku,
        )
    )


@router.post("/refund")
def refund_iap(
    body: RefundBody,
    request: Request,
    ident: ResolvedIdentity = Depends(require_authenticated_user),
) -> dict:
    try:
        require_payments_enabled()
    except PaymentError as exc:
        raise exc.as_http() from exc
    _rate(request, ident, "refund")
    return _run(
        lambda s: reconcile_refund(
            s,
            toss_user_key=ident.toss_user_key or ident.subject,
            order_id=body.order_id,
        )
    )
