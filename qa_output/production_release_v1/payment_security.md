# Payment security

## P0 fixes

- `TossIAPEntitlementProvider.grant_unlock` now raises `UNVERIFIED_PAYMENT_PROVIDER` (no fallback grant).
- `grant_from_purchase` requires same user + product + sku + resource_type + resource_id to reuse an order id. Mismatch → `PAYMENT_ORDER_BINDING_MISMATCH`.
- Unique `(provider, provider_order_id)`. IntegrityError is read-after-conflict, not raw 500.
- Client headers remain unverified even if `TOSS_IDENTITY_TRUST_MODE=VERIFIED_TOSS_SUBJECT`.
- Payment routes require `require_authenticated_user` (VAgent session after server-side Toss login).
- Frontend cannot choose entitlement type; grant derives from intent.
- Client amount/displayAmount ignored.

## Verified identity

authorizationCode is exchanged only on the backend. AccessToken/RefreshToken are not in the login JSON. Session is a short-lived HMAC VAgent bearer (`VAGENT_SESSION_SECRET`).

## Refunds

Server re-queries Toss status. Client cannot fake refund. Verified REFUNDED revokes entitlements.

## Mocks

Production: mock-unlock / mock-pay / regenerate 403 even if `ALLOW_MOCK_PREMIUM=true`.
