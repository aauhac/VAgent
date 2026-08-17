# IAP runbook

Apps in Toss one-time purchase operations for VAgent.

## Happy path

1. Verified Toss login (`appLogin` → `POST /v1/auth/toss/login`).
2. `POST /v1/payments/iap/intents` with `product_id` + `analysis_id`.
3. `IAP.createOneTimePurchaseOrder` using the **backend** SKU.
4. `processProductGrant` calls `POST /v1/payments/iap/grant`.
5. Only if grant returns `granted: true`, call `IAP.completeProductGrant`.

Intent TTL is **20 minutes** (`INTENT_TTL_SECONDS`).

## Pending orders (payment succeeded, grant failed)

Official recovery:

1. On app entry: `IAP.getPendingOrders()`.
2. For each `orderId` (+ `sku` when present): `POST /v1/payments/iap/recover`.
3. Bind only when the authenticated user has **exactly one** unresolved intent for that SKU.
   - 0 intents → `NEEDS_MANUAL_RESTORE` (ignore-safe, do not unlock a random analysis).
   - 2+ intents → `AMBIGUOUS_PENDING_PURCHASE`.
4. After backend grant: `IAP.completeProductGrant({ params: { orderId } })`.
5. If complete fails, retry on the next app entry. Do not create a second entitlement.

## Failed grants

- `processProductGrant` must return `false`.
- User copy: “결제 상태를 확인하고 있어요. 다시 앱을 열어도 이어서 확인할 수 있어요.”
- Do not show raw Toss enums (`PAYMENT_COMPLETED`, `MINIAPP_MISMATCH`, `HTTP_TIMEOUT`).

## Duplicate order

Same `provider + provider_order_id` is unique.

Idempotent success only when **user + product + sku + resource_type + resource_id** all match.

Any mismatch → `409 PAYMENT_ORDER_BINDING_MISMATCH`. Never grant a second resource.

## Refunds

- Client `REFUNDED` is not enough.
- Server re-reads order status over mTLS, then:
  - `PurchaseOrder.status = REFUNDED`
  - `Entitlement.status = REVOKED`
- Operational job: `python scripts/reconcile_toss_iap_orders.py --hours 72`

## Toss outage

- Analysis `/ready` stays up.
- Grant/recover fail closed (`503` retryable / deny).
- Do not fall back to mock unlock.

## DB outage

- Production startup and `/ready` fail closed.
- Do not serve paid content from frontend cache alone.

## User cancel

- Not an error banner. “결제가 취소됐어요.” CTA stays enabled.

## Feature flag

`PAYMENTS_ENABLED=false` stops new purchases. Existing entitlements remain.
