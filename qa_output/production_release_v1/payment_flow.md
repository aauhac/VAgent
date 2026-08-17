# Payment flow

Official Apps in Toss one-time IAP (SDK `@apps-in-toss/web-framework` ^2.6.0):

1. `appLogin()` → `POST /v1/auth/toss/login` (server token exchange + login-me). Toss tokens never returned.
2. `POST /v1/payments/iap/intents` `{product_id, analysis_id}` — backend derives SKU, checks owner + purchase eligibility. Intent TTL 20 minutes.
3. Frontend `IAP.getProductItemList()` for displayAmount; `IAP.createOneTimePurchaseOrder` uses backend SKU only.
4. `processProductGrant({orderId})` → `POST /v1/payments/iap/grant` `{intent_id, order_id}`.
5. Server mTLS `POST /api-partner/v1/apps-in-toss/order/get-order-status` with `x-toss-user-key`.
6. Accept `PAYMENT_COMPLETED` or `PURCHASED` and `resultType=SUCCESS`. Deny FAILED / REFUNDED / ORDER_IN_PROGRESS / NOT_FOUND / MINIAPP_MISMATCH. ERROR is retryable.
7. DB grant only after verify. Then frontend `IAP.completeProductGrant`.
8. App entry: `IAP.getPendingOrders` → `POST /v1/payments/iap/recover` → completeProductGrant.

SKU env: `IAP_SONG_DETAIL_SKU`, `IAP_DIAGNOSTIC_FULL_SKU`, `IAP_DIAGNOSTIC_UPGRADE_SKU`. Placeholders fail production payments startup.

Tested with in-process fake Toss clients. Official sandbox / QR test: NOT_RUN.
