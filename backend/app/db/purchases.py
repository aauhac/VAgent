"""Idempotent purchase → entitlement grants with strict order binding."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import Entitlement, PurchaseOrder


class PaymentOrderBindingMismatch(Exception):
    """Same provider order id is already bound to a different user/product/sku/resource."""

    code = "PAYMENT_ORDER_BINDING_MISMATCH"


def _norm(value: str | None) -> str:
    return (value or "").strip()


def order_bindings_match(
    order: PurchaseOrder,
    *,
    user_id: uuid.UUID,
    product_id: str,
    sku: str | None,
    resource_type: str,
    resource_id: str,
) -> bool:
    return (
        order.user_id == user_id
        and _norm(order.product_id) == _norm(product_id)
        and _norm(order.sku) == _norm(sku)
        and _norm(order.resource_type) == _norm(resource_type)
        and _norm(order.resource_id) == _norm(resource_id)
    )


def _lookup_order(session: Session, toss_order_id: str, provider: str) -> PurchaseOrder | None:
    order = session.scalar(select(PurchaseOrder).where(PurchaseOrder.toss_order_id == toss_order_id))
    if order is not None:
        return order
    return session.scalar(
        select(PurchaseOrder).where(
            PurchaseOrder.provider == provider,
            PurchaseOrder.provider_order_id == toss_order_id,
        )
    )


def grant_from_purchase(
    session: Session,
    *,
    user_id: uuid.UUID,
    toss_order_id: str,
    product_id: str,
    resource_type: str,
    resource_id: str,
    entitlement_type: str,
    sku: str | None = None,
    provider: str = "TOSS",
    provider_status: str | None = None,
) -> tuple[PurchaseOrder, Entitlement, bool]:
    """
    Returns (order, entitlement, created_new_entitlement).

    Same provider order id is idempotent ONLY when user/product/sku/resource match.
    Any mismatch raises PaymentOrderBindingMismatch — never grants a new entitlement.
    """
    now = datetime.now(timezone.utc)
    order_id = str(toss_order_id).strip()
    if not order_id:
        raise ValueError("order_id required")

    order = _lookup_order(session, order_id, provider)
    if order is None:
        order = PurchaseOrder(
            user_id=user_id,
            toss_order_id=order_id,
            provider=provider,
            provider_order_id=order_id,
            sku=sku,
            product_id=product_id,
            resource_type=resource_type,
            resource_id=resource_id,
            provider_status=provider_status or "PURCHASED",
            status="GRANTED",
            status_determined_at=now,
            granted_at=now,
            verified_at=now,
        )
        session.add(order)
        try:
            with session.begin_nested():
                session.flush()
        except IntegrityError:
            order = _lookup_order(session, order_id, provider)
            if order is None:
                raise
            if not order_bindings_match(
                order,
                user_id=user_id,
                product_id=product_id,
                sku=sku,
                resource_type=resource_type,
                resource_id=resource_id,
            ):
                raise PaymentOrderBindingMismatch(order_id) from None
    else:
        if not order_bindings_match(
            order,
            user_id=user_id,
            product_id=product_id,
            sku=sku,
            resource_type=resource_type,
            resource_id=resource_id,
        ):
            raise PaymentOrderBindingMismatch(order_id)
        if order.status == "REFUNDED" or order.refunded_at is not None:
            raise PaymentOrderBindingMismatch(order_id)

    existing = session.scalar(
        select(Entitlement).where(
            Entitlement.user_id == user_id,
            Entitlement.resource_type == resource_type,
            Entitlement.resource_id == resource_id,
            Entitlement.entitlement_type == entitlement_type,
        )
    )
    if existing:
        if existing.status == "REVOKED":
            existing.status = "ACTIVE"
            existing.revoked_at = None
            existing.purchase_order_id = order.id
            existing.granted_at = existing.granted_at or now
            session.flush()
        return order, existing, False

    ent = Entitlement(
        user_id=user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        entitlement_type=entitlement_type,
        product_id=product_id,
        purchase_order_id=order.id,
        status="ACTIVE",
        granted_at=now,
    )
    session.add(ent)
    try:
        with session.begin_nested():
            session.flush()
    except IntegrityError:
        existing = session.scalar(
            select(Entitlement).where(
                Entitlement.user_id == user_id,
                Entitlement.resource_type == resource_type,
                Entitlement.resource_id == resource_id,
                Entitlement.entitlement_type == entitlement_type,
            )
        )
        if existing is None:
            raise
        return order, existing, False
    return order, ent, True


def revoke_from_refund(
    session: Session,
    *,
    toss_order_id: str,
    provider: str = "TOSS",
) -> PurchaseOrder | None:
    now = datetime.now(timezone.utc)
    order = _lookup_order(session, str(toss_order_id).strip(), provider)
    if order is None:
        return None
    order.status = "REFUNDED"
    order.provider_status = "REFUNDED"
    order.refunded_at = order.refunded_at or now
    order.status_determined_at = now
    ents = session.scalars(
        select(Entitlement).where(Entitlement.purchase_order_id == order.id)
    ).all()
    for ent in ents:
        ent.status = "REVOKED"
        ent.revoked_at = ent.revoked_at or now
    session.flush()
    return order
