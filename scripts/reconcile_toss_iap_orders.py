"""Reconcile recent purchase orders against Apps in Toss order status API.

Never logs tokens or private keys. Does not grant new entitlements without verified REFUNDED/PURCHASED status.
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from backend.app.db.models import PurchaseOrder
from backend.app.db.purchases import revoke_from_refund
from backend.app.db.session import session_scope
from backend.app.payments.toss_clients import TossApiError, get_iap_client

logger = logging.getLogger("vagent.iap.reconcile")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, default=72)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=args.hours)
    client = get_iap_client()
    with session_scope() as session:
        orders = session.scalars(
            select(PurchaseOrder)
            .where(PurchaseOrder.created_at >= cutoff)
            .order_by(PurchaseOrder.created_at.desc())
            .limit(args.limit)
        ).all()
        for order in orders:
            oid = order.provider_order_id or order.toss_order_id
            try:
                status = client.get_order_status(oid)
            except TossApiError as exc:
                logger.warning("reconcile_skip order=%s code=%s", oid[:8], exc.code)
                continue
            if status.result_type != "SUCCESS":
                continue
            if status.status == "REFUNDED":
                revoke_from_refund(session, toss_order_id=oid, provider=order.provider or "TOSS")
                logger.info("reconcile_refunded order=%s", oid[:8])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
