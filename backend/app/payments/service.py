"""Payment intent / grant / recover / refund — DB transaction after external Toss verify."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Analysis, Entitlement, PaymentIntent, PurchaseOrder, User
from ..db.purchases import (
    PaymentOrderBindingMismatch,
    grant_from_purchase,
    revoke_from_refund,
)
from ..db.users import get_or_create_user
from ..entitlements.provider import (
    ENTITLEMENT_DIAGNOSTIC,
    ENTITLEMENT_SONG_DETAIL,
    RESOURCE_ANALYSIS,
    RESOURCE_DIAGNOSTIC_SESSION,
)
from ..products.catalog import (
    PRODUCT_DIAGNOSTIC_FULL,
    PRODUCT_DIAGNOSTIC_UPGRADE,
    PRODUCT_SONG_DETAIL,
)
from .errors import PaymentError
from .settings import (
    DENY_ORDER_STATUSES,
    GRANTABLE_ORDER_STATUSES,
    INTENT_TTL_SECONDS,
    payments_enabled,
    production_skus,
)
from .toss_clients import TossApiError, TossOrderStatus, get_iap_client

logger = logging.getLogger("vagent.payments")

PROVIDER_TOSS = "TOSS"

PAYMENTS_DISABLED_MESSAGE = "현재 결제를 이용할 수 없어요."


def require_payments_enabled() -> None:
    if not payments_enabled():
        raise PaymentError("PAYMENTS_DISABLED", PAYMENTS_DISABLED_MESSAGE, 503)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _sku_for_product(product_id: str) -> str:
    skus = production_skus()
    sku = skus.get(product_id)
    if not sku:
        raise PaymentError("UNKNOWN_PRODUCT", "결제를 시작하지 못했어요. 잠시 후 다시 시도해주세요.", 400)
    return sku


def _entitlement_for_product(product_id: str) -> tuple[str, str]:
    if product_id == PRODUCT_SONG_DETAIL:
        return RESOURCE_ANALYSIS, ENTITLEMENT_SONG_DETAIL
    if product_id in (PRODUCT_DIAGNOSTIC_FULL, PRODUCT_DIAGNOSTIC_UPGRADE):
        return RESOURCE_DIAGNOSTIC_SESSION, ENTITLEMENT_DIAGNOSTIC
    raise PaymentError("UNKNOWN_PRODUCT", "결제를 시작하지 못했어요. 잠시 후 다시 시도해주세요.", 400)


def resolve_toss_user(session: Session, toss_user_key: str) -> User:
    return get_or_create_user(session, provider=PROVIDER_TOSS, subject=str(toss_user_key))


def _analysis_owned(session: Session, user: User, analysis_id: str) -> Analysis:
    row = session.get(Analysis, analysis_id)
    if row is None or row.deleted_at is not None or row.user_id != user.id:
        raise PaymentError("RESOURCE_NOT_FOUND", "분석 기록을 찾을 수 없어요.", 404)
    return row


def _has_active(
    session: Session,
    user_id: uuid.UUID,
    resource_type: str,
    resource_id: str,
    entitlement_type: str,
) -> bool:
    row = session.scalar(
        select(Entitlement).where(
            Entitlement.user_id == user_id,
            Entitlement.resource_type == resource_type,
            Entitlement.resource_id == resource_id,
            Entitlement.entitlement_type == entitlement_type,
            Entitlement.status == "ACTIVE",
        )
    )
    return row is not None


def create_intent(
    session: Session,
    *,
    toss_user_key: str,
    product_id: str,
    analysis_id: str | None,
    session_id: str | None,
) -> PaymentIntent:
    require_payments_enabled()
    user = resolve_toss_user(session, toss_user_key)
    now = _utcnow()
    sku = _sku_for_product(product_id)

    if product_id == PRODUCT_SONG_DETAIL:
        if not analysis_id:
            raise PaymentError("RESOURCE_REQUIRED", "결제를 시작하지 못했어요. 잠시 후 다시 시도해주세요.", 400)
        _analysis_owned(session, user, analysis_id)
        if _has_active(session, user.id, RESOURCE_ANALYSIS, analysis_id, ENTITLEMENT_SONG_DETAIL):
            raise PaymentError("ALREADY_PURCHASED", "이미 이용할 수 있는 리포트예요.", 409)
        resource_type, resource_id = RESOURCE_ANALYSIS, analysis_id
    elif product_id in (PRODUCT_DIAGNOSTIC_FULL, PRODUCT_DIAGNOSTIC_UPGRADE):
        if not analysis_id:
            raise PaymentError("RESOURCE_REQUIRED", "결제를 시작하지 못했어요. 잠시 후 다시 시도해주세요.", 400)
        _analysis_owned(session, user, analysis_id)
        detail_owned = _has_active(
            session, user.id, RESOURCE_ANALYSIS, analysis_id, ENTITLEMENT_SONG_DETAIL
        )
        if product_id == PRODUCT_DIAGNOSTIC_UPGRADE and not detail_owned:
            raise PaymentError(
                "DETAIL_REQUIRED",
                "결제를 시작하지 못했어요. 잠시 후 다시 시도해주세요.",
                409,
            )
        if product_id == PRODUCT_DIAGNOSTIC_FULL and detail_owned:
            raise PaymentError(
                "UPGRADE_REQUIRED",
                "이미 상세 리포트를 이용 중이에요.",
                409,
            )
        resource_type, resource_id = RESOURCE_ANALYSIS, analysis_id
    else:
        raise PaymentError("UNKNOWN_PRODUCT", "결제를 시작하지 못했어요. 잠시 후 다시 시도해주세요.", 400)

    existing_rows = session.scalars(
        select(PaymentIntent).where(
            PaymentIntent.user_id == user.id,
            PaymentIntent.product_id == product_id,
            PaymentIntent.resource_type == resource_type,
            PaymentIntent.resource_id == resource_id,
            PaymentIntent.status == "PENDING",
        )
    ).all()
    existing = [row for row in existing_rows if _as_utc(row.expires_at) > now]
    if existing:
        return {
            "id": str(existing[0].id),
            "product_id": existing[0].product_id,
            "sku": existing[0].sku,
            "resource_type": existing[0].resource_type,
            "resource_id": existing[0].resource_id,
            "status": existing[0].status,
        }

    intent = PaymentIntent(
        user_id=user.id,
        product_id=product_id,
        sku=sku,
        resource_type=resource_type,
        resource_id=resource_id,
        status="PENDING",
        expires_at=now + timedelta(seconds=INTENT_TTL_SECONDS),
    )
    session.add(intent)
    session.flush()
    return {
        "id": str(intent.id),
        "product_id": intent.product_id,
        "sku": intent.sku,
        "resource_type": intent.resource_type,
        "resource_id": intent.resource_id,
        "status": intent.status,
    }


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _expire_if_needed(intent: PaymentIntent) -> None:
    if intent.status == "PENDING" and _as_utc(intent.expires_at) <= _utcnow():
        intent.status = "EXPIRED"


def _verify_order(
    *,
    order_id: str,
    toss_user_key: str,
    expected_sku: str,
) -> TossOrderStatus:
    client = get_iap_client()
    try:
        status = client.get_order_status(order_id, toss_user_key=toss_user_key)
    except TossApiError as exc:
        if exc.retryable:
            raise PaymentError(
                "PAYMENT_PENDING",
                "결제 상태를 확인하고 있어요. 다시 앱을 열어도 이어서 확인할 수 있어요.",
                503,
            ) from exc
        raise PaymentError(
            "PAYMENT_VERIFY_FAILED",
            "결제를 확인하지 못했어요. 잠시 후 다시 시도해주세요.",
            502,
        ) from exc
    if status.result_type != "SUCCESS":
        raise PaymentError(
            "PAYMENT_VERIFY_FAILED",
            "결제를 확인하지 못했어요. 잠시 후 다시 시도해주세요.",
            502,
        )
    if status.status == "ERROR":
        raise PaymentError(
            "PAYMENT_PENDING",
            "결제 상태를 확인하고 있어요. 다시 앱을 열어도 이어서 확인할 수 있어요.",
            503,
        )
    if status.status == "REFUNDED":
        raise PaymentError("PAYMENT_REFUNDED", "환불된 구매라 현재 이용할 수 없어요.", 409)
    if status.status == "MINIAPP_MISMATCH":
        logger.warning("iap_miniapp_mismatch order=%s", _mask_order(order_id))
        raise PaymentError("PAYMENT_VERIFY_FAILED", "결제를 확인하지 못했어요. 잠시 후 다시 시도해주세요.", 403)
    if status.status not in GRANTABLE_ORDER_STATUSES:
        raise PaymentError(
            "PAYMENT_NOT_GRANTABLE",
            "아직 결제를 완료하지 않았어요.",
            409,
        )
    if not status.sku or status.sku != expected_sku:
        raise PaymentError("SKU_MISMATCH", "결제를 확인하지 못했어요. 잠시 후 다시 시도해주세요.", 409)
    if status.order_id and status.order_id != order_id:
        raise PaymentError("ORDER_MISMATCH", "결제를 확인하지 못했어요. 잠시 후 다시 시도해주세요.", 409)
    return status


def _mask_order(order_id: str) -> str:
    s = order_id or ""
    if len(s) <= 8:
        return "***"
    return f"{s[:4]}…{s[-4:]}"


def _mask_user(key: str) -> str:
    s = key or ""
    if len(s) <= 4:
        return "***"
    return f"{s[:2]}…{s[-2:]}"


def peek_intent_sku(session: Session, *, toss_user_key: str, intent_id: str) -> str:
    user = resolve_toss_user(session, toss_user_key)
    try:
        iid = uuid.UUID(str(intent_id))
    except ValueError as exc:
        raise PaymentError("INTENT_NOT_FOUND", "결제를 시작하지 못했어요. 잠시 후 다시 시도해주세요.", 404) from exc
    intent = session.get(PaymentIntent, iid)
    if intent is None or intent.user_id != user.id:
        raise PaymentError("INTENT_NOT_FOUND", "결제를 시작하지 못했어요. 잠시 후 다시 시도해주세요.", 404)
    _expire_if_needed(intent)
    if intent.status == "EXPIRED":
        raise PaymentError("INTENT_EXPIRED", "결제를 시작하지 못했어요. 잠시 후 다시 시도해주세요.", 409)
    return intent.sku


def verify_order_for_grant(*, order_id: str, toss_user_key: str, expected_sku: str) -> TossOrderStatus:
    return _verify_order(order_id=order_id, toss_user_key=toss_user_key, expected_sku=expected_sku)


def grant_for_intent(
    session: Session,
    *,
    toss_user_key: str,
    intent_id: str,
    order_id: str,
    order_status: TossOrderStatus | None = None,
) -> dict[str, Any]:
    require_payments_enabled()
    user = resolve_toss_user(session, toss_user_key)
    try:
        iid = uuid.UUID(str(intent_id))
    except ValueError as exc:
        raise PaymentError("INTENT_NOT_FOUND", "결제를 시작하지 못했어요. 잠시 후 다시 시도해주세요.", 404) from exc
    intent = session.get(PaymentIntent, iid)
    if intent is None or intent.user_id != user.id:
        raise PaymentError("INTENT_NOT_FOUND", "결제를 시작하지 못했어요. 잠시 후 다시 시도해주세요.", 404)
    _expire_if_needed(intent)
    if intent.status == "EXPIRED":
        raise PaymentError("INTENT_EXPIRED", "결제를 시작하지 못했어요. 잠시 후 다시 시도해주세요.", 409)
    if intent.status not in ("PENDING", "COMPLETED"):
        raise PaymentError("INTENT_INVALID", "결제를 시작하지 못했어요. 잠시 후 다시 시도해주세요.", 409)

    if order_status is None:
        order_status = _verify_order(
            order_id=order_id,
            toss_user_key=toss_user_key,
            expected_sku=intent.sku,
        )

    resource_id = intent.resource_id
    try:
        order, ent, _created = grant_from_purchase(
            session,
            user_id=user.id,
            toss_order_id=order_id,
            product_id=intent.product_id,
            resource_type=RESOURCE_ANALYSIS,
            resource_id=resource_id,
            entitlement_type=ENTITLEMENT_SONG_DETAIL
            if intent.product_id == PRODUCT_SONG_DETAIL
            else ENTITLEMENT_SONG_DETAIL,
            sku=intent.sku,
            provider=PROVIDER_TOSS,
            provider_status=order_status.status,
        )
        if intent.product_id in (PRODUCT_DIAGNOSTIC_FULL, PRODUCT_DIAGNOSTIC_UPGRADE):
            _, ent, _ = grant_from_purchase(
                session,
                user_id=user.id,
                toss_order_id=order_id,
                product_id=intent.product_id,
                resource_type=RESOURCE_ANALYSIS,
                resource_id=resource_id,
                entitlement_type=ENTITLEMENT_DIAGNOSTIC,
                sku=intent.sku,
                provider=PROVIDER_TOSS,
                provider_status=order_status.status,
            )
    except PaymentOrderBindingMismatch as exc:
        logger.warning(
            "iap_order_binding_mismatch user=%s order=%s intent=%s",
            _mask_user(toss_user_key),
            _mask_order(order_id),
            intent.id,
        )
        raise PaymentError(
            "PAYMENT_ORDER_BINDING_MISMATCH",
            "이 결제는 다른 계정이나 분석에 연결되어 있어요.",
            409,
        ) from exc

    intent.status = "COMPLETED"
    intent.toss_order_id = order_id
    intent.updated_at = _utcnow()
    logger.info(
        "iap_grant_ok user=%s product=%s order=%s intent=%s status=%s",
        _mask_user(toss_user_key),
        intent.product_id,
        _mask_order(order_id),
        str(intent.id),
        order_status.status,
    )
    return {
        "granted": True,
        "intent_id": str(intent.id),
        "order_id": order_id,
        "product_id": intent.product_id,
        "resource_type": intent.resource_type,
        "resource_id": intent.resource_id,
        "complete_product_grant": True,
    }


def recover_pending_order(
    session: Session,
    *,
    toss_user_key: str,
    order_id: str,
    sku: str | None = None,
) -> dict[str, Any]:
    require_payments_enabled()
    user = resolve_toss_user(session, toss_user_key)
    now = _utcnow()
    # Prefer already-bound intent
    bound = session.scalar(
        select(PaymentIntent).where(
            PaymentIntent.user_id == user.id,
            PaymentIntent.toss_order_id == order_id,
        )
    )
    if bound is not None:
        return grant_for_intent(
            session,
            toss_user_key=toss_user_key,
            intent_id=str(bound.id),
            order_id=order_id,
        )

    q = select(PaymentIntent).where(
        PaymentIntent.user_id == user.id,
        PaymentIntent.status == "PENDING",
    )
    if sku:
        q = q.where(PaymentIntent.sku == sku)
    candidates = [row for row in session.scalars(q).all() if _as_utc(row.expires_at) > now]
    if len(candidates) == 0:
        raise PaymentError(
            "NEEDS_MANUAL_RESTORE",
            "결제 상태를 확인하고 있어요. 다시 앱을 열어도 이어서 확인할 수 있어요.",
            409,
        )
    if len(candidates) > 1:
        raise PaymentError(
            "AMBIGUOUS_PENDING_PURCHASE",
            "복구할 구매를 특정하지 못했어요. 잠시 후 다시 시도해주세요.",
            409,
        )
    intent = candidates[0]
    return grant_for_intent(
        session,
        toss_user_key=toss_user_key,
        intent_id=str(intent.id),
        order_id=order_id,
    )


def reconcile_refund(
    session: Session,
    *,
    toss_user_key: str,
    order_id: str,
) -> dict[str, Any]:
    require_payments_enabled()
    user = resolve_toss_user(session, toss_user_key)
    status = _verify_order_for_refund(order_id, toss_user_key)
    if status.status != "REFUNDED":
        raise PaymentError("NOT_REFUNDED", "환불된 구매가 아니에요.", 409)
    order = revoke_from_refund(session, toss_order_id=order_id, provider=PROVIDER_TOSS)
    if order is None:
        raise PaymentError("ORDER_NOT_FOUND", "결제 기록을 찾을 수 없어요.", 404)
    if order.user_id != user.id:
        raise PaymentError("PAYMENT_ORDER_BINDING_MISMATCH", "이 결제는 다른 계정이나 분석에 연결되어 있어요.", 409)
    return {"refunded": True, "order_id": order_id, "revoked": True}


def _verify_order_for_refund(order_id: str, toss_user_key: str) -> TossOrderStatus:
    client = get_iap_client()
    try:
        status = client.get_order_status(order_id, toss_user_key=toss_user_key)
    except TossApiError as exc:
        raise PaymentError(
            "PAYMENT_VERIFY_FAILED",
            "결제를 확인하지 못했어요. 잠시 후 다시 시도해주세요.",
            502,
        ) from exc
    if status.result_type != "SUCCESS":
        raise PaymentError(
            "PAYMENT_VERIFY_FAILED",
            "결제를 확인하지 못했어요. 잠시 후 다시 시도해주세요.",
            502,
        )
    return status
