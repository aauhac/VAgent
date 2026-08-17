# Refund and recovery

## Pending

App init calls `recoverPendingPurchases()` → `IAP.getPendingOrders` (undefined = unsupported app version, no retry loop) → backend recover → `completeProductGrant` only after `granted: true`.

Ambiguous intents are never auto-bound to a random analysis.

## Refund

`POST /v1/payments/iap/refund` re-reads Toss status. REFUNDED → PurchaseOrder.REFUNDED + Entitlement.REVOKED.

Ops: `python scripts/reconcile_toss_iap_orders.py --hours 72`

## Complete failure

Entitlement already granted: next app entry retries `completeProductGrant` only. No second entitlement.
