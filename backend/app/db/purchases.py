"""Idempotent purchase → entitlement grants."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Entitlement, PurchaseOrder


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
) -> tuple[PurchaseOrder, Entitlement, bool]:
    """
    Returns (order, entitlement, created_new_entitlement).
    Same toss_order_id never double-grants.
    """
    now = datetime.now(timezone.utc)
    order = session.scalar(select(PurchaseOrder).where(PurchaseOrder.toss_order_id == toss_order_id))
    if order is None:
        order = PurchaseOrder(
            user_id=user_id,
            toss_order_id=toss_order_id,
            sku=sku,
            product_id=product_id,
            status="GRANTED",
            status_determined_at=now,
            granted_at=now,
        )
        session.add(order)
        session.flush()
    else:
        # Idempotent: reuse existing order
        pass

    existing = session.scalar(
        select(Entitlement).where(
            Entitlement.user_id == user_id,
            Entitlement.resource_type == resource_type,
            Entitlement.resource_id == resource_id,
            Entitlement.entitlement_type == entitlement_type,
        )
    )
    if existing:
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
    session.flush()
    return order, ent, True
